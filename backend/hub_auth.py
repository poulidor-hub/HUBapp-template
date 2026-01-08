"""
Module d'authentification Hub avec validation JWT et gestion des rôles.

Fonctionnalités :
- Rotation automatique des clés JWKS (plus besoin de redéployer)
- Cache intelligent avec TTL de 1h
- Fallback automatique sur clé PEM si JWKS indisponible
"""
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Callable
from functools import wraps
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from datetime import datetime, timedelta
import logging
import ssl

from config import get_settings
from hub_client import hub_client

logger = logging.getLogger(__name__)

# Configuration du cache JWKS
JWKS_CACHE_TTL_SECONDS = 3600  # 1 heure - Rotation automatique des clés
PEM_CACHE_TTL_SECONDS = 3600   # 1 heure - Cache pour la clé PEM fallback


class RoleLevel(IntEnum):
    """Niveaux de rôles hiérarchiques."""
    VIEWER = 1
    USER = 2
    MANAGER = 3
    ADMIN = 4
    SERVICE = 3  # Service account = niveau manager


ROLE_MAPPING = {
    "viewer": RoleLevel.VIEWER,
    "user": RoleLevel.USER,
    "manager": RoleLevel.MANAGER,
    "admin": RoleLevel.ADMIN,
    "service": RoleLevel.SERVICE,
}


@dataclass
class TokenPayload:
    """Payload décodé du token JWT."""
    sub: str  # Username
    roles: list[str]  # Rôles globaux
    apps: dict[str, str]  # Rôles par application {app_slug: role}
    token_type: str  # "user" ou "service"
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    jti: str  # Token ID unique
    
    def get_app_role(self, app_slug: str) -> Optional[str]:
        """Retourne le rôle pour une application spécifique."""
        return self.apps.get(app_slug)
    
    def get_app_role_level(self, app_slug: str) -> int:
        """Retourne le niveau de rôle pour une application."""
        role = self.get_app_role(app_slug)
        if role:
            return ROLE_MAPPING.get(role, 0)
        return 0
    
    def has_global_role(self, role: str) -> bool:
        """Vérifie si l'utilisateur a un rôle global."""
        return role in self.roles
    
    def is_service_account(self) -> bool:
        """Vérifie si c'est un service account (M2M)."""
        # La doc indique que token_type peut être "service_account" ou "service"
        # Et le rôle dans apps peut être "service"
        return (
            self.token_type in ("service", "service_account") or 
            "service_account" in self.roles or
            "service" in self.apps.values()
        )


