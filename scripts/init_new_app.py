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
    python scripts/init_new_app.py

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

# === PORTS ===
API_PORT={config['API_PORT']}
FRONTEND_PORT={config['FRONTEND_PORT']}

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
    
    return update_file(filepath, replacements, "Valeurs par défaut mises à jour")


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

- Création du projet à partir de HUBapp_TEMPLATE v1.7.0
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
    print_header()
    
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
    print(f"{Colors.CYAN}[1/10] Création du fichier .env{Colors.ENDC}")
    success &= create_env_file(root, config)
    
    # 2. Mettre à jour .env.example
    print(f"{Colors.CYAN}[2/10] Mise à jour .env.example{Colors.ENDC}")
    success &= update_env_example(root, config)
    
    # 3. docker-compose.yml
    print(f"{Colors.CYAN}[3/10] Mise à jour docker-compose.yml{Colors.ENDC}")
    success &= update_docker_compose(root, config)
    
    # 4. backend/config.py
    print(f"{Colors.CYAN}[4/10] Mise à jour backend/config.py{Colors.ENDC}")
    success &= update_backend_config(root, config)
    
    # 5. Dockerfile.frontend
    print(f"{Colors.CYAN}[5/10] Mise à jour Dockerfile.frontend{Colors.ENDC}")
    success &= update_dockerfile_frontend(root, config)
    
    # 6. frontend/index.html
    print(f"{Colors.CYAN}[6/10] Mise à jour frontend/index.html{Colors.ENDC}")
    success &= update_frontend_index(root, config)
    
    # 7. frontend/Header.jsx
    print(f"{Colors.CYAN}[7/10] Mise à jour frontend/Header.jsx{Colors.ENDC}")
    success &= update_frontend_header(root, config)
    
    # 8. frontend/package.json
    print(f"{Colors.CYAN}[8/10] Mise à jour frontend/package.json{Colors.ENDC}")
    success &= update_frontend_package_json(root, config)
    
    # 9. VERSION
    print(f"{Colors.CYAN}[9/10] Réinitialisation VERSION{Colors.ENDC}")
    success &= create_version_file(root)
    
    # 10. CHANGELOG.md et README.md
    print(f"{Colors.CYAN}[10/10] Réinitialisation documentation{Colors.ENDC}")
    success &= create_changelog(root, config)
    success &= create_readme(root, config)
    
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
