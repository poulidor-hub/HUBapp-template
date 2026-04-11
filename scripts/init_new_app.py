#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'initialisation d'une nouvelle application à partir du template HUBapp.

Ce script transforme le template en une nouvelle application avec :
- Nouveau slug, nom et description
- Nouveaux ports API et Frontend
- Fichiers VERSION, CHANGELOG.md, README.md réinitialisés
- Frontend nettoyé des références au template
- Fichier .env généré automatiquement

Usage:
    python scripts/init_new_app.py              # Initialisation standard
    python scripts/init_new_app.py --clean      # + suppression du contenu de démo

Compatible Linux / Windows / macOS
"""

import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path

# Couleurs ANSI pour le terminal (désactivées sur Windows si pas supporté)
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Désactiver les couleurs sur Windows si nécessaire
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        # Désactiver les couleurs si pas supporté
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')


def print_header():
    """Affiche l'en-tête du script."""
    print(f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║  {Colors.BOLD}🚀 Initialisation d'une nouvelle application HUB{Colors.ENDC}{Colors.CYAN}               ║
║                                                                  ║
║  Ce script va transformer le template en une nouvelle app.       ║
║  Les fichiers suivants seront modifiés :                         ║
║    • .env.example → .env (généré)                                ║
║    • docker-compose.yml                                          ║
║    • backend/config.py                                           ║
║    • frontend/index.html, package.json, Header.jsx               ║
║    • VERSION, CHANGELOG.md, README.md                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝{Colors.ENDC}
""")


def get_project_root() -> Path:
    """Retourne le chemin racine du projet."""
    script_dir = Path(__file__).resolve().parent
    return script_dir.parent


def validate_slug(slug: str) -> bool:
    """Valide le format du slug (minuscules, chiffres, tirets)."""
    return bool(re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', slug)) and len(slug) >= 3


def validate_port(port_str: str) -> bool:
    """Valide un numéro de port."""
    try:
        port = int(port_str)
        return 1024 <= port <= 65535
    except ValueError:
        return False


def prompt_input(prompt: str, default: str = "", validator=None, error_msg: str = "") -> str:
    """Demande une saisie utilisateur avec validation optionnelle."""
    while True:
        if default:
            user_input = input(f"{Colors.CYAN}{prompt} [{default}]: {Colors.ENDC}").strip()
            if not user_input:
                user_input = default
        else:
            user_input = input(f"{Colors.CYAN}{prompt}: {Colors.ENDC}").strip()
        
        if validator is None or validator(user_input):
            return user_input
        else:
            print(f"{Colors.RED}✗ {error_msg}{Colors.ENDC}")


def collect_app_info() -> dict:
    """Collecte les informations de la nouvelle application."""
    print(f"\n{Colors.BOLD}📝 Configuration de votre nouvelle application{Colors.ENDC}\n")
    
    # APP_SLUG
    print(f"{Colors.YELLOW}Le slug est l'identifiant unique de l'application.")
    print(f"Format: minuscules, chiffres et tirets uniquement (ex: mon-app, gestion-stock){Colors.ENDC}")
    app_slug = prompt_input(
        "APP_SLUG (identifiant unique)",
        validator=validate_slug,
        error_msg="Le slug doit contenir au moins 3 caractères, commencer par une lettre, "
                  "et ne contenir que des minuscules, chiffres et tirets."
    )
    
    # APP_NAME
    print(f"\n{Colors.YELLOW}Le nom sera affiché dans l'interface et le Hub.{Colors.ENDC}")
    app_name = prompt_input(
        "APP_NAME (nom affiché)",
        default=app_slug.replace("-", " ").title()
    )
    
    # APP_DESCRIPTION
    print(f"\n{Colors.YELLOW}Description courte de l'application.{Colors.ENDC}")
    app_description = prompt_input(
        "APP_DESCRIPTION",
        default=f"Application {app_name}"
    )
    
    # Ports
    print(f"\n{Colors.BOLD}🔌 Configuration des ports{Colors.ENDC}")
    print(f"{Colors.YELLOW}Choisissez des ports non utilisés sur votre système.{Colors.ENDC}\n")
    
    api_port = prompt_input(
        "API_PORT (port backend)",
        default="9045",
        validator=validate_port,
        error_msg="Le port doit être un nombre entre 1024 et 65535."
    )
    
    frontend_port = prompt_input(
        "FRONTEND_PORT (port frontend)",
        default="4250",
        validator=validate_port,
        error_msg="Le port doit être un nombre entre 1024 et 65535."
    )
    
    # Hub configuration
    print(f"\n{Colors.BOLD}🔗 Configuration du Hub{Colors.ENDC}")
    print(f"{Colors.YELLOW}Adresse du serveur Hub auquel cette app se connectera.{Colors.ENDC}\n")
    
    hub_host = prompt_input(
        "HUB_HOST (IP/hostname du Hub)",
        default="192.0.2.11"
    )
    
    hub_api_port = prompt_input(
        "HUB_API_PORT",
        default="8000",
        validator=validate_port,
        error_msg="Le port doit être un nombre entre 1024 et 65535."
    )
    
    hub_frontend_port = prompt_input(
        "HUB_FRONTEND_PORT",
        default="80",
        validator=lambda x: validate_port(x) or x == "80",
        error_msg="Le port doit être un nombre entre 1024 et 65535."
    )
    
    return {
        "APP_SLUG": app_slug,
        "APP_NAME": app_name,
        "APP_DESCRIPTION": app_description,
        "API_PORT": api_port,
        "FRONTEND_PORT": frontend_port,
        "HUB_HOST": hub_host,
        "HUB_API_PORT": hub_api_port,
        "HUB_FRONTEND_PORT": hub_frontend_port,
    }


def confirm_settings(config: dict) -> bool:
    """Affiche un récapitulatif et demande confirmation."""
    print(f"\n{Colors.BOLD}📋 Récapitulatif de la configuration{Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 50}{Colors.ENDC}")
    
    print(f"  APP_SLUG:         {Colors.GREEN}{config['APP_SLUG']}{Colors.ENDC}")
    print(f"  APP_NAME:         {Colors.GREEN}{config['APP_NAME']}{Colors.ENDC}")
    print(f"  APP_DESCRIPTION:  {Colors.GREEN}{config['APP_DESCRIPTION']}{Colors.ENDC}")
    print(f"  API_PORT:         {Colors.GREEN}{config['API_PORT']}{Colors.ENDC}")
    print(f"  FRONTEND_PORT:    {Colors.GREEN}{config['FRONTEND_PORT']}{Colors.ENDC}")
    print(f"  HUB_HOST:         {Colors.GREEN}{config['HUB_HOST']}{Colors.ENDC}")
    print(f"  HUB_API_PORT:     {Colors.GREEN}{config['HUB_API_PORT']}{Colors.ENDC}")
    print(f"  HUB_FRONTEND_PORT:{Colors.GREEN}{config['HUB_FRONTEND_PORT']}{Colors.ENDC}")
    
    print(f"{Colors.CYAN}{'─' * 50}{Colors.ENDC}")
    
    response = input(f"\n{Colors.YELLOW}Confirmer ces paramètres ? (O/n): {Colors.ENDC}").strip().lower()
    return response in ('', 'o', 'oui', 'y', 'yes')


def update_file(filepath: Path, replacements: list, description: str) -> bool:
    """
    Met à jour un fichier avec une liste de remplacements.
    
    Args:
        filepath: Chemin du fichier
        replacements: Liste de tuples (pattern, replacement) ou (old_text, new_text)
        description: Description de l'opération
    
    Returns:
        True si succès, False sinon
    """
    try:
        if not filepath.exists():
            print(f"  {Colors.YELLOW}⚠ Fichier non trouvé: {filepath.name}{Colors.ENDC}")
            return False
        
        content = filepath.read_text(encoding='utf-8')
        original_content = content
        
        for old, new in replacements:
            content = content.replace(old, new)
        
        if content != original_content:
            filepath.write_text(content, encoding='utf-8')
            print(f"  {Colors.GREEN}✓ {description}: {filepath.name}{Colors.ENDC}")
            return True
        else:
            print(f"  {Colors.YELLOW}○ Pas de changement: {filepath.name}{Colors.ENDC}")
            return True
            
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur {filepath.name}: {e}{Colors.ENDC}")
        return False


def create_env_file(root: Path, config: dict) -> bool:
    """Crée le fichier .env à partir de la configuration."""
    env_content = f"""# ============================================================
# Configuration de l'application {config['APP_NAME']}
# ============================================================
# Généré automatiquement le {datetime.now().strftime('%d/%m/%Y à %H:%M')}

# === IDENTIFICATION APPLICATION ===
APP_SLUG={config['APP_SLUG']}
APP_NAME={config['APP_NAME']}
APP_DESCRIPTION={config['APP_DESCRIPTION']}

# === VERSION ===
# Source de vérité: fichier VERSION
APP_VERSION=0.0.1

# === PORTS ===
API_PORT={config['API_PORT']}
FRONTEND_PORT={config['FRONTEND_PORT']}
FRONTEND_HTTPS_PORT={int(config['FRONTEND_PORT']) + 1}

# === HOST DE CETTE APPLICATION ===
# Laisser vide si l'app est sur le même serveur que le Hub
APP_HOST=

# === HUB ===
HUB_HOST={config['HUB_HOST']}
HUB_API_PORT={config['HUB_API_PORT']}
HUB_FRONTEND_PORT={config['HUB_FRONTEND_PORT']}

# === BASE DE DONNÉES ===
POSTGRES_HOST={config['APP_SLUG']}-postgres
POSTGRES_PORT=5432
POSTGRES_USER=app_user
POSTGRES_PASSWORD=app_password_secure_123
POSTGRES_DB=app_db

# === ENVIRONNEMENT ===
DEBUG=false

# === M2M (MACHINE-TO-MACHINE) ===
IS_SHARED=false
"""
    
    try:
        env_path = root / '.env'
        env_path.write_text(env_content, encoding='utf-8')
        print(f"  {Colors.GREEN}✓ Fichier .env créé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur création .env: {e}{Colors.ENDC}")
        return False


def update_env_example(root: Path, config: dict) -> bool:
    """Met à jour .env.example avec les nouvelles valeurs par défaut."""
    filepath = root / '.env.example'

    try:
        content = filepath.read_text(encoding='utf-8')

        replacements = [
            ('APP_SLUG=mon-app', f'APP_SLUG={config["APP_SLUG"]}'),
            ('APP_NAME=Mon Application', f'APP_NAME={config["APP_NAME"]}'),
            ('APP_DESCRIPTION=Application template avec authentification Hub', 
             f'APP_DESCRIPTION={config["APP_DESCRIPTION"]}'),
            ('API_PORT=9045', f'API_PORT={config["API_PORT"]}'),
            ('FRONTEND_PORT=4250', f'FRONTEND_PORT={config["FRONTEND_PORT"]}'),
            ('HUB_HOST=192.0.2.11', f'HUB_HOST={config["HUB_HOST"]}'),
            ('HUB_API_PORT=8000', f'HUB_API_PORT={config["HUB_API_PORT"]}'),
            ('HUB_FRONTEND_PORT=80', f'HUB_FRONTEND_PORT={config["HUB_FRONTEND_PORT"]}'),
            ('POSTGRES_HOST=mon-app-postgres', f'POSTGRES_HOST={config["APP_SLUG"]}-postgres'),
            ('# Configuration de l\'application Template Hub',
             f'# Configuration de l\'application {config["APP_NAME"]}'),
        ]

        for old, new in replacements:
            content = content.replace(old, new)

        if re.search(r'^APP_VERSION=.*$', content, flags=re.MULTILINE):
            content = re.sub(r'^APP_VERSION=.*$', 'APP_VERSION=0.0.1', content, flags=re.MULTILINE)
        else:
            content = content.replace(
                f'APP_DESCRIPTION={config["APP_DESCRIPTION"]}',
                f'APP_DESCRIPTION={config["APP_DESCRIPTION"]}\n\n# === VERSION ===\n# Source de vérité: fichier VERSION\nAPP_VERSION=0.0.1'
            )

        filepath.write_text(content, encoding='utf-8')
        print(f"  {Colors.GREEN}✓ Valeurs par défaut mises à jour: {filepath.name}{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur {filepath.name}: {e}{Colors.ENDC}")
        return False


def update_docker_compose(root: Path, config: dict) -> bool:
    """Met à jour docker-compose.yml."""
    filepath = root / 'docker-compose.yml'
    
    replacements = [
        ('# Docker Compose - Application Template Hub',
         f'# Docker Compose - {config["APP_NAME"]}'),
        ('${APP_SLUG:-mon-app}', f'${{APP_SLUG:-{config["APP_SLUG"]}}}'),
        ('${API_PORT:-9045}', f'${{API_PORT:-{config["API_PORT"]}}}'),
        ('${FRONTEND_PORT:-4250}', f'${{FRONTEND_PORT:-{config["FRONTEND_PORT"]}}}'),
        ('${HUB_API_PORT:-8000}', f'${{HUB_API_PORT:-{config["HUB_API_PORT"]}}}'),
        ('${HUB_FRONTEND_PORT:-80}', f'${{HUB_FRONTEND_PORT:-{config["HUB_FRONTEND_PORT"]}}}'),
    ]
    
    return update_file(filepath, replacements, "Configuration Docker mise à jour")


def update_backend_config(root: Path, config: dict) -> bool:
    """Met à jour backend/config.py."""
    filepath = root / 'backend' / 'config.py'
    
    replacements = [
        ('APP_SLUG: str = "mon-app"', f'APP_SLUG: str = "{config["APP_SLUG"]}"'),
        ('APP_NAME: str = "Mon Application"', f'APP_NAME: str = "{config["APP_NAME"]}"'),
        ('APP_DESCRIPTION: str = "Template d\'application avec authentification Hub"',
         f'APP_DESCRIPTION: str = "{config["APP_DESCRIPTION"]}"'),
        ('API_PORT: int = 9045', f'API_PORT: int = {config["API_PORT"]}'),
        ('FRONTEND_PORT: int = 4250', f'FRONTEND_PORT: int = {config["FRONTEND_PORT"]}'),
        ('HUB_API_PORT: int = 8000', f'HUB_API_PORT: int = {config["HUB_API_PORT"]}'),
        ('HUB_FRONTEND_PORT: int = 80', f'HUB_FRONTEND_PORT: int = {config["HUB_FRONTEND_PORT"]}'),
    ]
    
    return update_file(filepath, replacements, "Config backend mise à jour")


def update_dockerfile_frontend(root: Path, config: dict) -> bool:
    """Met à jour Dockerfile.frontend."""
    filepath = root / 'Dockerfile.frontend'
    
    replacements = [
        ('ARG VITE_API_PORT=9045', f'ARG VITE_API_PORT={config["API_PORT"]}'),
        ('ARG VITE_HUB_API_PORT=8000', f'ARG VITE_HUB_API_PORT={config["HUB_API_PORT"]}'),
        ('ARG VITE_HUB_FRONTEND_PORT=80', f'ARG VITE_HUB_FRONTEND_PORT={config["HUB_FRONTEND_PORT"]}'),
        ('ARG VITE_APP_SLUG=mon-app', f'ARG VITE_APP_SLUG={config["APP_SLUG"]}'),
    ]
    
    return update_file(filepath, replacements, "Dockerfile frontend mis à jour")


def update_frontend_index(root: Path, config: dict) -> bool:
    """Met à jour frontend/index.html."""
    filepath = root / 'frontend' / 'index.html'
    
    replacements = [
        ('<title>Template App - Hub Auth</title>', 
         f'<title>{config["APP_NAME"]}</title>'),
    ]
    
    return update_file(filepath, replacements, "Titre HTML mis à jour")


def update_frontend_header(root: Path, config: dict) -> bool:
    """Met à jour frontend/src/components/Header.jsx."""
    filepath = root / 'frontend' / 'src' / 'components' / 'Header.jsx'
    
    replacements = [
        ('<h1>🔐 Template App - Hub Auth</h1>', 
         f'<h1>🔐 {config["APP_NAME"]}</h1>'),
    ]
    
    return update_file(filepath, replacements, "Header frontend mis à jour")


def update_frontend_package_json(root: Path, config: dict) -> bool:
    """Met à jour frontend/package.json."""
    filepath = root / 'frontend' / 'package.json'
    
    try:
        content = json.loads(filepath.read_text(encoding='utf-8'))
        content['name'] = f'{config["APP_SLUG"]}-frontend'
        content['version'] = '0.0.1'
        
        filepath.write_text(json.dumps(content, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f"  {Colors.GREEN}✓ package.json mis à jour{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur package.json: {e}{Colors.ENDC}")
        return False


def update_frontend_config_js(root: Path, config: dict) -> bool:
    """Met à jour frontend/src/config.js avec le nouveau appSlug."""
    filepath = root / 'frontend' / 'src' / 'config.js'
    
    replacements = [
        ("APP_SLUG: import.meta.env.VITE_APP_SLUG || 'mon-app'",
         f"APP_SLUG: import.meta.env.VITE_APP_SLUG || '{config['APP_SLUG']}'"),
    ]
    
    return update_file(filepath, replacements, "Config frontend (src) mise à jour")


def update_test_fixtures(root: Path, config: dict) -> bool:
    """Met à jour les fixtures de test avec le nouveau appSlug."""
    success = True
    
    # conftest.py
    conftest_path = root / 'backend' / 'tests' / 'conftest.py'
    if conftest_path.exists():
        try:
            content = conftest_path.read_text(encoding='utf-8')
            content = content.replace(
                '{"mon-app": app_role}',
                '{' + f'"{config["APP_SLUG"]}": app_role' + '}'
            )
            content = content.replace(
                '{"mon-app": "service"}',
                '{' + f'"{config["APP_SLUG"]}": "service"' + '}'
            )
            conftest_path.write_text(content, encoding='utf-8')
            print(f"  {Colors.GREEN}✓ conftest.py mis à jour{Colors.ENDC}")
        except Exception as e:
            print(f"  {Colors.RED}✗ Erreur conftest.py: {e}{Colors.ENDC}")
            success = False
    
    # test_m2m.py
    test_m2m_path = root / 'backend' / 'tests' / 'test_m2m.py'
    if test_m2m_path.exists():
        try:
            content = test_m2m_path.read_text(encoding='utf-8')
            content = content.replace('"mon-app"', f'"{config["APP_SLUG"]}"')
            test_m2m_path.write_text(content, encoding='utf-8')
            print(f"  {Colors.GREEN}✓ test_m2m.py mis à jour{Colors.ENDC}")
        except Exception as e:
            print(f"  {Colors.RED}✗ Erreur test_m2m.py: {e}{Colors.ENDC}")
            success = False
    
    return success


def cleanup_obsolete_files(root: Path) -> bool:
    """Supprime les fichiers obsolètes du template."""
    success = True
    
    # frontend/config.js - vestige de la version vanilla JS, jamais importé
    obsolete_config = root / 'frontend' / 'config.js'
    if obsolete_config.exists():
        try:
            obsolete_config.unlink()
            print(f"  {Colors.GREEN}✓ Supprimé frontend/config.js (vestige inutilisé){Colors.ENDC}")
        except Exception as e:
            print(f"  {Colors.RED}✗ Erreur suppression frontend/config.js: {e}{Colors.ENDC}")
            success = False
    
    # Supprimer les __pycache__
    import shutil
    for pycache in root.rglob('__pycache__'):
        try:
            shutil.rmtree(pycache)
        except Exception:
            pass
    
    return success


# ============================================================
# NETTOYAGE DU CONTENU DE DÉMO (--clean)
# ============================================================

def clean_demo_content(root: Path, config: dict) -> bool:
    """
    Supprime tout le contenu de démonstration du template.
    Appelé quand le flag --clean est utilisé.
    
    Supprime :
    - Modèles de démo (Item, TestData) dans models.py
    - Schémas de démo dans schemas.py
    - Endpoints de démo dans main.py (~400 lignes)
    - Composants frontend de démo
    - Tests de démo (test_auth.py, test_items.py)
    - Endpoint SSRF /api/m2m/test-call
    """
    print(f"\n{Colors.BOLD}🧹 Nettoyage du contenu de démonstration...{Colors.ENDC}\n")
    
    success = True
    
    # 1. Nettoyer models.py
    print(f"  {Colors.CYAN}Nettoyage backend/models.py...{Colors.ENDC}")
    success &= _clean_models(root)
    
    # 2. Nettoyer schemas.py
    print(f"  {Colors.CYAN}Nettoyage backend/schemas.py...{Colors.ENDC}")
    success &= _clean_schemas(root)
    
    # 3. Nettoyer main.py
    print(f"  {Colors.CYAN}Nettoyage backend/main.py...{Colors.ENDC}")
    success &= _clean_main(root, config)
    
    # 4. Supprimer composants frontend de démo
    print(f"  {Colors.CYAN}Nettoyage composants frontend...{Colors.ENDC}")
    success &= _clean_frontend_components(root)
    
    # 5. Nettoyer App.jsx
    print(f"  {Colors.CYAN}Réécriture App.jsx (squelette minimal)...{Colors.ENDC}")
    success &= _clean_app_jsx(root)
    
    # 6. Supprimer tests de démo
    print(f"  {Colors.CYAN}Nettoyage tests de démo...{Colors.ENDC}")
    success &= _clean_demo_tests(root)
    
    if success:
        print(f"\n  {Colors.GREEN}✅ Contenu de démo supprimé avec succès !{Colors.ENDC}")
    else:
        print(f"\n  {Colors.YELLOW}⚠ Nettoyage terminé avec des avertissements{Colors.ENDC}")
    
    return success


def _clean_models(root: Path) -> bool:
    """Supprime les modèles Item et TestData, ne garde que UserPreference et UploadedFile."""
    filepath = root / 'backend' / 'models.py'
    
    content = '''"""
Modèles SQLAlchemy pour l\'application.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, BigInteger
from datetime import datetime, timezone

from database import Base


class UserPreference(Base):
    """
    Préférences utilisateur stockées localement.
    Le Hub ne gère pas les préférences, c\'est à l\'application de le faire.
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
        return f"<UserPreference(username=\'{self.username}\')>"


class UploadedFile(Base):
    """
    Fichier uploadé dans l\'application.
    Permet de tracker les fichiers pour le système de backup/restore.
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
    
    # Référence optionnelle à une entité
    entity_type = Column(String(50), nullable=True, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<UploadedFile(id={self.id}, filename=\'{self.filename}\', owner=\'{self.owner}\')>"
    
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
'''
    
    try:
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ models.py nettoyé (Item, TestData supprimés){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur models.py: {e}{Colors.ENDC}")
        return False


def _clean_schemas(root: Path) -> bool:
    """Supprime les schémas Item et TestData."""
    filepath = root / 'backend' / 'schemas.py'
    
    content = '''"""
Schémas Pydantic pour la validation des données.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


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
    api_url: str = Field(..., description="URL de l\'API du service")
    frontend_url: Optional[str] = Field(None, description="URL du frontend du service")
    version: Optional[str] = Field(None, description="Version du service")
    status: Optional[str] = Field(None, description="Statut du service")
    is_healthy: bool = Field(True, description="Le service est-il en bonne santé")


class DiscoveredServiceDetailResponse(DiscoveredServiceResponse):
    """Service découvert avec informations techniques (admin only)."""
    ip: Optional[str] = Field(None, description="Adresse IP du service")
    api_port: Optional[int] = Field(None, description="Port de l\'API")
    frontend_port: Optional[int] = Field(None, description="Port du frontend")
    registered_at: Optional[str] = Field(None, description="Date d\'enregistrement")
    last_seen: Optional[str] = Field(None, description="Dernière activité")
    is_shared: bool = Field(True, description="Service en mode partagé")


class ServiceDiscoveryResponse(BaseModel):
    """Réponse de découverte des services."""
    count: int = Field(..., description="Nombre de services découverts")
    services: list[DiscoveredServiceResponse] = Field(..., description="Liste des services")
    cached_at: Optional[str] = Field(None, description="Date de mise en cache")
    per_page: Optional[int] = Field(None, description="Nombre par page")
    pages: Optional[int] = Field(None, description="Nombre total de pages")


# ============ Uploaded Files ============

class UploadedFileBase(BaseModel):
    """Base pour les fichiers uploadés."""
    filename: str = Field(..., max_length=255, description="Nom du fichier")
    category: str = Field("general", max_length=100, description="Catégorie de classement")
    description: Optional[str] = Field(None, description="Description du fichier")


class UploadedFileCreate(UploadedFileBase):
    """Création d\'un fichier uploadé."""
    entity_type: Optional[str] = Field(None, max_length=50)
    entity_id: Optional[int] = Field(None)


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
    """Estimation de la taille et durée d\'un backup."""
    total_preferences: int = Field(..., description="Nombre de préférences utilisateur")
    total_files: int = Field(..., description="Nombre de fichiers uploadés")
    
    database_size_bytes: int = Field(..., description="Taille estimée des données DB")
    files_size_bytes: int = Field(..., description="Taille totale des fichiers")
    total_size_bytes: int = Field(..., description="Taille totale estimée du backup")
    total_size_human: str = Field(..., description="Taille lisible (ex: 15.3 MB)")
    
    estimated_duration_seconds: float = Field(..., description="Durée estimée en secondes")
    estimated_duration_human: str = Field(..., description="Durée lisible")
    
    files_by_category: dict = Field(default_factory=dict)
    files_by_mime_type: dict = Field(default_factory=dict)
    
    warning: Optional[str] = Field(None, description="Avertissement si backup volumineux")


class BackupMetadata(BaseModel):
    """Métadonnées d\'un backup."""
    backup_id: str = Field(..., description="Identifiant unique du backup")
    app_slug: str = Field(..., description="Slug de l\'application")
    app_version: str = Field(..., description="Version de l\'application")
    created_at: str = Field(..., description="Date de création ISO")
    created_by: str = Field(..., description="Utilisateur ayant créé le backup")
    
    total_preferences: int = Field(..., description="Nombre de préférences")
    total_files: int = Field(..., description="Nombre de fichiers")
    total_size_bytes: int = Field(..., description="Taille totale")
    total_size_human: str = Field(..., description="Taille lisible")
    
    includes_files: bool = Field(True, description="Fichiers inclus dans le backup")
    checksum: str = Field(..., description="Checksum du backup")


class BackupResponse(BaseModel):
    """Réponse après création d\'un backup."""
    success: bool
    message: str
    metadata: BackupMetadata
    download_url: Optional[str] = Field(None, description="URL de téléchargement")


class RestoreRequest(BaseModel):
    """Requête de restauration."""
    backup_id: Optional[str] = Field(None)
    clear_existing: bool = Field(False)
    restore_preferences: bool = Field(True)
    restore_files: bool = Field(True)


class RestoreResponse(BaseModel):
    """Réponse après restauration."""
    success: bool
    message: str
    
    preferences_restored: int = Field(0)
    files_restored: int = Field(0)
    files_skipped: int = Field(0)
    
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SyncToHubRequest(BaseModel):
    """Requête de synchronisation vers le Hub."""
    description: Optional[str] = Field(None)
    tags: list[str] = Field(default_factory=list)


class SyncFromHubRequest(BaseModel):
    """Requête de synchronisation depuis le Hub."""
    backup_id: Optional[str] = Field(None)
    clear_existing: bool = Field(False)
'''
    
    try:
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ schemas.py nettoyé (Item/TestData schémas supprimés){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur schemas.py: {e}{Colors.ENDC}")
        return False


def _clean_main(root: Path, config: dict) -> bool:
    """Nettoie main.py : supprime les endpoints de démo, garde l'infra."""
    filepath = root / 'backend' / 'main.py'
    
    try:
        content = filepath.read_text(encoding='utf-8')
        
        # Remplacer les imports de démo
        content = content.replace(
            'from models import Item, UserPreference, TestData',
            'from models import UserPreference'
        )
        
        # Supprimer les imports de schémas de démo
        content = re.sub(
            r'from schemas import \(\n.*?\)',
            '''from schemas import (
    UserPreferenceUpdate, UserPreferenceResponse,
    UserInfo, MessageResponse, PaginatedResponse,
    ServiceDiscoveryResponse, DiscoveredServiceResponse, DiscoveredServiceDetailResponse
)''',
            content,
            flags=re.DOTALL
        )
        
        # Supprimer les sections de démo par marqueurs de section
        # On garde tout ce qui est avant "ENDPOINTS PUBLICS" et les sections infra
        
        # Supprimer endpoint /api/public
        content = re.sub(
            r'\n@app\.get\("/api/public".*?\n    return \{[^}]+\}\n',
            '\n',
            content,
            flags=re.DOTALL
        )
        
        # Supprimer endpoint /api/protected
        content = re.sub(
            r'\n@app\.get\("/api/protected".*?\n    return \{[^}]+\}\n',
            '\n',
            content,
            flags=re.DOTALL
        )
        
        # Supprimer la section "ENDPOINTS PAR RÔLE" entière
        content = re.sub(
            r'\n# ={5,}\n# ENDPOINTS PAR RÔLE.*?(?=\n# ={5,}\n# ENDPOINTS M2M)',
            '\n',
            content,
            flags=re.DOTALL
        )
        
        # Supprimer endpoint /api/m2m/test-call (SSRF)
        content = re.sub(
            r'\n@app\.post\("/api/m2m/test-call".*?\n    except Exception as e:\n        return \{"success": False, "error": str\(e\)\}\n',
            '\n',
            content,
            flags=re.DOTALL
        )
        
        # Supprimer la section "CRUD ITEMS" entière
        content = re.sub(
            r'\n# ={5,}\n# CRUD ITEMS.*?(?=\n# ={5,}\n# DONNÉES DE TEST)',
            '\n',
            content,
            flags=re.DOTALL
        )
        
        # Supprimer la section "DONNÉES DE TEST" entière
        content = re.sub(
            r'\n# ={5,}\n# DONNÉES DE TEST.*?(?=\n# ={5,}\n# PRÉFÉRENCES)',
            '\n',
            content,
            flags=re.DOTALL
        )
        
        # Nettoyer les lignes vides multiples
        content = re.sub(r'\n{4,}', '\n\n\n', content)
        
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ main.py nettoyé (endpoints de démo supprimés){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur main.py: {e}{Colors.ENDC}")
        return False


def _clean_frontend_components(root: Path) -> bool:
    """Supprime les composants frontend de démonstration."""
    demo_components = [
        'EndpointTests.jsx',
        'M2MTests.jsx',
        'DataTable.jsx',
        'TokenCard.jsx',
        'UserCard.jsx',
    ]
    
    components_dir = root / 'frontend' / 'src' / 'components'
    success = True
    
    for component in demo_components:
        filepath = components_dir / component
        if filepath.exists():
            try:
                filepath.unlink()
                print(f"    {Colors.GREEN}✓ Supprimé {component}{Colors.ENDC}")
            except Exception as e:
                print(f"    {Colors.RED}✗ Erreur {component}: {e}{Colors.ENDC}")
                success = False
    
    return success


def _clean_app_jsx(root: Path) -> bool:
    """Réécrit App.jsx avec un squelette minimal."""
    filepath = root / 'frontend' / 'src' / 'App.jsx'
    
    content = """import React, { useState, useEffect } from 'react'
import { useConfig } from './context/ConfigContext'
import { useAuth } from './context/AuthContext'
import Header from './components/Header'
import LoginPrompt from './components/LoginPrompt'

function App() {
  const [theme, setTheme] = useState(() => 
    localStorage.getItem('theme') || 'light'
  )
  const config = useConfig()
  const { isAuthenticated, user } = useAuth()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  }

  if (!config.loaded) {
    return (
      <div className="loading">
        <p>Chargement de la configuration...</p>
      </div>
    )
  }

  return (
    <div className="app">
      <Header theme={theme} toggleTheme={toggleTheme} />
      
      <div className="container">
        {!isAuthenticated ? (
          <LoginPrompt />
        ) : (
          <div className="card">
            <h2>Bienvenue {user?.username} !</h2>
            <p>Votre application est prête. Commencez à développer ici.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
"""
    
    try:
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ App.jsx réécrit (squelette minimal){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur App.jsx: {e}{Colors.ENDC}")
        return False


def _clean_demo_tests(root: Path) -> bool:
    """Supprime les fichiers de test de démo."""
    demo_tests = [
        'test_auth.py',
        'test_items.py',
    ]
    
    tests_dir = root / 'backend' / 'tests'
    success = True
    
    for test_file in demo_tests:
        filepath = tests_dir / test_file
        if filepath.exists():
            try:
                filepath.unlink()
                print(f"    {Colors.GREEN}✓ Supprimé {test_file}{Colors.ENDC}")
            except Exception as e:
                print(f"    {Colors.RED}✗ Erreur {test_file}: {e}{Colors.ENDC}")
                success = False
    
    return success


def create_version_file(root: Path) -> bool:
    """Réinitialise le fichier VERSION."""
    try:
        version_path = root / 'VERSION'
        version_path.write_text('0.0.1\n', encoding='utf-8')
        print(f"  {Colors.GREEN}✓ VERSION réinitialisé à 0.0.1{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur VERSION: {e}{Colors.ENDC}")
        return False


def create_changelog(root: Path, config: dict) -> bool:
    """Crée un nouveau CHANGELOG.md."""
    today = datetime.now().strftime('%d %B %Y').lstrip('0')
    
    # Mois en français
    months_fr = {
        'January': 'janvier', 'February': 'février', 'March': 'mars',
        'April': 'avril', 'May': 'mai', 'June': 'juin',
        'July': 'juillet', 'August': 'août', 'September': 'septembre',
        'October': 'octobre', 'November': 'novembre', 'December': 'décembre'
    }
    for en, fr in months_fr.items():
        today = today.replace(en, fr)
    
    content = f"""# Changelog - {config['APP_NAME']}

Historique des modifications de l'application.

Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

---

## [0.0.1] - {today}

### ✨ Initialisation

- Création du projet à partir de HUBapp_TEMPLATE
- Configuration initiale : `{config['APP_SLUG']}`
- Intégration authentification Hub

---

<!-- 
### Catégories disponibles :
- ✨ Nouvelles fonctionnalités (Added)
- 🔄 Modifications (Changed)  
- 🗑️ Suppressions (Removed)
- 🐛 Corrections (Fixed)
- 🔒 Sécurité (Security)
- ⚠️ Dépréciations (Deprecated)
-->
"""
    
    try:
        changelog_path = root / 'CHANGELOG.md'
        changelog_path.write_text(content, encoding='utf-8')
        print(f"  {Colors.GREEN}✓ CHANGELOG.md réinitialisé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur CHANGELOG.md: {e}{Colors.ENDC}")
        return False


def create_readme(root: Path, config: dict) -> bool:
    """Crée un nouveau README.md."""
    content = f"""# {config['APP_NAME']}

{config['APP_DESCRIPTION']}

## 🚀 Démarrage rapide

### Prérequis

- Docker et Docker Compose
- Accès au Hub (authentification centralisée)

### Installation

1. **Configurer l'environnement** (déjà fait si vous avez utilisé `init_new_app.py`)
   
   ```bash
   # Vérifier le fichier .env
   cat .env
   ```

2. **Lancer l'application**
   
   ```bash
   docker-compose up -d
   ```

3. **Accéder à l'application**
   
   - Frontend : http://localhost:{config['FRONTEND_PORT']}
   - API : http://localhost:{config['API_PORT']}
   - Documentation API : http://localhost:{config['API_PORT']}/docs

## 📁 Structure du projet

```
{config['APP_SLUG']}/
├── backend/           # API FastAPI
│   ├── main.py        # Point d'entrée
│   ├── config.py      # Configuration
│   ├── hub_auth.py    # Authentification Hub
│   ├── hub_client.py  # Client M2M Hub
│   ├── routes/        # Endpoints API
│   └── tests/         # Tests unitaires
├── frontend/          # Interface React
│   └── src/
├── docker-compose.yml
└── .env               # Configuration locale
```

## 🔐 Authentification

Cette application utilise le système d'authentification centralisé du Hub.

- Les utilisateurs se connectent via le Hub
- Les tokens JWT sont validés côté backend
- Le système M2M permet la communication inter-applications

## 🔧 Configuration

| Variable | Description | Valeur |
|----------|-------------|--------|
| `APP_SLUG` | Identifiant unique | `{config['APP_SLUG']}` |
| `API_PORT` | Port API | `{config['API_PORT']}` |
| `FRONTEND_PORT` | Port frontend | `{config['FRONTEND_PORT']}` |
| `HUB_HOST` | Adresse du Hub | `{config['HUB_HOST']}` |

## 📝 Développement

### Lancer les tests

```bash
docker-compose exec api pytest
```

### Voir les logs

```bash
docker-compose logs -f api
```

## 📄 License

Projet interne - Tous droits réservés.
"""
    
    try:
        readme_path = root / 'README.md'
        readme_path.write_text(content, encoding='utf-8')
        print(f"  {Colors.GREEN}✓ README.md réinitialisé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur README.md: {e}{Colors.ENDC}")
        return False


def main():
    """Point d'entrée principal."""
    # Détecter le flag --clean
    clean_mode = '--clean' in sys.argv
    
    print_header()
    
    if clean_mode:
        print(f"{Colors.YELLOW}🧹 Mode --clean activé : le contenu de démonstration sera supprimé{Colors.ENDC}\n")
    
    # Vérifier qu'on est dans le bon répertoire
    root = get_project_root()
    if not (root / 'docker-compose.yml').exists():
        print(f"{Colors.RED}✗ Erreur: Ce script doit être exécuté depuis le projet HUBapp_TEMPLATE{Colors.ENDC}")
        print(f"  Répertoire actuel: {root}")
        sys.exit(1)
    
    # Collecter les informations
    config = collect_app_info()
    
    # Confirmer
    if not confirm_settings(config):
        print(f"\n{Colors.YELLOW}Opération annulée.{Colors.ENDC}")
        sys.exit(0)
    
    # Appliquer les modifications
    print(f"\n{Colors.BOLD}🔄 Application des modifications...{Colors.ENDC}\n")
    
    success = True
    
    # 1. Créer .env
    print(f"{Colors.CYAN}[1/13] Création du fichier .env{Colors.ENDC}")
    success &= create_env_file(root, config)
    
    # 2. Mettre à jour .env.example
    print(f"{Colors.CYAN}[2/13] Mise à jour .env.example{Colors.ENDC}")
    success &= update_env_example(root, config)
    
    # 3. docker-compose.yml
    print(f"{Colors.CYAN}[3/13] Mise à jour docker-compose.yml{Colors.ENDC}")
    success &= update_docker_compose(root, config)
    
    # 4. backend/config.py
    print(f"{Colors.CYAN}[4/13] Mise à jour backend/config.py{Colors.ENDC}")
    success &= update_backend_config(root, config)
    
    # 5. Dockerfile.frontend
    print(f"{Colors.CYAN}[5/13] Mise à jour Dockerfile.frontend{Colors.ENDC}")
    success &= update_dockerfile_frontend(root, config)
    
    # 6. frontend/index.html
    print(f"{Colors.CYAN}[6/13] Mise à jour frontend/index.html{Colors.ENDC}")
    success &= update_frontend_index(root, config)
    
    # 7. frontend/Header.jsx
    print(f"{Colors.CYAN}[7/13] Mise à jour frontend/Header.jsx{Colors.ENDC}")
    success &= update_frontend_header(root, config)
    
    # 8. frontend/package.json
    print(f"{Colors.CYAN}[8/13] Mise à jour frontend/package.json{Colors.ENDC}")
    success &= update_frontend_package_json(root, config)
    
    # 9. frontend/src/config.js (appSlug)
    print(f"{Colors.CYAN}[9/13] Mise à jour frontend/src/config.js{Colors.ENDC}")
    success &= update_frontend_config_js(root, config)
    
    # 10. Fixtures de test (appSlug)
    print(f"{Colors.CYAN}[10/13] Mise à jour des fixtures de test{Colors.ENDC}")
    success &= update_test_fixtures(root, config)
    
    # 11. VERSION
    print(f"{Colors.CYAN}[11/13] Réinitialisation VERSION{Colors.ENDC}")
    success &= create_version_file(root)
    
    # 12. CHANGELOG.md et README.md
    print(f"{Colors.CYAN}[12/13] Réinitialisation documentation{Colors.ENDC}")
    success &= create_changelog(root, config)
    success &= create_readme(root, config)
    
    # 13. Nettoyage fichiers obsolètes
    print(f"{Colors.CYAN}[13/13] Nettoyage fichiers obsolètes{Colors.ENDC}")
    success &= cleanup_obsolete_files(root)
    
    # Nettoyage du contenu de démo si --clean
    if clean_mode:
        success &= clean_demo_content(root, config)
    
    # Résumé final
    print(f"\n{'═' * 60}")
    if success:
        print(f"""
{Colors.GREEN}✅ Initialisation terminée avec succès !{Colors.ENDC}

{Colors.BOLD}Prochaines étapes :{Colors.ENDC}

  1. Vérifier la configuration :
     {Colors.CYAN}cat .env{Colors.ENDC}

  2. Lancer l'application :
     {Colors.CYAN}docker-compose up -d{Colors.ENDC}

  3. Accéder à l'application :
     • Frontend : {Colors.BLUE}http://localhost:{config['FRONTEND_PORT']}{Colors.ENDC}
     • API :      {Colors.BLUE}http://localhost:{config['API_PORT']}{Colors.ENDC}
     • Docs :     {Colors.BLUE}http://localhost:{config['API_PORT']}/docs{Colors.ENDC}

{Colors.YELLOW}💡 N'oubliez pas de committer vos changements !{Colors.ENDC}
""")
    else:
        print(f"""
{Colors.YELLOW}⚠ Initialisation terminée avec des avertissements.{Colors.ENDC}
Veuillez vérifier les messages ci-dessus.
""")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
