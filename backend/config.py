"""
Configuration de l'application avec auto-détection IP.
"""
import os
import socket
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional, Union


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
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
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
    
    # Host de cette application (si différent du HUB - pour apps sur serveur distant)
    # Laisser vide si l'app est sur le même serveur que le HUB
    APP_HOST: Optional[str] = None
    
    # Ports HTTP
    API_PORT: int = 9045
    FRONTEND_PORT: int = 4250
    
    # Ports HTTPS (optionnels - si définis, seront utilisés en priorité)
    API_HTTPS_PORT: Optional[int] = None  # Port HTTPS de l'API backend
    FRONTEND_HTTPS_PORT: Optional[int] = None  # Port HTTPS du frontend
    
    # Hub - Auto-détecté si non spécifié
    HUB_HOST: Optional[str] = None
    HUB_API_PORT: int = 8000
    HUB_FRONTEND_PORT: int = 80
    
    # === HTTPS / SSL ===
    HUB_HTTPS_ENABLED: bool = False
    HUB_HTTPS_PORT: int = 443
    HUB_CA_CERT_PATH: Optional[str] = None
    
    # Certificats SSL de cette application (si API_HTTPS_PORT est défini)
    APP_SSL_CERT_PATH: Optional[str] = None
    APP_SSL_KEY_PATH: Optional[str] = None
    
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
    
    # Validateurs pour gérer les chaînes vides comme None
    @field_validator('API_HTTPS_PORT', 'FRONTEND_HTTPS_PORT', mode='before')
    @classmethod
    def empty_str_to_none_int(cls, v):
        """Convertit les chaînes vides en None pour les ports optionnels."""
        if v == '' or v is None:
            return None
        return int(v)
    
    @field_validator('APP_HOST', 'HUB_HOST', 'HUB_CA_CERT_PATH', 'APP_SSL_CERT_PATH', 'APP_SSL_KEY_PATH', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        """Convertit les chaînes vides en None pour les chaînes optionnelles."""
        if v == '':
            return None
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
    def hub_api_url(self) -> str:
        """URL complète de l'API Hub (HTTP ou HTTPS)."""
        if self.HUB_HTTPS_ENABLED:
            port = f":{self.HUB_HTTPS_PORT}" if self.HUB_HTTPS_PORT != 443 else ""
            return f"https://{self.hub_host}{port}"
        return f"http://{self.hub_host}:{self.HUB_API_PORT}"
    
    @property
    def hub_frontend_url(self) -> str:
        """URL complète du frontend Hub (HTTP ou HTTPS)."""
        if self.HUB_HTTPS_ENABLED:
            port = f":{self.HUB_HTTPS_PORT}" if self.HUB_HTTPS_PORT != 443 else ""
            return f"https://{self.hub_host}{port}"
        return f"http://{self.hub_host}:{self.HUB_FRONTEND_PORT}"
    
    @property
    def hub_ssl_verify(self) -> Union[str, bool]:
        """
        Certificat CA pour vérifier le Hub en HTTPS.
        
        Retourne:
        - Chemin du CA si HTTPS activé et CA configuré et présent
        - True si HTTP (pas de vérification SSL nécessaire)
        
        Raises:
            RuntimeError: Si HTTPS est activé mais le certificat CA n'est pas disponible.
                         La communication non certifiée n'est PAS autorisée.
        
        Note: Le certificat est fourni dynamiquement par le Hub.
        Utiliser wait_for_hub_certificate() au démarrage si HTTPS est activé.
        """
        if self.HUB_HTTPS_ENABLED:
            if self.HUB_CA_CERT_PATH:
                ca_path = Path(self.HUB_CA_CERT_PATH)
                if ca_path.exists():
                    return str(ca_path)
            # HTTPS sans CA = REFUSER la communication (sécurité obligatoire)
            raise RuntimeError(
                "❌ Communication HTTPS impossible : certificat CA du Hub non disponible. "
                "La communication non certifiée par le Hub n'est pas autorisée. "
                f"Vérifiez que HUB_CA_CERT_PATH={self.HUB_CA_CERT_PATH} existe."
            )
        return True  # HTTP = pas de SSL
    
    def is_hub_certificate_available(self) -> bool:
        """Vérifie si le certificat CA du Hub est disponible."""
        if not self.HUB_HTTPS_ENABLED:
            return True  # Pas besoin de certificat en HTTP
        if not self.HUB_CA_CERT_PATH:
            return False
        return Path(self.HUB_CA_CERT_PATH).exists()
    
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
        """URL de l'API de cette application (HTTPS si configuré, sinon HTTP)."""
        if self.API_HTTPS_PORT:
            return f"https://{self.app_host}:{self.API_HTTPS_PORT}"
        return f"http://{self.app_host}:{self.API_PORT}"
    
    @property
    def frontend_url(self) -> str:
        """URL du frontend de cette application (HTTPS si configuré, sinon HTTP)."""
        if self.FRONTEND_HTTPS_PORT:
            return f"https://{self.app_host}:{self.FRONTEND_HTTPS_PORT}"
        return f"http://{self.app_host}:{self.FRONTEND_PORT}"
    
    @property
    def is_api_https_enabled(self) -> bool:
        """Indique si l'API utilise HTTPS."""
        return self.API_HTTPS_PORT is not None
    
    @property
    def is_frontend_https_enabled(self) -> bool:
        """Indique si le frontend utilise HTTPS."""
        return self.FRONTEND_HTTPS_PORT is not None
    
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