class HubAuth:
    """
    Gestion de l'authentification via le Hub.
    
    Stratégie de validation JWT :
    1. JWKS (standard OIDC) - Méthode recommandée avec rotation automatique des clés
    2. Clé PEM statique - Fallback si JWKS indisponible
    
    Fonctionnalités de résilience :
    - Cache JWKS avec TTL de 1h (rotation automatique des clés)
    - Fallback automatique sur clé PEM si JWKS indisponible (init + runtime)
    - Pas besoin de redéployer lors de la rotation des clés
    
    Configuration SSL/TLS :
    - VERIFY_SSL: Active/désactive la vérification SSL (défaut: True)
    - HUB_CA_CERT_PATH: Chemin vers le certificat CA pour les certificats auto-signés
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._jwk_client: Optional[PyJWKClient] = None
        self._public_key: Optional[str] = None
        self._public_key_fetched_at: Optional[datetime] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
        self._jwks_available: bool = True  # Flag pour le fallback intelligent
    
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """
        Crée un contexte SSL pour les connexions JWKS.
        
        Returns:
            SSLContext configuré ou None si SSL désactivé
        """
        if not self.settings.VERIFY_SSL:
            logger.warning("⚠️ Vérification SSL désactivée (VERIFY_SSL=False)")
            return None
        
        ssl_context = ssl.create_default_context()
        
        # Certificat CA personnalisé (pour certificats auto-signés)
        if self.settings.HUB_CA_CERT_PATH:
            ca_path = Path(self.settings.HUB_CA_CERT_PATH)
            if ca_path.exists():
                ssl_context.load_verify_locations(str(ca_path))
                logger.info(f"✅ Certificat CA chargé: {ca_path}")
            else:
                logger.warning(f"⚠️ Certificat CA non trouvé: {ca_path}")
        
        return ssl_context
    
    async def initialize(self):
        """
        Initialise l'authentification en récupérant les clés du Hub.
        
        Le cache JWKS a un TTL de 1h, permettant la rotation automatique
        des clés sans redéploiement de l'application.
        
        Tente d'abord JWKS (standard OIDC), puis fallback sur PEM.
        """
        self._ssl_context = self._create_ssl_context()
        
        # Tentative 1: JWKS (méthode recommandée - standard OIDC)
        try:
            jwks_url = f"{self.settings.hub_api_url}/api/auth/.well-known/jwks.json"
            self._jwk_client = PyJWKClient(
                jwks_url,
                ssl_context=self._ssl_context,
                cache_keys=True,
                lifespan=JWKS_CACHE_TTL_SECONDS  # Cache 1h
            )
            # Test de connexion pour valider que JWKS est accessible
            self._jwk_client.get_signing_keys()
            self._jwks_available = True
            logger.info(f"✅ Authentification Hub initialisée (JWKS, cache {JWKS_CACHE_TTL_SECONDS}s)")
            return
        except Exception as e:
            logger.warning(f"⚠️ JWKS indisponible, fallback sur clé PEM: {e}")
            self._jwk_client = None
            self._jwks_available = False
        
        # Tentative 2: Clé PEM statique (fallback)
        await self._refresh_pem_key()
        if self._public_key:
            logger.info("✅ Authentification Hub initialisée (clé PEM)")
        else:
            logger.error("❌ Impossible d'initialiser l'authentification Hub")
    
    async def _refresh_pem_key(self) -> bool:
        """
        Rafraîchit la clé PEM depuis le Hub.
        
        Returns:
            True si la clé a été récupérée, False sinon
        """
        try:
            self._public_key = await hub_client.fetch_public_key()
            if self._public_key:
                self._public_key_fetched_at = datetime.now()
                logger.info("✅ Clé PEM récupérée (fallback)")
                return True
        except Exception as e:
            logger.error(f"❌ Erreur récupération clé PEM: {e}")
        return False
    
    def _is_pem_cache_valid(self) -> bool:
        """Vérifie si le cache PEM est encore valide."""
        if not self._public_key or not self._public_key_fetched_at:
            return False
        elapsed = (datetime.now() - self._public_key_fetched_at).total_seconds()
        return elapsed < PEM_CACHE_TTL_SECONDS
    
    def _decode_with_jwks(self, token: str) -> dict:
        """
        Décode le token avec JWKS.
        
        Raises:
            Exception si JWKS indisponible ou erreur de décodage
        """
        signing_key = self._jwk_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_exp": True}
        )
    
    def _decode_with_pem(self, token: str) -> dict:
        """
        Décode le token avec la clé PEM.
        
        Raises:
            Exception si la clé PEM n'est pas disponible
        """
        if not self._public_key:
            raise ValueError("Clé PEM non disponible")
        return jwt.decode(
            token,
            self._public_key,
            algorithms=["RS256"],
            options={"verify_exp": True}
        )
    
    def decode_token(self, token: str) -> TokenPayload:
        """
        Décode et valide un token JWT.
        
        Stratégie de validation avec fallback automatique :
        1. Essaie JWKS (recommandé, cache 1h)
        2. Si JWKS échoue → fallback automatique sur PEM
        3. Le fallback PEM est aussi caché 1h
        
        Args:
            token: Token JWT à valider
            
        Returns:
            TokenPayload avec les informations du token
            
        Raises:
            HTTPException: Si le token est invalide ou expiré
        """
        payload = None
        
        try:
            # Stratégie 1: JWKS (recommandé) avec fallback automatique sur PEM
            if self._jwk_client and self._jwks_available:
                try:
                    payload = self._decode_with_jwks(token)
                except Exception as jwks_error:
                    # JWKS a échoué en runtime → fallback automatique sur PEM
                    logger.warning(f"⚠️ JWKS indisponible en runtime, fallback PEM: {jwks_error}")
                    self._jwks_available = False
                    
                    # Rafraîchir la clé PEM si nécessaire (synchrone impossible ici)
                    # On utilise la clé PEM en cache si disponible
                    if self._public_key:
                        payload = self._decode_with_pem(token)
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Service d'authentification temporairement indisponible (JWKS down, pas de PEM en cache)"
                        )
            
            # Stratégie 2: PEM uniquement (fallback ou mode dégradé)
            elif self._public_key:
                payload = self._decode_with_pem(token)
            
            else:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service d'authentification non disponible"
                )
            
            return TokenPayload(
                sub=payload.get("sub", ""),
                roles=payload.get("roles", []),
                apps=payload.get("apps", {}),
                token_type=payload.get("type", payload.get("token_type", "user")),
                exp=payload.get("exp", 0),
                iat=payload.get("iat", 0),
                jti=payload.get("jti", ""),
            )
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expiré",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token invalide: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur inattendue lors du décodage du token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur interne lors de la validation du token"
            )
    
    async def try_restore_jwks(self) -> bool:
        """
        Tente de restaurer la connexion JWKS après un fallback PEM.
        À appeler périodiquement (ex: via un background task).
        
        Returns:
            True si JWKS est de nouveau disponible
        """
        if self._jwks_available:
            return True
        
        try:
            # Réinitialiser le client JWKS
            await self.initialize()
            if self._jwks_available:
                logger.info("✅ JWKS restauré après indisponibilité")
                return True
        except Exception as e:
            logger.debug(f"JWKS toujours indisponible: {e}")
        
        return False


# Instance singleton
hub_auth = HubAuth()

# Security scheme pour Swagger
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
) -> TokenPayload:
    """
    Dépendance FastAPI pour obtenir l'utilisateur courant.
    Requiert un token valide.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification requis",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return hub_auth.decode_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
) -> Optional[TokenPayload]:
    """
    Dépendance FastAPI pour obtenir l'utilisateur courant (optionnel).
    Retourne None si pas de token.
    """
    if not credentials:
        return None
    
    try:
        return hub_auth.decode_token(credentials.credentials)
    except HTTPException:
        return None


