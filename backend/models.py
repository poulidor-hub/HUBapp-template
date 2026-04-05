"""
Modèles SQLAlchemy pour l'application.
Exemple de modèle Item pour démonstration.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, BigInteger, Index
from datetime import datetime, timezone

from database import Base


class Item(Base):
    """
    Modèle exemple pour démonstration.
    Représente un élément simple avec propriétaire.
    """
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Propriétaire (username du token)
    owner = Column(String(100), nullable=False, index=True)
    
    # Visibilité: public = visible par tous, sinon par owner + admins
    is_public = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('ix_item_owner_is_public', 'owner', 'is_public'),
    )
    
    def __repr__(self):
        return f"<Item(id={self.id}, title='{self.title}', owner='{self.owner}')>"


class UserPreference(Base):
    """
    Préférences utilisateur stockées localement.
    Le Hub ne gère pas les préférences, c'est à l'application de le faire.
    """
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    
    # Préférences UI
    theme = Column(String(20), default="system")  # light, dark, system
    language = Column(String(5), default="fr")
    items_per_page = Column(Integer, default=20)
    
    # Préférences notifications
    email_notifications = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<UserPreference(username='{self.username}')>"


class UploadedFile(Base):
    """
    Fichier uploadé dans l'application.
    Permet de tracker les fichiers pour le système de backup/restore.
    
    Les futures applications peuvent utiliser ce modèle pour :
    - Stocker des documents PDF, images, etc.
    - Associer des fichiers à d'autres entités (items, projets, etc.)
    - Inclure automatiquement tous les fichiers dans les backups
    """
    __tablename__ = "uploaded_files"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Identifiants et chemins
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    relative_path = Column(String(500), nullable=False, unique=True, index=True)
    
    # Métadonnées fichier
    size = Column(BigInteger, nullable=False)  # Taille en bytes
    mime_type = Column(String(100), nullable=False)
    hash = Column(String(64), nullable=False)  # SHA-256
    
    # Classification
    category = Column(String(100), default="general", index=True)
    description = Column(Text, nullable=True)
    
    # Propriétaire
    owner = Column(String(100), nullable=False, index=True)
    
    # Référence optionnelle à une entité (pour lier fichiers à items, etc.)
    # Les futures apps peuvent utiliser ces champs pour associer des fichiers
    entity_type = Column(String(50), nullable=True, index=True)  # ex: "item", "project"
    entity_id = Column(Integer, nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index('ix_uploaded_files_owner_category', 'owner', 'category'),
    )
    
    def __repr__(self):
        return f"<UploadedFile(id={self.id}, filename='{self.filename}', owner='{self.owner}')>"
    
    def to_backup_dict(self) -> dict:
        """Convertit en dict pour le backup (sans le contenu binaire)."""
        return {
            "id": self.id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "relative_path": self.relative_path,
            "size": self.size,
            "mime_type": self.mime_type,
            "hash": self.hash,
            "category": self.category,
            "description": self.description,
            "owner": self.owner,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class TestData(Base):
    """
    Données de test partagées pour tester le système de backup.
    Ces données sont modifiables par tous les utilisateurs authentifiés
    et visibles par tous (partagées).
    """
    __tablename__ = "test_data"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Données modifiables
    name = Column(String(255), nullable=False)
    value = Column(String(500), nullable=True)
    category = Column(String(100), default="general", index=True)
    
    # Metadata
    last_modified_by = Column(String(100), nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<TestData(id={self.id}, name='{self.name}', value='{self.value}')>"
    
    def to_backup_dict(self) -> dict:
        """Convertit en dict pour le backup."""
        return {
            "id": self.id,
            "name": self.name,
            "value": self.value,
            "category": self.category,
            "last_modified_by": self.last_modified_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

