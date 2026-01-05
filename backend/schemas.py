"""
Schémas Pydantic pour la validation des données.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ============ Items ============

class ItemBase(BaseModel):
    """Base pour les items."""
    title: str = Field(..., min_length=1, max_length=255, description="Titre de l'item")
    description: Optional[str] = Field(None, description="Description de l'item")
    is_public: bool = Field(False, description="Item visible par tous")


class ItemCreate(ItemBase):
    """Création d'un item."""
    pass


class ItemUpdate(BaseModel):
    """Mise à jour d'un item (tous les champs optionnels)."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_public: Optional[bool] = None


class ItemResponse(ItemBase):
    """Réponse avec un item."""
    id: int
    owner: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============ User Preferences ============

class UserPreferenceBase(BaseModel):
    """Base pour les préférences utilisateur."""
    theme: str = Field("system", pattern="^(light|dark|system)$")
    language: str = Field("fr", min_length=2, max_length=5)
    items_per_page: int = Field(20, ge=5, le=100)
    email_notifications: bool = True


class UserPreferenceUpdate(BaseModel):
    """Mise à jour des préférences."""
    theme: Optional[str] = Field(None, pattern="^(light|dark|system)$")
    language: Optional[str] = Field(None, min_length=2, max_length=5)
    items_per_page: Optional[int] = Field(None, ge=5, le=100)
    email_notifications: Optional[bool] = None


class UserPreferenceResponse(UserPreferenceBase):
    """Réponse avec les préférences."""
    username: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============ Auth / User ============

class UserInfo(BaseModel):
    """Informations utilisateur depuis le token."""
    username: str
    roles: list[str]
    app_role: Optional[str]
    is_service_account: bool


class TokenInfo(BaseModel):
    """Informations sur le token."""
    valid: bool
    username: Optional[str] = None
    app_role: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


# ============ Generic ============

class MessageResponse(BaseModel):
    """Réponse simple avec message."""
    message: str
    detail: Optional[str] = None


class PaginatedResponse(BaseModel):
    """Réponse paginée générique."""
    items: list
    total: int
    page: int


# ============ Services Discovery ============

class DiscoveredServiceResponse(BaseModel):
    """Service découvert via le Hub."""
    slug: str = Field(..., description="Identifiant unique du service")
    name: str = Field(..., description="Nom du service")
    description: Optional[str] = Field(None, description="Description du service")
    api_url: str = Field(..., description="URL de l'API du service")
    frontend_url: Optional[str] = Field(None, description="URL du frontend du service")
    version: Optional[str] = Field(None, description="Version du service")
    status: Optional[str] = Field(None, description="Statut du service (online, offline, degraded)")
    is_healthy: bool = Field(True, description="Le service est-il en bonne santé")


class DiscoveredServiceDetailResponse(DiscoveredServiceResponse):
    """Service découvert avec informations techniques (admin only)."""
    ip: Optional[str] = Field(None, description="Adresse IP du service")
    api_port: Optional[int] = Field(None, description="Port de l'API")
    frontend_port: Optional[int] = Field(None, description="Port du frontend")
    registered_at: Optional[str] = Field(None, description="Date d'enregistrement")
    last_seen: Optional[str] = Field(None, description="Dernière activité")
    is_shared: bool = Field(True, description="Service en mode partagé")


class ServiceDiscoveryResponse(BaseModel):
    """Réponse de découverte des services."""
    count: int = Field(..., description="Nombre de services découverts")
    services: list[DiscoveredServiceResponse] = Field(..., description="Liste des services")
    cached_at: Optional[str] = Field(None, description="Date de mise en cache")
    per_page: int
    pages: int
