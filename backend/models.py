"""
Modèles SQLAlchemy pour l'application.
Exemple de modèle Item pour démonstration.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<UserPreference(username='{self.username}')>"
