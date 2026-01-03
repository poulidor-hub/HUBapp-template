"""
Configuration de l'application avec auto-détection IP.
"""
import socket
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


def get_local_ip() -> str:
    """Détecte l'IP locale de la machine (pas localhost)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class Settings(BaseSettings):
    """Configuration de l'application."""
    
    # Identifiant unique de l'application (OBLIGATOIRE)
    APP_SLUG: str = "mon-app"
    APP_NAME: str = "Mon Application"
    APP_DESCRIPTION: str = "Template d'application avec authentification Hub"
    
    # Ports
    API_PORT: int = 18087
    FRONTEND_PORT: int = 4178
    
    # Hub - Auto-détecté si non spécifié
    HUB_HOST: Optional[str] = None
    HUB_API_PORT: int = 8000
    HUB_FRONTEND_PORT: int = 80
    
    # Base de données PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "app_user"
    POSTGRES_PASSWORD: str = "app_password"
    POSTGRES_DB: str = "app_db"
    
    # Environnement
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    @property
    def local_ip(self) -> str:
        """IP locale de la machine."""
        return get_local_ip()
    
    @property
    def hub_host(self) -> str:
        """Host du Hub (auto-détecté si non spécifié)."""
        return self.HUB_HOST or self.local_ip
    
    @property
    def hub_api_url(self) -> str:
        """URL complète de l'API Hub."""
        return f"http://{self.hub_host}:{self.HUB_API_PORT}"
    
    @property
    def hub_frontend_url(self) -> str:
        """URL complète du frontend Hub."""
        return f"http://{self.hub_host}:{self.HUB_FRONTEND_PORT}"
    
    @property
    def api_url(self) -> str:
        """URL de l'API de cette application."""
        return f"http://{self.local_ip}:{self.API_PORT}"
    
    @property
    def frontend_url(self) -> str:
        """URL du frontend de cette application."""
        return f"http://{self.local_ip}:{self.FRONTEND_PORT}"
    
    @property
    def database_url(self) -> str:
        """URL de connexion PostgreSQL."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @property
    def database_url_sync(self) -> str:
        """URL de connexion PostgreSQL synchrone (pour Alembic)."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


@lru_cache()
def get_settings() -> Settings:
    """Singleton pour la configuration."""
    return Settings()
