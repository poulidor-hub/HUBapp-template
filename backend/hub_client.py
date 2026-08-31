"""
Client Hub pour l'auto-enregistrement M2M et la communication inter-services.

Fonctionnalités :
- Auto-enregistrement au démarrage
- Régénération automatique du secret si invalide (401)
- Cache du token M2M avec renouvellement automatique
- Retry automatique en cas d'erreur d'authentification
- Thread-safety avec asyncio.Lock()
- Découverte dynamique des services partagés (IS_SHARED)
- Protection contre les enregistrements concurrents (multi-workers)
"""
import httpx
import asyncio
import os
from typing import Optional, List, Dict

# fcntl n'est pas disponible sur Windows — fallback sans file locking
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from config import get_settings, APP_VERSION
from pathlib import Path
from outbox import outbox_service
import yaml

logger = logging.getLogger(__name__)

# Répertoire pour les credentials - /app/storage en container, fallback /tmp en local/test
_storage_dir = Path("/app/storage")
try:
    _storage_dir.mkdir(parents=True, exist_ok=True)
except PermissionError:
    _storage_dir = Path("/tmp")
    logger.warning(f"⚠️ /app/storage inaccessible, fallback vers {_storage_dir}")

# Nombre max de tentatives de resync automatique
MAX_RESYNC_ATTEMPTS = 3

# Durée de cache pour les services découverts (en secondes)
DISCOVERED_SERVICES_CACHE_TTL = 60

# Fichier de lock pour éviter les enregistrements concurrents entre workers
REGISTER_LOCK_FILE = str(_storage_dir / ".hub_register.lock")
# Fichier de credentials partagé entre workers
CREDENTIALS_FILE = str(_storage_dir / ".hub_credentials")
# depends.yaml : cherché dans backend/ (copié dans l'image sous /app) puis,
# à défaut, à la racine du projet (visible uniquement sur l'hôte).
DEPENDS_BACKEND_FILE = Path(__file__).resolve().parent / "depends.yaml"
DEPENDS_ROOT_FILE = Path(__file__).resolve().parent.parent / "depends.yaml"


def _find_depends_file() -> Optional[Path]:
    """Retourne le premier depends.yaml existant (backend/ puis racine), sinon None."""
    for candidate in (DEPENDS_BACKEND_FILE, DEPENDS_ROOT_FILE):
        if candidate.is_file():
            return candidate
    return None


@dataclass
class DiscoveredService:
    """Service découvert via le Hub (en mode IS_SHARED)."""
    slug: str
    name: str
    api_url: str
    description: Optional[str] = None
    # Informations réseau
    ip: Optional[str] = None
    api_port: Optional[int] = None
    frontend_port: Optional[int] = None
    frontend_url: Optional[str] = None
    # Métadonnées
    version: Optional[str] = None
    registered_at: Optional[str] = None
    last_seen: Optional[str] = None
    # Statut détaillé
    is_healthy: bool = True
    is_shared: bool = True
    status: Optional[str] = None  # ex: "online", "offline", "degraded"


@dataclass
class HubCredentials:
    """Credentials M2M. Sauvegardés dans un fichier local (mode 0600) pour partage entre workers."""
    client_id: str
    client_secret: str
    access_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None


