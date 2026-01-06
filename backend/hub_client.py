"""
Client Hub pour l'auto-enregistrement M2M et la communication inter-services.

Fonctionnalités :
- Auto-enregistrement au démarrage
- Régénération automatique du secret si invalide (401)
- Cache du token M2M avec renouvellement automatique
- Retry automatique en cas d'erreur d'authentification
- Thread-safety avec asyncio.Lock()
- Découverte dynamique des services partagés (IS_SHARED)
- Attente du certificat CA fourni par le Hub (si HTTPS activé)
"""
import httpx
import asyncio
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import logging

from config import get_settings

logger = logging.getLogger(__name__)

# Nombre max de tentatives de resync automatique
MAX_RESYNC_ATTEMPTS = 3

# Durée de cache pour les services découverts (en secondes)
DISCOVERED_SERVICES_CACHE_TTL = 60

# Configuration attente certificat Hub
CERT_WAIT_INTERVAL = 2  # secondes entre chaque vérification
CERT_WAIT_TIMEOUT = 120  # timeout max en secondes (2 minutes)


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
    """Credentials M2M stockés en mémoire (JAMAIS sur disque)."""
    client_id: str
    client_secret: str
    access_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None


async def download_hub_ca_certificate() -> bool:
    """
    Télécharge le certificat CA du Hub via HTTP.
    
    Cette fonction permet aux applications distantes (sur un autre hôte que le Hub)
    de récupérer automatiquement le certificat CA pour établir des connexions HTTPS.
    
    Le certificat CA est une information publique, donc ce téléchargement initial
    via HTTP est sécuritairement acceptable (similaire aux CA publiques).
    
    Returns:
        True si le certificat a été téléchargé avec succès, False sinon
    
    Note:
        - Utilise HTTP (non HTTPS) car c'est le bootstrap initial
        - Le Hub doit exposer GET /api/pki/ca.crt (endpoint public)
    """
    settings = get_settings()
    
    if not settings.HUB_CA_CERT_PATH:
        logger.error("HUB_CA_CERT_PATH non configuré")
        return False
    
    cert_path = Path(settings.HUB_CA_CERT_PATH)
    
    # URL HTTP pour télécharger le certificat (bootstrap initial)
    # On utilise le port HTTP (HUB_API_PORT) et non HTTPS pour ce premier contact
    hub_http_url = f"http://{settings.hub_host}:{settings.HUB_API_PORT}/api/pki/ca.crt"
    
    logger.info(f"📥 Téléchargement du certificat CA depuis {hub_http_url}...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(hub_http_url)
            
            if response.status_code == 200:
                # Créer le dossier parent si nécessaire
                cert_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Sauvegarder le certificat
                cert_path.write_bytes(response.content)
                
                # Vérifier que c'est bien un certificat PEM
                content = response.content.decode('utf-8', errors='ignore')
                if '-----BEGIN CERTIFICATE-----' in content:
                    logger.info(f"✅ Certificat CA téléchargé et sauvegardé: {cert_path}")
                    return True
                else:
                    logger.error("❌ Le fichier téléchargé n'est pas un certificat PEM valide")
                    cert_path.unlink(missing_ok=True)
                    return False
            
            elif response.status_code == 404:
                logger.error("❌ CA non initialisée sur le Hub. Exécutez 'python pki.py init' sur le Hub.")
                return False
            else:
                logger.error(f"❌ Erreur téléchargement CA: {response.status_code} - {response.text}")
                return False
                
    except httpx.ConnectError:
        logger.error(f"❌ Impossible de contacter le Hub sur {hub_http_url}")
        logger.error("   Vérifiez que le Hub est accessible et que le port HTTP est ouvert")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur lors du téléchargement du certificat CA: {e}")
        return False


async def wait_for_hub_certificate(timeout: int = CERT_WAIT_TIMEOUT) -> bool:
    """
    Attend que le certificat CA du Hub soit disponible.
    
    Cette fonction tente d'abord de télécharger le certificat via HTTP
    si celui-ci n'existe pas localement. Cela permet aux applications
    sur des hôtes distants de fonctionner sans partage de volume Docker.
    
    Flux:
    1. Si le certificat existe déjà localement → l'utiliser
    2. Sinon, tenter de le télécharger via HTTP depuis le Hub
    3. Si le téléchargement échoue, attendre qu'il soit fourni via volume
    
    Une fois trouvé, le certificat est installé au niveau système pour que
    Python/SSL puisse l'utiliser.
    
    Args:
        timeout: Temps max d'attente en secondes (défaut: 120s)
    
    Returns:
        True si le certificat est disponible, False si timeout atteint
    
    Note: 
        - Si HTTPS n'est pas activé, retourne immédiatement True
        - Appelée automatiquement par HubClient.register() si nécessaire
    """
    import subprocess
    import shutil
    
    settings = get_settings()
    
    # Pas besoin d'attendre si HTTPS désactivé
    if not settings.HUB_HTTPS_ENABLED:
        logger.debug("HTTPS désactivé, pas d'attente du certificat CA")
        return True
    
    # Pas de chemin configuré
    if not settings.HUB_CA_CERT_PATH:
        logger.warning("HUB_CA_CERT_PATH non configuré mais HTTPS activé")
        return False
    
    cert_path = Path(settings.HUB_CA_CERT_PATH)
    system_cert_path = Path("/usr/local/share/ca-certificates/hub-ca.crt")
    
    # === ÉTAPE 1: Vérifier si le certificat existe déjà ===
    if cert_path.exists() and cert_path.stat().st_size > 0:
        logger.info(f"✅ Certificat CA déjà présent: {cert_path}")
    else:
        # === ÉTAPE 2: Tenter de télécharger le certificat via HTTP ===
        logger.info("📡 Certificat CA absent, tentative de téléchargement depuis le Hub...")
        downloaded = await download_hub_ca_certificate()
        
        if not downloaded:
            # === ÉTAPE 3: Attendre que le certificat soit fourni via volume ===
            logger.info("⏳ Téléchargement échoué, attente du certificat via volume Docker...")
            elapsed = 0
            
            while elapsed < timeout:
                if cert_path.exists() and cert_path.stat().st_size > 0:
                    logger.info(f"✅ Certificat CA disponible via volume: {cert_path}")
                    break
                
                await asyncio.sleep(CERT_WAIT_INTERVAL)
                elapsed += CERT_WAIT_INTERVAL
                
                if elapsed % 10 == 0:
                    logger.info(f"⏳ Attente du certificat CA... ({elapsed}s/{timeout}s)")
            else:
                logger.error(f"❌ Timeout: certificat CA non disponible après {timeout}s")
                return False
    
    # === ÉTAPE 4: Installer le certificat au niveau système ===
    if cert_path.exists() and cert_path.stat().st_size > 0:
        try:
            if not system_cert_path.exists() or system_cert_path.read_bytes() != cert_path.read_bytes():
                logger.info("🔐 Installation du certificat dans le système...")
                shutil.copy(cert_path, system_cert_path)
                subprocess.run(["update-ca-certificates"], capture_output=True, check=True)
                logger.info("✅ Certificat installé au niveau système")
        except Exception as e:
            logger.warning(f"⚠️ Impossible d'installer le certificat au niveau système: {e}")
            # Continue quand même, httpx utilisera le chemin direct
        
        return True
    
    return False


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
        # Lock pour éviter les régénérations concurrentes
        self._resync_lock = asyncio.Lock()
        self._last_resync_attempt: Optional[datetime] = None
        self._resync_count: int = 0
        # Cache des services découverts
        self._discovered_services: Dict[str, DiscoveredService] = {}
        self._discovered_services_fetched_at: Optional[datetime] = None
    
    @property
    def is_registered(self) -> bool:
        """Vérifie si l'app est enregistrée auprès du Hub."""
        return self._credentials is not None
    
    @property
    def credentials(self) -> Optional[HubCredentials]:
        """Retourne les credentials M2M."""
        return self._credentials
    
    async def register(self) -> bool:
        """
        Auto-enregistrement auprès du Hub.
        À appeler au démarrage de l'application.
        
        Note: Attend automatiquement le certificat CA si HTTPS est activé.
        """
        # Attendre le certificat CA si HTTPS activé
        if self.settings.HUB_HTTPS_ENABLED:
            cert_available = await wait_for_hub_certificate()
            if not cert_available:
                logger.error("Impossible de s'enregistrer: certificat CA du Hub non disponible")
                return False
        
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.settings.hub_ssl_verify) as client:
                # Construire le payload avec les ports HTTPS si disponibles
                payload = {
                    "slug": self.settings.APP_SLUG,
                    "name": self.settings.APP_NAME,
                    "description": self.settings.APP_DESCRIPTION,
                    "api_port": self.settings.API_PORT,
                    "frontend_port": self.settings.FRONTEND_PORT,
                    "is_shared": self.settings.IS_SHARED,  # Service partagé M2M
                }
                # Ajouter le port HTTPS de l'API si configuré
                if self.settings.API_HTTPS_PORT:
                    payload["api_https_port"] = self.settings.API_HTTPS_PORT
                # Ajouter le port HTTPS du frontend si configuré
                if self.settings.FRONTEND_HTTPS_PORT:
                    payload["frontend_https_port"] = self.settings.FRONTEND_HTTPS_PORT
                
                response = await client.post(
                    f"{self.settings.hub_api_url}/api/apps/register",
                    json=payload
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
            logger.error(f"❌ Impossible de contacter le Hub: {e}")
            return False
    
    async def _recover_credentials(self) -> bool:
        """
        Récupère les credentials d'une app déjà enregistrée.
        Utilise un lock pour éviter les régénérations concurrentes.
        """
        async with self._resync_lock:
            logger.debug(f"🔐 Lock acquis pour régénération des credentials")
            try:
                async with httpx.AsyncClient(timeout=10.0, verify=self.settings.hub_ssl_verify) as client:
                    logger.info(f"🔄 Appel Hub: POST /api/apps/me/regenerate-secret (X-Slug: {self.settings.APP_SLUG})")
                    response = await client.post(
                        f"{self.settings.hub_api_url}/api/apps/me/regenerate-secret",
                        headers={"X-Slug": self.settings.APP_SLUG}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        self._credentials = HubCredentials(
                            client_id=data["client_id"],
                            client_secret=data["client_secret"]
                        )
                        self._last_resync_attempt = datetime.utcnow()
                        self._resync_count += 1
                        logger.info(f"✅ Credentials régénérés pour '{self.settings.APP_SLUG}' (resync #{self._resync_count})")
                        logger.debug(f"   Client ID: {self._credentials.client_id}")
                        return True
                    else:
                        logger.error(f"❌ Impossible de récupérer les credentials: {response.status_code} - {response.text}")
                        return False
            except httpx.RequestError as e:
                logger.error(f"❌ Erreur récupération credentials: {e}")
                return False
            finally:
                logger.debug(f"🔓 Lock libéré")
    
    async def _auto_resync(self) -> bool:
        """
        Resynchronisation automatique en cas de secret invalide.
        Protection contre les boucles: max 1 resync toutes les 30 secondes.
        
        Returns:
            True si resync réussi, False sinon
        """
        # Protection contre les boucles de resync
        if self._last_resync_attempt:
            elapsed = (datetime.utcnow() - self._last_resync_attempt).total_seconds()
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
            datetime.utcnow() < self._credentials.token_expires_at - timedelta(minutes=2)):
            logger.debug(f"✅ Token M2M en cache valide")
            return self._credentials.access_token
        
        logger.debug(f"🔄 Obtention d'un nouveau token M2M...")
        
        # Obtenir un nouveau token
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.settings.hub_ssl_verify) as client:
                response = await client.post(
                    f"{self.settings.hub_api_url}/api/auth/token",
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
                            self._credentials.token_expires_at = datetime.fromisoformat(expires_str).replace(tzinfo=None)
                        except (ValueError, TypeError):
                            self._credentials.token_expires_at = datetime.utcnow() + timedelta(minutes=28)
                    else:
                        self._credentials.token_expires_at = datetime.utcnow() + timedelta(minutes=28)
                    
                    logger.info(f"✅ Token M2M obtenu (expire: {self._credentials.token_expires_at})")
                    return self._credentials.access_token
                
                elif response.status_code == 401:
                    # Secret invalide → resync automatique
                    if _retry_count < MAX_RESYNC_ATTEMPTS:
                        logger.warning(f"⚠️ Erreur 401 - Secret invalide (tentative {_retry_count + 1}/{MAX_RESYNC_ATTEMPTS})")
                        if await self._auto_resync():
                            logger.info(f"🔄 Retry après resync...")
                            return await self.get_m2m_token(_retry_count=_retry_count + 1)
                        else:
                            logger.error(f"❌ Resync échoué")
                    else:
                        logger.error(f"❌ Max tentatives atteint ({MAX_RESYNC_ATTEMPTS}), abandon")
                    return None
                else:
                    logger.error(f"❌ Échec obtention token M2M: {response.status_code} - {response.text}")
                    return None
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur obtention token M2M: {e}")
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
            async with httpx.AsyncClient(timeout=10.0, verify=self.settings.hub_ssl_verify) as client:
                response = await client.get(
                    f"{self.settings.hub_api_url}/api/auth/.well-known/jwks.json"
                )
                
                if response.status_code == 200:
                    self._jwks = response.json()
                    logger.info("✅ Clé JWKS récupérée du Hub")
                    return self._jwks
                else:
                    logger.error(f"❌ Échec récupération JWKS: {response.text}")
                    return None
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur récupération JWKS: {e}")
            return None
    
    async def fetch_public_key(self) -> Optional[str]:
        """
        Récupère la clé publique PEM du Hub (alternative à JWKS).
        """
        if self._public_key:
            return self._public_key
        
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.settings.hub_ssl_verify) as client:
                response = await client.get(
                    f"{self.settings.hub_api_url}/api/auth/public-key"
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
            logger.error(f"❌ Erreur récupération clé publique: {e}")
            return None
    
    async def call_service(
        self, 
        service_slug: str, 
        endpoint: str, 
        method: str = "GET", 
        _retry_on_401: bool = True,
        **kwargs
    ) -> Optional[dict]:
        """
        Appelle un autre service via M2M.
        
        Gère automatiquement :
        - Authentification M2M
        - Retry si 401 (avec resync du secret)
        
        Args:
            service_slug: Slug du service cible
            endpoint: Endpoint à appeler (ex: "/api/users")
            method: Méthode HTTP
            _retry_on_401: Réessayer automatiquement si 401 (défaut: True)
            **kwargs: Arguments supplémentaires pour httpx
        
        Returns:
            Réponse JSON ou None si erreur
        """
        token = await self.get_m2m_token()
        if not token:
            logger.error(f"❌ Impossible d'obtenir un token M2M pour appeler {service_slug}")
            return None
        
        # Construire l'URL du service cible en remplaçant le port Hub par le slug du service
        url = f"{self.settings.hub_api_url.replace(f':{self.settings.HUB_API_PORT}', f':{service_slug}')}{endpoint}"
        logger.debug(f"📡 Appel service: {method} {url}")
        
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=self.settings.hub_ssl_verify) as client:
                headers = kwargs.pop("headers", {})
                headers["Authorization"] = f"Bearer {token}"
                
                response = await client.request(
                    method,
                    url,
                    headers=headers,
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
                        return await self.call_service(
                            service_slug, endpoint, method, 
                            _retry_on_401=False,  # Éviter boucle infinie
                            **kwargs
                        )
                    logger.error(f"❌ Resync échoué, abandon de l'appel")
                    return None
                else:
                    logger.error(f"❌ Erreur appel service {service_slug}: {response.status_code} - {response.text[:200]}")
                    return None
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur appel service {service_slug}: {e}")
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
            elapsed = (datetime.utcnow() - self._discovered_services_fetched_at).total_seconds()
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
            async with httpx.AsyncClient(timeout=10.0, verify=self.settings.hub_ssl_verify) as client:
                response = await client.get(
                    f"{self.settings.hub_api_url}/api/apps/discover",
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
                    
                    self._discovered_services_fetched_at = datetime.utcnow()
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
            async with httpx.AsyncClient(timeout=30.0, verify=self.settings.hub_ssl_verify) as client:
                headers = kwargs.pop("headers", {})
                headers["Authorization"] = f"Bearer {token}"
                headers["X-Slug"] = service_slug  # Identification du service cible
                
                response = await client.request(
                    method,
                    url,
                    headers=headers,
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
                    return None
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur appel service {service_slug}: {e}")
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


# Instance singleton
hub_client = HubClient()
