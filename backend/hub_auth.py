"""
Module d'authentification Hub avec validation JWT et gestion des rôles.
"""
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Callable
from functools import wraps
from dataclasses import dataclass
from enum import IntEnum
import logging

from config import get_settings
from hub_client import hub_client

logger = logging.getLogger(__name__)


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
        return self.token_type in ("service", "service_account") or "service_account" in self.roles


class HubAuth:
    """
    Gestion de l'authentification via le Hub.
    Valide les tokens JWT avec la clé publique JWKS.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._jwk_client: Optional[PyJWKClient] = None
        self._public_key: Optional[str] = None
    
    async def initialize(self):
        """Initialise le client JWKS."""
        try:
            jwks_url = f"{self.settings.hub_api_url}/api/auth/.well-known/jwks.json"
            self._jwk_client = PyJWKClient(jwks_url)
            logger.info(f"✅ Client JWKS initialisé: {jwks_url}")
        except Exception as e:
            logger.warning(f"⚠️ Impossible d'initialiser JWKS, fallback sur clé PEM: {e}")
            # Fallback sur la clé PEM
            self._public_key = await hub_client.fetch_public_key()
    
    def decode_token(self, token: str) -> TokenPayload:
        """
        Décode et valide un token JWT.
        
        Args:
            token: Token JWT à valider
            
        Returns:
            TokenPayload avec les informations du token
            
        Raises:
            HTTPException: Si le token est invalide ou expiré
        """
        try:
            if self._jwk_client:
                # Validation avec JWKS (recommandé)
                signing_key = self._jwk_client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    options={"verify_exp": True}
                )
            elif self._public_key:
                # Fallback avec clé PEM
                payload = jwt.decode(
                    token,
                    self._public_key,
                    algorithms=["RS256"],
                    options={"verify_exp": True}
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service d'authentification non disponible"
                )
            
            return TokenPayload(
                sub=payload.get("sub", ""),
                roles=payload.get("roles", []),
                apps=payload.get("apps", {}),
                token_type=payload.get("type", "user"),
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
        # Vérifier le rôle pour cette application
        user_level = user.get_app_role_level(settings.APP_SLUG)
        
        # Les admins globaux ont tous les droits
        if user.has_global_role("admin"):
            return user
        
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
        user_role = user.get_app_role(settings.APP_SLUG)
        
        # Les admins globaux ont tous les droits
        if user.has_global_role("admin"):
            return user
        
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
