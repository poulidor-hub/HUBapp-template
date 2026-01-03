"""
Client Hub pour l'auto-enregistrement M2M et la communication inter-services.
"""
import httpx
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from config import get_settings

logger = logging.getLogger(__name__)


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
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._credentials: Optional[HubCredentials] = None
        self._public_key: Optional[str] = None
        self._jwks: Optional[dict] = None
    
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
        """Récupère les credentials d'une app déjà enregistrée."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Régénérer le secret pour obtenir de nouveaux credentials
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
                    logger.info(f"✅ Credentials régénérés pour '{self.settings.APP_SLUG}'")
                    return True
                else:
                    logger.error(f"❌ Impossible de récupérer les credentials: {response.text}")
                    return False
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur récupération credentials: {e}")
            return False
    
    async def get_m2m_token(self) -> Optional[str]:
        """
        Obtient un token M2M pour les appels inter-services.
        Gère automatiquement le renouvellement.
        """
        if not self._credentials:
            logger.error("Application non enregistrée auprès du Hub")
            return None
        
        # Vérifier si le token actuel est encore valide
        if (self._credentials.access_token and 
            self._credentials.token_expires_at and 
            datetime.utcnow() < self._credentials.token_expires_at - timedelta(minutes=2)):
            return self._credentials.access_token
        
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
                    # Token M2M valide 30 minutes
                    self._credentials.token_expires_at = datetime.utcnow() + timedelta(minutes=28)
                    return self._credentials.access_token
                else:
                    logger.error(f"❌ Échec obtention token M2M: {response.text}")
                    return None
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur obtention token M2M: {e}")
            return None
    
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
    
    async def call_service(self, service_slug: str, endpoint: str, method: str = "GET", **kwargs) -> Optional[dict]:
        """
        Appelle un autre service via M2M.
        
        Args:
            service_slug: Slug du service cible
            endpoint: Endpoint à appeler (ex: "/api/users")
            method: Méthode HTTP
            **kwargs: Arguments supplémentaires pour httpx
        
        Returns:
            Réponse JSON ou None si erreur
        """
        token = await self.get_m2m_token()
        if not token:
            return None
        
        # TODO: Récupérer l'URL du service via le Hub
        # Pour l'instant, on suppose que le service est sur le même réseau
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = kwargs.pop("headers", {})
                headers["Authorization"] = f"Bearer {token}"
                
                response = await client.request(
                    method,
                    f"{self.settings.hub_api_url.replace(':8000', f':{service_slug}')}{endpoint}",
                    headers=headers,
                    **kwargs
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"❌ Erreur appel service {service_slug}: {response.status_code}")
                    return None
                    
        except httpx.RequestError as e:
            logger.error(f"❌ Erreur appel service {service_slug}: {e}")
            return None


# Instance singleton
hub_client = HubClient()