class HubClient:
    """
    Client pour communiquer avec le Hub.
    Gère l'auto-enregistrement et les tokens M2M.
    
    Fonctionnalités de résilience :
    - Détection automatique des credentials invalides (401)
    - Régénération automatique du secret
    - Retry transparent pour l'appelant
    - Protection contre les régénérations concurrentes (asyncio.Lock)
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._credentials: Optional[HubCredentials] = None
        self._public_key: Optional[str] = None
        self._jwks: Optional[dict] = None
        # Client HTTP partagé (connection pooling)
        self._http_client: Optional[httpx.AsyncClient] = None
        # Lock pour éviter les régénérations concurrentes
        self._resync_lock = asyncio.Lock()
        self._last_resync_attempt: Optional[datetime] = None
        self._resync_count: int = 0
        # Cache des services découverts
        self._discovered_services: Dict[str, DiscoveredService] = {}
        self._discovered_services_fetched_at: Optional[datetime] = None

    def _load_depends_yaml(self) -> list:
        """Lit depends.yaml (backend/ puis racine) s'il existe. Retourne [] sinon.

        Retourne la liste brute d'entrées : [{"slug": "X", "note": "..."}, ...].
        Jamais d'exception — l'app doit démarrer même si le fichier est corrompu.
        """
        depends_file = _find_depends_file()
        if depends_file is None:
            return []
        try:
            data = yaml.safe_load(depends_file.read_text()) or {}
            return data.get("depends_on", []) or []
        except Exception as e:
            logger.warning(f"⚠️ depends.yaml illisible ({depends_file}): {e}")
            return []

    async def _get_client(self) -> httpx.AsyncClient:
        """Retourne le client HTTP partagé, le créant si nécessaire."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def close(self) -> None:
        """Ferme le client HTTP partagé. À appeler au shutdown de l'application."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.close()
            self._http_client = None
    
    @property
    def is_registered(self) -> bool:
        """Vérifie si l'app est enregistrée auprès du Hub."""
        return self._credentials is not None
    
    @property
    def credentials(self) -> Optional[HubCredentials]:
        """Retourne les credentials M2M."""
        return self._credentials
    
    def _save_credentials_to_file(self) -> None:
        """Sauvegarde les credentials dans un fichier partagé entre workers."""
        if self._credentials:
            try:
                # Écrire avec permissions restrictives (lecture/écriture propriétaire uniquement)
                fd = os.open(CREDENTIALS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w') as f:
                    f.write(f"{self._credentials.client_id}\n{self._credentials.client_secret}")
                logger.debug(f"💾 Credentials sauvegardés dans {CREDENTIALS_FILE} (mode 0600)")
            except Exception as e:
                logger.warning(f"⚠️ Impossible de sauvegarder les credentials: {e}")
    
    def _load_credentials_from_file(self) -> bool:
        """Charge les credentials depuis le fichier partagé."""
        try:
            if os.path.exists(CREDENTIALS_FILE):
                with open(CREDENTIALS_FILE, 'r') as f:
                    lines = f.read().strip().split('\n')
                    if len(lines) >= 2:
                        self._credentials = HubCredentials(
                            client_id=lines[0],
                            client_secret=lines[1]
                        )
                        logger.info(f"📂 Credentials chargés depuis {CREDENTIALS_FILE}")
                        return True
        except Exception as e:
            logger.debug(f"Pas de credentials en cache: {e}")
        return False

    def _clear_cached_credentials(self) -> None:
        """Supprime les credentials locaux devenus invalides."""
        self._credentials = None
        try:
            os.remove(CREDENTIALS_FILE)
        except OSError:
            pass
    
    async def _push_deps_to_hub(self) -> None:
        """Envoie le depends.yaml au hub (best-effort, non bloquant).

        Appelé à chaque succès de register() — que l'enregistrement soit
        nouveau ou que les credentials aient déjà été en cache.
        """
        deps = self._load_depends_yaml()
        if deps:
            try:
                await self.call_hub_endpoint(
                    "/api/apps/dependencies",
                    method="POST",
                    json={"depends_on": deps},
                )
                logger.info(f"📦 Dépendances envoyées au hub ({len(deps)} entrées)")
            except Exception as e:
                logger.warning(f"⚠️ Envoi dépendances au hub échoué: {e}")

    async def register(self) -> bool:
        """
        Auto-enregistrement auprès du Hub.
        À appeler au démarrage de l'application.
        
        Utilise un lock fichier pour éviter que plusieurs workers
        ne s'enregistrent simultanément.

        Après succès (nouvel enregistrement ou cache), envoie toujours
        le graphe de dépendances (depends.yaml) au hub.
        """
        # Essayer de charger les credentials depuis le fichier partagé
        # (un autre worker a peut-être déjà fait l'enregistrement)
        if self._load_credentials_from_file():
            await self._push_deps_to_hub()
            return True
        
        # Utiliser un lock fichier pour éviter les enregistrements concurrents
        lock_file = None
        try:
            if HAS_FCNTL:
                lock_file = open(REGISTER_LOCK_FILE, 'w')
                # Non-blocking lock - si on ne peut pas l'obtenir, un autre worker est en train de s'enregistrer
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (IOError, OSError):
                    # Un autre worker a le lock, attendre qu'il finisse
                    logger.info("⏳ Enregistrement en cours par un autre worker, attente...")
                    await asyncio.sleep(2)  # Attendre un peu
                    # Réessayer de charger les credentials
                    if self._load_credentials_from_file():
                        await self._push_deps_to_hub()
                        return True
                    # Sinon, attendre le lock
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    # Revérifier si les credentials sont disponibles
                    if self._load_credentials_from_file():
                        await self._push_deps_to_hub()
                        return True
                
                # On a le lock, vérifier une dernière fois si les credentials existent
                if self._load_credentials_from_file():
                    await self._push_deps_to_hub()
                    return True
            
            # Faire l'enregistrement
            reg_ok = await self._do_register()
            if reg_ok:
                await self._push_deps_to_hub()
            return reg_ok
            
        finally:
            if lock_file:
                try:
                    if HAS_FCNTL:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except:
                    pass
    
    async def _do_register(self) -> bool:
        """Effectue l'enregistrement réel auprès du Hub."""
        try:
            client = await self._get_client()
            # Construire le payload
            payload = {
                "slug": self.settings.APP_SLUG,
                "name": self.settings.APP_NAME,
                "description": self.settings.APP_DESCRIPTION,
                "api_port": self.settings.API_PORT,
                "frontend_port": self.settings.FRONTEND_PORT,
                "is_shared": self.settings.IS_SHARED,  # Service partagé M2M
                "version": APP_VERSION,  # Version de l'app (fichier VERSION), capturée par le Hub à l'enregistrement
            }
            # Envoyer le port HTTPS si HTTPS est activé
            if self.settings.HTTPS_ENABLED and self.settings.FRONTEND_HTTPS_PORT:
                payload["frontend_https_port"] = self.settings.FRONTEND_HTTPS_PORT
            # Toujours envoyer custom_host avec l'IP de l'application
            # Permet au Hub d'utiliser l'IP correcte définie dans le .env de l'app
            # (APP_HOST si défini, sinon HUB_HOST qui est l'IP du serveur Hub)
            payload["custom_host"] = self.settings.app_host
            if self.settings.is_remote_app:
                logger.info(f"🌐 Application DISTANTE : enregistrement avec custom_host={self.settings.app_host}")
            else:
                logger.info(f"📍 Application LOCALE : enregistrement avec custom_host={self.settings.app_host}")
            
            request_kwargs = {"json": payload}
            if self._credentials and self._credentials.access_token:
                request_kwargs["headers"] = {
                    "Authorization": f"Bearer {self._credentials.access_token}"
                }
            response = await client.post(
                f"{self.settings.hub_api_internal_url}/api/apps/register",
                **request_kwargs,
            )
            
            if response.status_code == 200:
                data = response.json()
                # Les credentials sont dans data["credentials"] ou directement dans data
                creds = data.get("credentials", data)
                is_new = data.get("is_new", True)
                
                # Si l'app existait déjà, le secret n'est pas retourné - il faut le régénérer
                if not is_new and not creds.get("client_secret"):
                    logger.info(f"Application existante, régénération du secret...")
                    return await self._recover_credentials()
                
                self._credentials = HubCredentials(
                    client_id=creds["client_id"],
                    client_secret=creds["client_secret"]
                )
                # Sauvegarder pour les autres workers
                self._save_credentials_to_file()
                logger.info(f"✅ Application '{self.settings.APP_SLUG}' {'enregistrée' if is_new else 'reconnectée'} au Hub")
                return True
            elif response.status_code == 409:
                # App déjà enregistrée, récupérer les credentials existants
                logger.info(f"Application déjà enregistrée, récupération des credentials...")
                return await self._recover_credentials()
            else:
                logger.error(f"❌ Échec enregistrement Hub: {response.status_code} - {response.text}")
                return False
                    
        except httpx.RequestError as e:
            logger.error(
                f"❌ Impossible de contacter le Hub via "
                f"{self.settings.hub_api_internal_url}: "
                f"{type(e).__name__}: {e!r}"
            )
            return False
    
    async def _recover_credentials(self) -> bool:
        """
        Récupère les credentials d'une app déjà enregistrée.

        Chemin de self-healing : ré-enregistrement trusted (POST /api/apps/register).
        Le Hub fait tourner le secret si le SA existe, ou le recrée s'il a
        disparu (T1). regenerate-secret n'est plus utilisé : il exige un token
        M2M valide — or le secret est précisément ce qu'on a perdu (H9).
        Utilise un lock pour éviter les régénérations concurrentes.
        """
        async with self._resync_lock:
            logger.debug("🔐 Lock acquis pour régénération des credentials")
            try:
                client = await self._get_client()
                payload = {
                    "slug": self.settings.APP_SLUG,
                    "name": self.settings.APP_NAME,
                    "description": self.settings.APP_DESCRIPTION,
                    "api_port": self.settings.API_PORT,
                    "frontend_port": self.settings.FRONTEND_PORT,
                    "is_shared": self.settings.IS_SHARED,
                    "version": APP_VERSION,
                    "custom_host": self.settings.app_host,
                }
                # Envoyer le port HTTPS si HTTPS est activé (parité avec _do_register :
                # le register mid-life met à jour l'app côté Hub — sans ce champ, le Hub
                # écrase frontend_https_port à None et repasse l'URL en http)
                if self.settings.HTTPS_ENABLED and self.settings.FRONTEND_HTTPS_PORT:
                    payload["frontend_https_port"] = self.settings.FRONTEND_HTTPS_PORT
                logger.info(
                    f"🔄 Appel Hub: POST /api/apps/register "
                    f"(self-healing, slug: {self.settings.APP_SLUG})"
                )
                response = await client.post(
                    f"{self.settings.hub_api_internal_url}/api/apps/register",
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    creds = data.get("credentials", data)
                    if not creds.get("client_secret"):
                        logger.error(
                            "❌ Register n'a pas retourné de client_secret "
                            "(Hub sans correctif T1 ?)"
                        )
                        return False
                    self._credentials = HubCredentials(
                        client_id=creds["client_id"],
                        client_secret=creds["client_secret"],
                    )
                    self._last_resync_attempt = datetime.now(timezone.utc)
                    self._resync_count += 1
                    # Sauvegarder pour les autres workers
                    self._save_credentials_to_file()
                    logger.info(
                        f"✅ Credentials récupérés via register pour "
                        f"'{self.settings.APP_SLUG}' (resync #{self._resync_count})"
                    )
                    return True
                elif response.status_code == 404:
                    logger.warning(
                        f"⚠️ Application '{self.settings.APP_SLUG}' introuvable sur le Hub, "
                        f"réinscription avec suppression du cache local"
                    )
                    self._clear_cached_credentials()
                    return await self._do_register()
                else:
                    logger.error(
                        f"❌ Impossible de récupérer les credentials: "
                        f"{response.status_code} - {response.text}"
                    )
                    return False
            except httpx.RequestError as e:
                logger.error(
                    f"❌ Erreur récupération credentials via "
                    f"{self.settings.hub_api_internal_url}: "
                    f"{type(e).__name__}: {e!r}"
                )
                return False
            finally:
                logger.debug("🔓 Lock libéré")
    
    async def _auto_resync(self) -> bool:
        """
        Resynchronisation automatique en cas de secret invalide.
        Protection contre les boucles: max 1 resync toutes les 30 secondes.
        
        Returns:
            True si resync réussi, False sinon
        """
        # Protection contre les boucles de resync
        if self._last_resync_attempt:
            elapsed = (datetime.now(timezone.utc) - self._last_resync_attempt).total_seconds()
            if elapsed < 30:
                logger.warning(f"⚠️ Resync ignoré (dernier il y a {elapsed:.0f}s, cooldown 30s)")
                return False
        
        logger.warning(f"🔄 Secret invalide détecté, resynchronisation automatique...")
        
        # Invalider le token actuel
        if self._credentials:
            logger.debug(f"🗑️ Invalidation du token actuel")
            self._credentials.access_token = None
            self._credentials.token_expires_at = None
        
        return await self._recover_credentials()
    
    async def get_m2m_token(self, _retry_count: int = 0) -> Optional[str]:
        """
        Obtient un token M2M pour les appels inter-services.
        
        Gère automatiquement :
        - Cache du token avec renouvellement avant expiration
        - Resync automatique si secret invalide (401)
        - Retry transparent (max 3 tentatives)
        
        Args:
            _retry_count: Compteur interne de retry (ne pas utiliser)
        
        Returns:
            Token M2M ou None si erreur
        """
        if not self._credentials:
            logger.warning("⚠️ Application non enregistrée, tentative d'enregistrement...")
            if await self.register():
                return await self.get_m2m_token(_retry_count=_retry_count)
            logger.error("❌ Impossible d'enregistrer l'application")
            return None
        
        # Vérifier si le token actuel est encore valide (marge de 2 min)
        if (self._credentials.access_token and 
            self._credentials.token_expires_at and 
            datetime.now(timezone.utc) < self._credentials.token_expires_at - timedelta(minutes=2)):
            logger.debug(f"✅ Token M2M en cache valide")
            return self._credentials.access_token
        
        logger.debug(f"🔄 Obtention d'un nouveau token M2M...")
        
        # Obtenir un nouveau token
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.settings.hub_api_internal_url}/api/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._credentials.client_id,
                    "client_secret": self._credentials.client_secret,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self._credentials.access_token = data["access_token"]
                
                # Parser l'expiration si fournie
                if "expires_at" in data:
                    try:
                        expires_str = data["expires_at"].replace("Z", "+00:00")
                        parsed = datetime.fromisoformat(expires_str)
                        # S'assurer que le datetime est timezone-aware (UTC)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        self._credentials.token_expires_at = parsed
                    except (ValueError, TypeError):
                        self._credentials.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=28)
                else:
                    self._credentials.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=28)
                
                logger.info(f"✅ Token M2M obtenu (expire: {self._credentials.token_expires_at})")
                return self._credentials.access_token
            
            elif response.status_code == 401:
                # Secret invalide → resync automatique
                if _retry_count < MAX_RESYNC_ATTEMPTS:
                    logger.warning(f"⚠️ Erreur 401 - Secret invalide (tentative {_retry_count + 1}/{MAX_RESYNC_ATTEMPTS})")
                    if await self._auto_resync():
                        # Backoff exponentiel avant retry (1s, 2s, 4s)
                        backoff = 2 ** _retry_count
                        logger.info(f"🔄 Retry après resync (backoff {backoff}s)...")
                        await asyncio.sleep(backoff)
                        return await self.get_m2m_token(_retry_count=_retry_count + 1)
                    else:
                        logger.error(f"❌ Resync échoué")
                else:
                    logger.error(f"❌ Max tentatives atteint ({MAX_RESYNC_ATTEMPTS}), abandon")
                return None
            
            elif response.status_code == 403:
                # Service account désactivé → réenregistrement complet
                if _retry_count < MAX_RESYNC_ATTEMPTS:
                    logger.warning(f"⚠️ Erreur 403 - SA désactivé (tentative {_retry_count + 1}/{MAX_RESYNC_ATTEMPTS}), réenregistrement...")
                    # Invalider les credentials actuelles pour forcer un nouvel enregistrement
                    self._clear_cached_credentials()
                    if await self.register():
                        backoff = 2 ** _retry_count
                        logger.info(f"🔄 Retry après réenregistrement (backoff {backoff}s)...")
                        await asyncio.sleep(backoff)
                        return await self.get_m2m_token(_retry_count=_retry_count + 1)
                    else:
                        logger.error(f"❌ Réenregistrement échoué")
                else:
                    logger.error(f"❌ Max tentatives atteint ({MAX_RESYNC_ATTEMPTS}), abandon")
                return None
            else:
                logger.error(f"❌ Échec obtention token M2M: {response.status_code} - {response.text}")
                return None
                    
        except httpx.RequestError as e:
            logger.error(
                f"❌ Erreur obtention token M2M via "
                f"{self.settings.hub_api_internal_url}: "
                f"{type(e).__name__}: {e!r}"
            )
            return None
    
    async def ensure_valid_credentials(self) -> bool:
        """
        Vérifie que les credentials sont valides en obtenant un token.
        Utile pour tester la connexion au Hub.
        
        Returns:
            True si credentials valides, False sinon
        """
        token = await self.get_m2m_token()
        return token is not None
    
    async def fetch_jwks(self) -> Optional[dict]:
        """
        Récupère la clé publique JWKS du Hub pour valider les tokens.
        Recommandé par rapport à la clé PEM.
        """
        if self._jwks:
            return self._jwks
        
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.settings.hub_api_internal_url}/api/auth/.well-known/jwks.json"
            )
            
            if response.status_code == 200:
                self._jwks = response.json()
                logger.info("✅ Clé JWKS récupérée du Hub")
                return self._jwks
            else:
                logger.error(f"❌ Échec récupération JWKS: {response.text}")
                return None
                    
        except httpx.RequestError as e:
            logger.error(
                f"❌ Erreur récupération JWKS via "
                f"{self.settings.hub_api_internal_url}: "
                f"{type(e).__name__}: {e!r}"
            )
            return None
    
    async def fetch_public_key(self) -> Optional[str]:
        """
        Récupère la clé publique PEM du Hub (alternative à JWKS).
        """
        if self._public_key:
            return self._public_key
        
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.settings.hub_api_internal_url}/api/auth/public-key"
            )
            
            if response.status_code == 200:
                data = response.json()
                self._public_key = data.get("public_key")
                logger.info("✅ Clé publique PEM récupérée du Hub")
                return self._public_key
            else:
                logger.error(f"❌ Échec récupération clé publique: {response.text}")
                return None
                    
        except httpx.RequestError as e:
            logger.error(
                f"❌ Erreur récupération clé publique via "
                f"{self.settings.hub_api_internal_url}: "
                f"{type(e).__name__}: {e!r}"
            )
            return None

    async def discover_services(self, force_refresh: bool = False) -> Dict[str, DiscoveredService]:
        """
        Découvre les services partagés (IS_SHARED=true) disponibles via le Hub.
        
        Appelle GET /api/apps/discover qui retourne tous les services partagés
        avec leur api_url dynamique.
        
        Args:
            force_refresh: Force le rafraîchissement du cache
        
        Returns:
            Dictionnaire {slug: DiscoveredService}
        """
        # Vérifier le cache
        if not force_refresh and self._discovered_services_fetched_at:
            elapsed = (datetime.now(timezone.utc) - self._discovered_services_fetched_at).total_seconds()
            if elapsed < DISCOVERED_SERVICES_CACHE_TTL:
                logger.debug(f"✅ Services découverts en cache ({len(self._discovered_services)} services)")
                return self._discovered_services
        
        logger.info(f"🔍 Découverte des services partagés via le Hub...")
        
        # Obtenir le token M2M pour l'authentification
        token = await self.get_m2m_token()
        if not token:
            logger.error(f"❌ Impossible d'obtenir un token M2M pour la découverte des services")
            return self._discovered_services
        
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.settings.hub_api_internal_url}/api/apps/discover",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Slug": self.settings.APP_SLUG
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                # Le Hub retourne "shared_services" (priorité), "services" ou "apps"
                services = data if isinstance(data, list) else data.get("shared_services", data.get("services", data.get("apps", [])))
                
                self._discovered_services = {}
                for svc in services:
                    slug = svc.get("slug")
                    if slug:
                        self._discovered_services[slug] = DiscoveredService(
                            slug=slug,
                            name=svc.get("name", slug),
                            api_url=svc.get("api_url", ""),
                            description=svc.get("description"),
                            # Informations réseau
                            ip=svc.get("ip"),
                            api_port=svc.get("api_port"),
                            frontend_port=svc.get("frontend_port"),
                            frontend_url=svc.get("frontend_url"),
                            # Métadonnées
                            version=svc.get("version"),
                            registered_at=svc.get("registered_at"),
                            last_seen=svc.get("last_seen"),
                            # Statut détaillé
                            is_healthy=svc.get("is_healthy", True),
                            is_shared=svc.get("is_shared", True),
                            status=svc.get("status", "online" if svc.get("is_healthy", True) else "offline")
                        )
                
                self._discovered_services_fetched_at = datetime.now(timezone.utc)
                logger.info(f"✅ {len(self._discovered_services)} service(s) partagé(s) découvert(s)")
                for slug, svc in self._discovered_services.items():
                    logger.debug(f"   - {slug}: {svc.api_url} (v{svc.version or '?'}, {svc.status})")
                
                return self._discovered_services
            else:
                logger.error(f"❌ Échec découverte services: {response.status_code} - {response.text}")
                return self._discovered_services
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur découverte services: {e}")
            return self._discovered_services
    
    async def get_service_by_slug(self, slug: str, force_refresh: bool = False) -> Optional[DiscoveredService]:
        """
        Récupère un service découvert par son slug.
        
        Args:
            slug: Identifiant unique du service
            force_refresh: Force le rafraîchissement du cache
        
        Returns:
            DiscoveredService ou None si non trouvé
        """
        services = await self.discover_services(force_refresh=force_refresh)
        return services.get(slug)
    
    async def call_discovered_service(
        self,
        service_slug: str,
        endpoint: str,
        method: str = "GET",
        _retry_on_401: bool = True,
        _retry_on_discover: bool = True,
        **kwargs
    ) -> Optional[dict]:
        """
        Appelle un service découvert dynamiquement via M2M.
        
        Utilise l'api_url récupérée via discover et ajoute le header X-Slug
        pour l'identification du service cible.
        
        Args:
            service_slug: Slug du service cible (ex: "mon-autre-app")
            endpoint: Endpoint à appeler (ex: "/api/users")
            method: Méthode HTTP (GET, POST, PUT, DELETE, etc.)
            _retry_on_401: Réessayer automatiquement si 401 (défaut: True)
            _retry_on_discover: Re-découvrir si service non trouvé (défaut: True)
            **kwargs: Arguments supplémentaires pour httpx (json, data, params, etc.)
        
        Returns:
            Réponse JSON ou None si erreur
        
        Example:
            # Appeler GET /api/items sur le service "inventaire"
            result = await hub_client.call_discovered_service(
                "inventaire",
                "/api/items",
                method="GET"
            )
            
            # Appeler POST /api/orders sur le service "commandes"
            result = await hub_client.call_discovered_service(
                "commandes",
                "/api/orders",
                method="POST",
                json={"product_id": 123, "quantity": 2}
            )
        """
        # Récupérer le service découvert
        service = await self.get_service_by_slug(service_slug)
        
        if not service:
            if _retry_on_discover:
                logger.warning(f"⚠️ Service '{service_slug}' non trouvé, rafraîchissement du cache...")
                service = await self.get_service_by_slug(service_slug, force_refresh=True)
            
            if not service:
                logger.error(f"❌ Service '{service_slug}' non trouvé parmi les services partagés")
                return None
        
        if not service.api_url:
            logger.error(f"❌ Pas d'api_url pour le service '{service_slug}'")
            return None
        
        # Obtenir le token M2M
        token = await self.get_m2m_token()
        if not token:
            logger.error(f"❌ Impossible d'obtenir un token M2M pour appeler {service_slug}")
            return None
        
        # Construire l'URL complète
        url = f"{service.api_url.rstrip('/')}{endpoint}"
        logger.debug(f"📡 Appel service découvert: {method} {url} (X-Slug: {service_slug})")
        
        try:
            client = await self._get_client()
            headers = kwargs.pop("headers", {})
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Slug"] = service_slug  # Identification du service cible
            
            response = await client.request(
                method,
                url,
                headers=headers,
                timeout=30.0,
                **kwargs
            )
            
            if response.status_code == 200:
                logger.debug(f"✅ Réponse OK de {service_slug}")
                return response.json()
            
            elif response.status_code == 401 and _retry_on_401:
                # Token rejeté → resync et retry
                logger.warning(f"⚠️ 401 sur {method} {url}, tentative de resync...")
                if await self._auto_resync():
                    logger.info(f"🔄 Retry après resync...")
                    return await self.call_discovered_service(
                        service_slug, endpoint, method,
                        _retry_on_401=False,
                        _retry_on_discover=False,
                        **kwargs
                    )
                logger.error(f"❌ Resync échoué, abandon de l'appel")
                return None
            
            elif response.status_code == 404 and _retry_on_discover:
                # Service peut avoir changé d'URL → re-découvrir
                logger.warning(f"⚠️ 404 sur {url}, le service a peut-être changé d'URL...")
                return await self.call_discovered_service(
                    service_slug, endpoint, method,
                    _retry_on_401=_retry_on_401,
                    _retry_on_discover=False,
                    **kwargs
                )
            else:
                logger.error(f"❌ Erreur appel service {service_slug}: {response.status_code} - {response.text[:200]}")
                if response.status_code >= 500:
                    try:
                        msg_id = await outbox_service.enqueue(
                            target_url=url,
                            method=method,
                            headers=kwargs.get("headers", {}),
                            payload=kwargs.get("json"),
                            target_slug=service_slug,
                            auth_context={"type": "m2m", "slug": service_slug},
                        )
                        logger.info(f"📦 Message outbox #{msg_id} créé (HTTP {response.status_code})")
                    except Exception as outbox_err:
                        logger.error(f"❌ Outbox enqueue failed: {outbox_err}")
                return None
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur appel service {service_slug}: {e}")
            try:
                msg_id = await outbox_service.enqueue(
                    target_url=url,
                    method=method,
                    headers=kwargs.get("headers", {}),
                    payload=kwargs.get("json"),
                    target_slug=service_slug,
                    auth_context={"type": "m2m", "slug": service_slug},
                )
                logger.info(f"📦 Message outbox #{msg_id} créé pour {service_slug}{endpoint}")
            except Exception as outbox_err:
                logger.error(f"❌ Outbox enqueue failed: {outbox_err}")
            return None
    
    async def list_discovered_services(self, force_refresh: bool = False) -> List[DiscoveredService]:
        """
        Liste tous les services partagés disponibles.
        
        Args:
            force_refresh: Force le rafraîchissement du cache
        
        Returns:
            Liste des services découverts
        """
        services = await self.discover_services(force_refresh=force_refresh)
        return list(services.values())

    async def send_user_message(
        self,
        target_usernames: list[str],
        title: str,
        body: Optional[str] = None,
        priority: str = "info",
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        expires_at: Optional[str] = None,
        is_resend: bool = False,
        original_hub_message_id: Optional[int] = None
    ) -> Optional[dict]:
        """
        Envoie un message à des utilisateurs via le Hub (M2M).
        
        Args:
            target_usernames: Liste des usernames destinataires
            title: Titre du message (max 200 caractères)
            body: Corps du message (optionnel)
            priority: Niveau de priorité ("info", "warning", "urgent")
            action_url: URL d'action optionnelle (lien cliquable)
            action_label: Libellé du bouton d'action (optionnel)
            expires_at: Date d'expiration ISO (optionnel)
            is_resend: Marquer comme renvoi (le Hub préfixe le titre avec [Renvoi])
            original_hub_message_id: ID du message original côté Hub (traçabilité)
        
        Returns:
            Réponse JSON du Hub ou None si erreur
        """
        payload = {
            "title": title,
            "target_usernames": target_usernames,
            "priority": priority,
        }
        if body:
            payload["body"] = body
        if action_url:
            payload["action_url"] = action_url
        if action_label:
            payload["action_label"] = action_label
        if expires_at:
            payload["expires_at"] = expires_at
        if is_resend:
            payload["is_resend"] = True
        if original_hub_message_id is not None:
            payload["original_hub_message_id"] = original_hub_message_id

        result = await self.call_hub_endpoint(
            "/api/messages/m2m/send",
            method="POST",
            json=payload
        )
        if result and "error" not in result:
            logger.info(f"📩 Message envoyé à {len(target_usernames)} utilisateur(s): {title}")
        else:
            logger.error(f"❌ Erreur envoi message: {result}")
        return result

    async def send_message(self, payload: dict) -> Optional[dict]:
        """
        Envoie un message via le Hub M2M avec un payload brut.
        
        Raccourci pour call_hub_endpoint("/api/messages/m2m/send", ...).
        Utile quand le payload est déjà construit (ex: renvoi avec champs custom).
        
        Args:
            payload: Dict contenant au minimum title et target_usernames
        
        Returns:
            Réponse JSON du Hub ou None si erreur
        """
        return await self.call_hub_endpoint(
            "/api/messages/m2m/send",
            method="POST",
            json=payload
        )

    async def call_hub_endpoint(
        self,
        endpoint: str,
        method: str = "GET",
        _retry_on_401: bool = True,
        timeout: float = 30.0,
        **kwargs
    ) -> Optional[dict]:
        """
        Appelle directement un endpoint de l'API Hub avec authentification M2M.
        
        Contrairement à call_discovered_service qui route via un slug de service,
        cette méthode appelle directement le Hub lui-même.
        
        Args:
            endpoint: Endpoint à appeler (ex: "/api/apps/mon-app/backup")
            method: Méthode HTTP (GET, POST, PUT, DELETE)
            _retry_on_401: Réessayer automatiquement si 401 (défaut: True)
            timeout: Timeout en secondes (défaut: 30)
            **kwargs: Arguments supplémentaires pour httpx (json, data, files, params, etc.)
        
        Returns:
            Réponse JSON ou None si erreur
        """
        # Obtenir le token M2M
        token = await self.get_m2m_token()
        if not token:
            logger.error(f"❌ Impossible d'obtenir un token M2M pour appeler le Hub")
            return None
        
        url = f"{self.settings.hub_api_internal_url.rstrip('/')}{endpoint}"
        logger.debug(f"📡 Appel Hub: {method} {url}")
        
        try:
            client = await self._get_client()
            headers = kwargs.pop("headers", {})
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Slug"] = self.settings.APP_SLUG
            
            response = await client.request(
                method,
                url,
                headers=headers,
                timeout=timeout,
                **kwargs
            )
            
            if response.status_code == 200:
                # Essayer de parser en JSON, sinon retourner le contenu brut
                try:
                    return response.json()
                except Exception:
                    return {"success": True, "content": response.text[:500]}
            
            elif response.status_code == 401 and _retry_on_401:
                logger.warning(f"⚠️ 401 sur {method} {url}, tentative de resync...")
                if await self._auto_resync():
                    return await self.call_hub_endpoint(
                        endpoint, method,
                        _retry_on_401=False,
                        timeout=timeout,
                        **kwargs
                    )
                logger.error(f"❌ Resync échoué, abandon de l'appel Hub")
                return None
            
            else:
                error_text = response.text[:200] if response.text else "(pas de contenu)"
                logger.error(f"❌ Erreur appel Hub: {response.status_code} - {error_text}")
                if response.status_code >= 500:
                    try:
                        msg_id = await outbox_service.enqueue(
                            target_url=url,
                            method=method,
                            headers=kwargs.get("headers", {}),
                            payload=kwargs.get("json"),
                            target_slug="hub",
                            auth_context={"type": "m2m", "slug": "hub"},
                        )
                        logger.info(f"📦 Message outbox #{msg_id} créé (HTTP {response.status_code})")
                    except Exception as outbox_err:
                        logger.error(f"❌ Outbox enqueue failed: {outbox_err}")
                return {"error": error_text, "status_code": response.status_code}
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur réseau appel Hub: {e}")
            try:
                msg_id = await outbox_service.enqueue(
                    target_url=url,
                    method=method,
                    headers=kwargs.get("headers", {}),
                    payload=kwargs.get("json"),
                    target_slug="hub",
                    auth_context={"type": "m2m", "slug": "hub"},
                )
                logger.info(f"📦 Message outbox #{msg_id} créé pour Hub{endpoint}")
            except Exception as outbox_err:
                logger.error(f"❌ Outbox enqueue failed: {outbox_err}")
            return None

    async def call_discovered_service_with_guarantee(
        self,
        service_slug: str,
        endpoint: str,
        method: str = "POST",
        payload: Optional[dict] = None,
        max_retries: int = 10,
    ) -> Optional[int]:
        """
        Appelle un service avec garantie de livraison via outbox.

        Contrairement à call_discovered_service, cette méthode écrit directement
        dans l'outbox pour une livraison asynchrone garantie.

        Returns:
            ID du message outbox, ou None si erreur avant enqueue
        """
        service = await self.get_service_by_slug(service_slug)
        if not service:
            service = await self.get_service_by_slug(service_slug, force_refresh=True)
        if not service or not service.api_url:
            logger.error(f"❌ Cannot enqueue: service '{service_slug}' not found")
            return None

        token = await self.get_m2m_token()
        if not token:
            logger.error(f"❌ Cannot enqueue: no M2M token for {service_slug}")
            return None

        url = f"{service.api_url.rstrip('/')}{endpoint}"
        headers = {"X-Slug": service_slug}
        auth_context = {"type": "m2m", "slug": service_slug}

        return await outbox_service.enqueue(
            target_url=url,
            method=method,
            headers=headers,
            payload=payload,
            target_slug=service_slug,
            auth_context=auth_context,
            max_retries=max_retries,
        )

    async def call_hub_endpoint_with_guarantee(
        self,
        endpoint: str,
        method: str = "POST",
        payload: Optional[dict] = None,
        max_retries: int = 10,
    ) -> Optional[int]:
        """
        Appelle un endpoint Hub avec garantie de livraison via outbox.

        Returns:
            ID du message outbox, ou None si erreur avant enqueue
        """
        token = await self.get_m2m_token()
        if not token:
            logger.error(f"❌ Cannot enqueue hub endpoint: no M2M token")
            return None

        url = f"{self.settings.hub_api_internal_url.rstrip('/')}{endpoint}"
        headers = {"X-Slug": self.settings.APP_SLUG}
        auth_context = {"type": "m2m", "slug": "hub"}

        return await outbox_service.enqueue(
            target_url=url,
            method=method,
            headers=headers,
            payload=payload,
            target_slug="hub",
            auth_context=auth_context,
            max_retries=max_retries,
        )

    async def fetch_app_cert(self) -> Optional[dict]:
        """
        Récupère le certificat HTTPS émis par la PKI du HUB pour cette app.

        Appelle POST /api/apps/cert/issue (Bearer token M2M + X-Slug) et
        retourne le dict {cert, key, ca, san, fingerprint} (PEM str), ou None
        si le HUB est injoignable / n'a pas émis de certificat.
        """
        data = await self.call_hub_endpoint("/api/apps/cert/issue", method="POST")
        if data and "error" not in data and data.get("cert"):
            return data
        return None

    async def report_sync(self, target_slug: str) -> None:
        """Signale au hub qu'une synchro M2M vient de réussir avec ``target_slug``.

        Met à jour ``last_sync_at`` côté hub. Best-effort : ne lève jamais,
        ne casse jamais le flux métier appelant. À appeler après un
        ``call_discovered_service`` réussi.
        """
        try:
            await self.call_hub_endpoint(
                "/api/apps/sync-report",
                method="POST",
                json={"target": target_slug},
            )
            logger.debug(f"📡 report_sync → {target_slug} ok")
        except Exception as e:
            logger.warning(f"⚠️ report_sync vers {target_slug} échoué: {e}")


# Instance singleton
hub_client = HubClient()
