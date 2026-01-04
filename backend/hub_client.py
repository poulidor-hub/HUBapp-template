"""
Client Hub pour l'auto-enregistrement M2M et la communication inter-services.

Fonctionnalités :
- Auto-enregistrement au démarrage
- Régénération automatique du secret si invalide (401)
- Cache du token M2M avec renouvellement automatique
- Retry automatique en cas d'erreur d'authentification
- Thread-safety avec asyncio.Lock()
"""
import httpx
import asyncio
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from config import get_settings

logger = logging.getLogger(__name__)

# Nombre max de tentatives de resync automatique
MAX_RESYNC_ATTEMPTS = 3


@dataclass
class HubCredentials:
    """Credentials M2M stockés en mémoire (JAMAIS sur disque)."""
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
        # Lock pour éviter les régénérations concurrentes
        self._resync_lock = asyncio.Lock()
        self._last_resync_attempt: Optional[datetime] = None
        self._resync_count: int = 0
    
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
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.settings.hub_api_url}/api/apps/register",
                    json={
                        "slug": self.settings.APP_SLUG,
                        "name": self.settings.APP_NAME,
                        "description": self.settings.APP_DESCRIPTION,
                        "api_port": self.settings.API_PORT,
                        "frontend_port": self.settings.FRONTEND_PORT,
                    }
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
                async with httpx.AsyncClient(timeout=10.0) as client:
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
            async with httpx.AsyncClient(timeout=30.0) as client:
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


# Instance singleton
hub_client = HubClient()
