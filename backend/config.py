"""
Configuration de l'application avec auto-détection IP.
"""
import os
import socket
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional


def get_app_version() -> str:
    """Lit la version depuis le fichier VERSION à la racine du projet."""
    possible_paths = [
        Path(__file__).parent.parent / "VERSION",
        Path(__file__).parent / "VERSION",
        Path("/app/VERSION"),
    ]
    for path in possible_paths:
        if path.exists():
            return path.read_text().strip()
    return "0.0.0"


APP_VERSION = get_app_version()


def get_docker_host_ip() -> Optional[str]:
    """
    Récupère l'IP externe de l'hôte Docker depuis un conteneur.
    
    Dans Docker, on ne peut pas facilement obtenir l'IP externe de l'hôte.
    Cette fonction tente plusieurs méthodes :
    
    1. Variable d'environnement APP_HOST (la plus fiable)
    2. Connexion UDP vers l'extérieur (fonctionne si le conteneur a accès réseau)
    
    Note: host.docker.internal pointe vers la gateway Docker (172.x.x.x), 
    pas vers l'IP externe de l'hôte.
    
    Returns:
        IP externe de l'hôte ou None si non détectable
    """
    # Méthode 1 : Variable d'environnement explicite (la plus fiable)
    app_host = os.environ.get("APP_HOST")
    if app_host:
        return app_host
    
    # Méthode 2 : Utiliser HUB_HOST si on est sur le même serveur
    # (pas de APP_HOST = même serveur que le Hub)
    hub_host = os.environ.get("HUB_HOST")
    if hub_host:
        return hub_host
    
    # Méthode 3 : Connexion UDP vers l'extérieur
    # Dans Docker avec network mode bridge, cela retourne l'IP du conteneur
    # Mais avec host network, cela retourne l'IP de l'hôte
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            # Ne retourner que si ce n'est pas une IP Docker interne
            if not ip.startswith("172."):
                return ip
    except Exception:
        pass
    
    return None


def is_running_in_docker() -> bool:
    """Détecte si on tourne dans un conteneur Docker."""
    # Méthode 1 : Fichier .dockerenv
    if Path("/.dockerenv").exists():
        return True
    # Méthode 2 : cgroup contient "docker"
    try:
        with open("/proc/1/cgroup") as f:
            return "docker" in f.read()
    except FileNotFoundError:
        pass
    return False


def get_local_ip() -> str:
    """
    Détecte l'IP locale de la machine.
    
    - Si dans Docker : retourne l'IP de l'hôte Docker
    - Sinon : retourne l'IP de l'interface réseau principale
    """
    # Dans Docker, on veut l'IP de l'hôte, pas du conteneur
    if is_running_in_docker():
        docker_host = get_docker_host_ip()
        if docker_host:
            return docker_host
    
    # Détection classique via connexion UDP
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class Settings(BaseSettings):
    """Configuration de l'application."""
    
    # Identifiant unique de l'application (OBLIGATOIRE)
    APP_SLUG: str = "mon-app"
    APP_NAME: str = "Mon Application"
    APP_DESCRIPTION: str = "Template d'application avec authentification Hub"
    
    # Host de cette application (si différent du HUB - pour apps sur serveur distant)
    # Laisser vide si l'app est sur le même serveur que le HUB
    APP_HOST: Optional[str] = None
    
    # Ports HTTP
    API_PORT: int = 9045
    FRONTEND_PORT: int = 4250
    
    # HTTPS
    HTTPS_ENABLED: bool = False
    FRONTEND_HTTPS_PORT: Optional[int] = None
    
    # Hub - Auto-détecté si non spécifié
    HUB_HOST: Optional[str] = None
    HUB_INTERNAL_HOST: Optional[str] = None
    HUB_API_PORT: int = 8000
    HUB_FRONTEND_PORT: int = 80
    
    # Base de données PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "app_user"
    POSTGRES_PASSWORD: str = "app_password"
    POSTGRES_DB: str = "app_db"
    
    # M2M (Machine-to-Machine)
    IS_SHARED: bool = False
    
    # Storage / Uploads
    UPLOADS_DIR: str = "/app/uploads"
    
    # Environnement
    DEBUG: bool = False

    # Endpoints de demo/test — desactiver en production
    ENABLE_DEMO_ENDPOINTS: bool = False
    
    @field_validator(
        'APP_HOST',
        'HUB_HOST',
        'HUB_INTERNAL_HOST',
        'FRONTEND_HTTPS_PORT',
        mode='before'
    )
    @classmethod
    def empty_str_to_none(cls, v):
        """Convertit les chaînes vides en None pour les chaînes optionnelles."""
        if v == '':
            return None
        return v

    @field_validator('HUB_API_PORT', 'HUB_FRONTEND_PORT', mode='before')
    @classmethod
    def empty_port_to_default(cls, v, info):
        """Hub legacy : ces variables peuvent manquer du .env et arriver vides (subst docker compose)."""
        if v in ('', None):
            return {'HUB_API_PORT': 8000, 'HUB_FRONTEND_PORT': 80}[info.field_name]
        return v
    
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
    def hub_internal_host(self) -> str:
        """Host interne du Hub pour les appels backend."""
        return self.HUB_INTERNAL_HOST or self.hub_host
    
    @property
    def hub_api_url(self) -> str:
        """URL complète de l'API Hub (HTTP)."""
        return f"http://{self.hub_host}:{self.HUB_API_PORT}"

    @property
    def hub_api_internal_url(self) -> str:
        """URL interne de l'API Hub pour les appels backend."""
        return f"http://{self.hub_internal_host}:{self.HUB_API_PORT}"
    
    @property
    def hub_frontend_url(self) -> str:
        """URL complète du frontend Hub (HTTP)."""
        return f"http://{self.hub_host}:{self.HUB_FRONTEND_PORT}"
    
    @property
    def app_host(self) -> str:
        """
        Host de cette application (auto-détecté si non spécifié).
        
        - Si APP_HOST est défini : utilise APP_HOST (configuration manuelle)
        - Sinon : auto-détecte l'IP locale de la machine
        
        L'auto-détection fonctionne en créant une connexion UDP vers 8.8.8.8
        pour déterminer l'interface réseau utilisée par défaut.
        """
        return self.APP_HOST or self.local_ip
    
    @property
    def is_remote_app(self) -> bool:
        """
        True si cette application est sur un serveur distant du Hub.
        
        Détecté automatiquement en comparant l'IP de l'app avec celle du Hub.
        """
        return self.app_host != self.hub_host
    
    @property
    def api_url(self) -> str:
        """URL de l'API de cette application (HTTP)."""
        return f"http://{self.app_host}:{self.API_PORT}"
    
    @property
    def frontend_url(self) -> str:
        """URL du frontend de cette application (HTTP)."""
        return f"http://{self.app_host}:{self.FRONTEND_PORT}"
    
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