def require_role(min_role: str):
    """
    Décorateur/dépendance pour exiger un rôle minimum.
    
    Usage:
        @app.get("/admin")
        async def admin_endpoint(user: TokenPayload = Depends(require_role("admin"))):
            ...
    
    Args:
        min_role: Rôle minimum requis ("viewer", "user", "manager", "admin")
    """
    min_level = ROLE_MAPPING.get(min_role, 0)
    settings = get_settings()
    
    async def role_checker(
        user: TokenPayload = Depends(get_current_user)
    ) -> TokenPayload:
        # Vérifier le rôle pour cette application uniquement
        # Note: Les rôles globaux du Hub ne sont pas pris en compte ici
        user_level = user.get_app_role_level(settings.APP_SLUG)
        
        if user_level < min_level:
            role_name = user.get_app_role(settings.APP_SLUG) or "aucun"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle insuffisant. Requis: {min_role}, Actuel: {role_name}"
            )
        
        return user
    
    return role_checker


def require_any_role(*roles: str):
    """
    Décorateur/dépendance pour exiger l'un des rôles spécifiés.
    
    Usage:
        @app.get("/special")
        async def special_endpoint(user: TokenPayload = Depends(require_any_role("admin", "manager"))):
            ...
    """
    settings = get_settings()
    
    async def role_checker(
        user: TokenPayload = Depends(get_current_user)
    ) -> TokenPayload:
        # Vérifier le rôle pour cette application uniquement
        # Note: Les rôles globaux du Hub ne sont pas pris en compte ici
        user_role = user.get_app_role(settings.APP_SLUG)
        
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle requis: {' ou '.join(roles)}. Actuel: {user_role or 'aucun'}"
            )
        
        return user
    
    return role_checker


def require_service_account():
    """
    Dépendance pour exiger un service account (M2M).
    Utilisé pour les endpoints inter-services.
    """
    async def service_checker(
        user: TokenPayload = Depends(get_current_user)
    ) -> TokenPayload:
        if not user.is_service_account():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès réservé aux service accounts"
            )
        return user
    
    return service_checker
