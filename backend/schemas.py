"""
Schémas Pydantic pour la validation des données.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


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
    per_page: int = 20
    pages: int = 1


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
    per_page: Optional[int] = Field(None, description="Nombre par page (si paginé)")
    pages: Optional[int] = Field(None, description="Nombre total de pages (si paginé)")


# ============ Uploaded Files ============

class UploadedFileBase(BaseModel):
    """Base pour les fichiers uploadés."""
    filename: str = Field(..., max_length=255, description="Nom du fichier")
    category: str = Field("general", max_length=100, description="Catégorie de classement")
    description: Optional[str] = Field(None, description="Description du fichier")


class UploadedFileCreate(UploadedFileBase):
    """Création d'un fichier uploadé (sans le fichier lui-même)."""
    entity_type: Optional[str] = Field(None, max_length=50, description="Type d'entité liée")
    entity_id: Optional[int] = Field(None, description="ID de l'entité liée")


class UploadedFileResponse(UploadedFileBase):
    """Réponse avec un fichier uploadé."""
    id: int
    original_filename: str
    relative_path: str
    size: int
    mime_type: str
    hash: str
    owner: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============ Backup / Restore ============

class BackupEstimate(BaseModel):
    """Estimation de la taille et durée d'un backup."""
    total_items: int = Field(..., description="Nombre total d'items")
    total_preferences: int = Field(..., description="Nombre de préférences utilisateur")
    total_files: int = Field(..., description="Nombre de fichiers uploadés")
    total_test_data: int = Field(0, description="Nombre de données de test")
    
    database_size_bytes: int = Field(..., description="Taille estimée des données DB")
    files_size_bytes: int = Field(..., description="Taille totale des fichiers")
    total_size_bytes: int = Field(..., description="Taille totale estimée du backup")
    total_size_human: str = Field(..., description="Taille lisible (ex: 15.3 MB)")
    
    estimated_duration_seconds: float = Field(..., description="Durée estimée en secondes")
    estimated_duration_human: str = Field(..., description="Durée lisible (ex: 2 min 30 sec)")
    
    files_by_category: dict = Field(default_factory=dict, description="Fichiers par catégorie")
    files_by_mime_type: dict = Field(default_factory=dict, description="Fichiers par type MIME")
    
    warning: Optional[str] = Field(None, description="Avertissement si backup volumineux")


class BackupMetadata(BaseModel):
    """Métadonnées d'un backup."""
    backup_id: str = Field(..., description="Identifiant unique du backup")
    app_slug: str = Field(..., description="Slug de l'application")
    app_version: str = Field(..., description="Version de l'application")
    created_at: str = Field(..., description="Date de création ISO")
    created_by: str = Field(..., description="Utilisateur ayant créé le backup")
    
    total_items: int = Field(..., description="Nombre d'items")
    total_preferences: int = Field(..., description="Nombre de préférences")
    total_files: int = Field(..., description="Nombre de fichiers")
    total_test_data: int = Field(0, description="Nombre de données de test")
    total_size_bytes: int = Field(..., description="Taille totale")
    total_size_human: str = Field(..., description="Taille lisible")
    
    includes_files: bool = Field(True, description="Fichiers inclus dans le backup")
    checksum: str = Field(..., description="Checksum du backup pour vérification")


class BackupResponse(BaseModel):
    """Réponse après création d'un backup."""
    success: bool
    message: str
    metadata: BackupMetadata
    download_url: Optional[str] = Field(None, description="URL de téléchargement")


class RestoreRequest(BaseModel):
    """Requête de restauration."""
    backup_id: Optional[str] = Field(None, description="ID du backup à restaurer (si stocké)")
    clear_existing: bool = Field(False, description="Supprimer les données existantes avant restore")
    restore_items: bool = Field(True, description="Restaurer les items")
    restore_preferences: bool = Field(True, description="Restaurer les préférences")
    restore_files: bool = Field(True, description="Restaurer les fichiers")


class RestoreResponse(BaseModel):
    """Réponse après restauration."""
    success: bool
    message: str
    
    items_restored: int = Field(0, description="Nombre d'items restaurés")
    preferences_restored: int = Field(0, description="Nombre de préférences restaurées")
    files_restored: int = Field(0, description="Nombre de fichiers restaurés")
    
    items_skipped: int = Field(0, description="Items ignorés (déjà existants)")
    files_skipped: int = Field(0, description="Fichiers ignorés")
    
    errors: list[str] = Field(default_factory=list, description="Erreurs rencontrées")
    warnings: list[str] = Field(default_factory=list, description="Avertissements")


class SyncToHubRequest(BaseModel):
    """Requête de synchronisation vers le Hub."""
    description: Optional[str] = Field(None, description="Description du backup")
    tags: list[str] = Field(default_factory=list, description="Tags pour le backup")


class SyncFromHubRequest(BaseModel):
    """Requête de synchronisation depuis le Hub."""
    backup_id: Optional[str] = Field(None, description="ID spécifique (sinon dernier)")
    clear_existing: bool = Field(False, description="Supprimer données existantes")


# ============ Test Data (pour test backup) ============

class TestDataBase(BaseModel):
    """Base pour les données de test."""
    name: str = Field(..., min_length=1, max_length=255, description="Nom de la donnée")
    value: Optional[str] = Field(None, max_length=500, description="Valeur de la donnée")
    category: str = Field("general", max_length=100, description="Catégorie")


class TestDataCreate(TestDataBase):
    """Création d'une donnée de test."""
    pass


class TestDataUpdate(BaseModel):
    """Mise à jour d'une donnée de test (tous les champs optionnels)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    value: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=100)


class TestDataResponse(TestDataBase):
    """Réponse avec une donnée de test."""
    id: int
    last_modified_by: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TestDataListResponse(BaseModel):
    """Réponse avec liste de données de test."""
    items: list[TestDataResponse]
    total: int

