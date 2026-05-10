#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'initialisation d'une nouvelle application HUB.

Ce script est le SEUL présent dans `ACTIONS/PYTHON/` au démarrage du template.
Il :
1. Collecte les paramètres de la nouvelle app (slug, nom, ports, hub...)
2. Met à jour les fichiers de config, docker-compose, frontend, backend, etc.
3. Optionnellement nettoie le contenu de démo (--clean) ou migre vers
   React + Tailwind CSS (--tailwind).
4. Génère les scripts d'action (`START`, `STOP`, `RESTART`, `LOGS`,
   `STATUS`, `DELETE_DATA`, `UPDATE`, `BACKUP_DB`, `SHELL_API`,
   `SHELL_DB`, `TEST`, `COMMIT`) sous `ACTIONS/PYTHON/` et leurs wrappers
   Linux (.sh) et Windows (.bat).
5. S'auto-supprime (lui-même + ses wrappers `INITIALISE.sh` / `.bat`).

Usage :
    python ACTIONS/PYTHON/INITIALISE.py
    python ACTIONS/PYTHON/INITIALISE.py --clean
    python ACTIONS/PYTHON/INITIALISE.py --tailwind
    python ACTIONS/PYTHON/INITIALISE.py --profile client.json

Compatible Linux / Windows / macOS.
"""

import os
import re
import sys
import json
import stat
from datetime import datetime
from pathlib import Path
from typing import Dict, List


APP_KIND_CLIENT = "client"
APP_KIND_TOOL = "tool"
APP_KIND_OTHER = "other"
APP_KIND_LABELS = {
    APP_KIND_CLIENT: "Application client",
    APP_KIND_TOOL: "Application outil",
    APP_KIND_OTHER: "Application autre",
}


# ============================================================
# COULEURS ANSI
# ============================================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')


# ============================================================
# UTILITAIRES
# ============================================================

def print_header():
    print(f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║  {Colors.BOLD}🚀 Initialisation d'une nouvelle application HUB{Colors.ENDC}{Colors.CYAN}               ║
║                                                                  ║
║  Ce script va transformer le template en une nouvelle app,       ║
║  puis générer les scripts d'action et s'auto-supprimer.          ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝{Colors.ENDC}
""")


def get_project_root() -> Path:
    """Retourne la racine du projet (ACTIONS/PYTHON/INITIALISE.py -> root)."""
    return Path(__file__).resolve().parents[2]


def validate_slug(slug: str) -> bool:
    return bool(re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', slug)) and len(slug) >= 3


def validate_port(port_str: str) -> bool:
    try:
        port = int(port_str)
        return 1024 <= port <= 65535
    except ValueError:
        return False


def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def parse_cli_options(argv: List[str]) -> dict:
    profile_path = None
    filtered_args = []
    skip_next = False

    for index, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--profile":
            if index + 1 >= len(argv):
                raise ValueError("L'option --profile attend un chemin de fichier JSON.")
            profile_path = Path(argv[index + 1]).expanduser().resolve()
            skip_next = True
            continue
        if arg.lower().endswith(".json") and profile_path is None:
            candidate = Path(arg).expanduser()
            if candidate.exists():
                profile_path = candidate.resolve()
                continue
        filtered_args.append(arg)

    return {
        "args": filtered_args,
        "profile_path": profile_path,
    }


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[O/n]" if default else "[o/N]"
    while True:
        response = input(f"{Colors.CYAN}{prompt} {suffix}: {Colors.ENDC}").strip().lower()
        if not response:
            return default
        if response in ('o', 'oui', 'y', 'yes'):
            return True
        if response in ('n', 'non', 'no'):
            return False
        print(f"{Colors.RED}✗ Réponse attendue: o/oui ou n/non.{Colors.ENDC}")


def prompt_choice(prompt: str, choices: Dict[str, str], default: str) -> str:
    options = ", ".join(
        f"{key}{' (défaut)' if key == default else ''} = {label}"
        for key, label in choices.items()
    )
    while True:
        response = input(f"{Colors.CYAN}{prompt} [{options}]: {Colors.ENDC}").strip().lower()
        if not response:
            return default
        if response in choices:
            return response
        print(f"{Colors.RED}✗ Choix invalide. Valeurs possibles: {', '.join(choices)}.{Colors.ENDC}")


def load_client_profile(profile_path: Path) -> dict:
    if not profile_path.exists():
        raise FileNotFoundError(f"Fiche client introuvable: {profile_path}")
    try:
        data = json.loads(profile_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalide dans {profile_path}: {exc}") from exc

    required_paths = [
        ("app.slug", ["app", "slug"]),
        ("app.name", ["app", "name"]),
        ("app.description", ["app", "description"]),
        ("client.name", ["client", "name"]),
        ("license.quote_number", ["license", "quote_number"]),
        ("license.quote_date", ["license", "quote_date"]),
        ("hub.host", ["hub", "host"]),
        ("hub.api_port", ["hub", "api_port"]),
        ("hub.frontend_port", ["hub", "frontend_port"]),
        ("ports.api", ["ports", "api"]),
        ("ports.frontend", ["ports", "frontend"]),
    ]
    for label, parts in required_paths:
        current = data
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"Champ requis absent dans la fiche client: {label}")
            current = current[part]

    if not validate_slug(str(data['app']['slug'])):
        raise ValueError("app.slug doit respecter le format de slug attendu.")
    if not validate_date(str(data['license']['quote_date'])):
        raise ValueError("license.quote_date doit être au format YYYY-MM-DD.")

    for label, value in {
        'hub.api_port': data['hub']['api_port'],
        'hub.frontend_port': data['hub']['frontend_port'],
        'ports.api': data['ports']['api'],
        'ports.frontend': data['ports']['frontend'],
    }.items():
        if not validate_port(str(value)) and str(value) != '80':
            raise ValueError(f"{label} doit être un port valide.")

    return data


def build_config_from_profile(profile: dict, profile_path: Path) -> dict:
    options = profile.get('options', {})
    license_info = profile.get('license', {})
    return {
        'APP_KIND': APP_KIND_CLIENT,
        'APP_KIND_LABEL': APP_KIND_LABELS[APP_KIND_CLIENT],
        'APP_PROFILE_PATH': str(profile_path),
        'APP_SLUG': profile['app']['slug'],
        'APP_NAME': profile['app']['name'],
        'APP_DESCRIPTION': profile['app']['description'],
        'API_PORT': str(profile['ports']['api']),
        'FRONTEND_PORT': str(profile['ports']['frontend']),
        'HUB_HOST': str(profile['hub']['host']),
        'HUB_API_PORT': str(profile['hub']['api_port']),
        'HUB_FRONTEND_PORT': str(profile['hub']['frontend_port']),
        'USE_TAILWIND': bool(options.get('tailwind', False)),
        'CLEAN_DEMO': bool(options.get('clean_demo', False)),
        'CLIENT_NAME': profile['client']['name'],
        'CLIENT_CONTACT_NAME': profile.get('client', {}).get('contact_name', ''),
        'CLIENT_CONTACT_EMAIL': profile.get('client', {}).get('contact_email', ''),
        'LICENSE_QUOTE_NUMBER': str(license_info['quote_number']),
        'LICENSE_QUOTE_DATE': str(license_info['quote_date']),
        'LICENSE_NOTICE_YEAR': str(license_info.get('notice_year') or datetime.now().year),
    }


def collect_license_info(app_kind: str) -> dict:
    if app_kind != APP_KIND_CLIENT:
        return {
            'CLIENT_NAME': '',
            'CLIENT_CONTACT_NAME': '',
            'CLIENT_CONTACT_EMAIL': '',
            'LICENSE_QUOTE_NUMBER': '',
            'LICENSE_QUOTE_DATE': '',
            'LICENSE_NOTICE_YEAR': str(datetime.now().year),
        }

    print(f"\n{Colors.BOLD}📄 Informations de licence client{Colors.ENDC}\n")
    return {
        'CLIENT_NAME': prompt_input(
            'Nom du client',
            validator=lambda value: bool(value.strip()),
            error_msg='Le nom du client est obligatoire.'
        ),
        'CLIENT_CONTACT_NAME': prompt_input('Nom du contact client', default=''),
        'CLIENT_CONTACT_EMAIL': prompt_input('Email du contact client', default=''),
        'LICENSE_QUOTE_NUMBER': prompt_input(
            'Numéro du devis',
            validator=lambda value: bool(value.strip()),
            error_msg='Le numéro du devis est obligatoire.'
        ),
        'LICENSE_QUOTE_DATE': prompt_input(
            'Date du devis (YYYY-MM-DD)',
            default=datetime.now().strftime('%Y-%m-%d'),
            validator=validate_date,
            error_msg='Format attendu: YYYY-MM-DD.'
        ),
        'LICENSE_NOTICE_YEAR': prompt_input(
            'Année de copyright',
            default=str(datetime.now().year),
            validator=lambda value: value.isdigit() and len(value) == 4,
            error_msg='Entrez une année sur 4 chiffres.'
        ),
    }


def prompt_input(prompt: str, default: str = "", validator=None, error_msg: str = "") -> str:
    while True:
        if default:
            user_input = input(f"{Colors.CYAN}{prompt} [{default}]: {Colors.ENDC}").strip()
            if not user_input:
                user_input = default
        else:
            user_input = input(f"{Colors.CYAN}{prompt}: {Colors.ENDC}").strip()
        if validator is None or validator(user_input):
            return user_input
        print(f"{Colors.RED}✗ {error_msg}{Colors.ENDC}")


def collect_app_info(parsed_options: dict) -> dict:
    print(f"\n{Colors.BOLD}📝 Configuration de votre nouvelle application{Colors.ENDC}\n")

    app_kind = prompt_choice(
        "Type d'application",
        {
            APP_KIND_CLIENT: APP_KIND_LABELS[APP_KIND_CLIENT],
            APP_KIND_TOOL: APP_KIND_LABELS[APP_KIND_TOOL],
            APP_KIND_OTHER: APP_KIND_LABELS[APP_KIND_OTHER],
        },
        default=APP_KIND_CLIENT,
    )

    profile_path = parsed_options.get('profile_path')
    if app_kind == APP_KIND_CLIENT:
        if profile_path is None and prompt_yes_no("Importer une fiche client JSON", default=True):
            profile_path = Path(
                prompt_input(
                    'Chemin vers la fiche client JSON',
                    validator=lambda value: Path(value).expanduser().exists(),
                    error_msg='Le fichier JSON indiqué est introuvable.'
                )
            ).expanduser().resolve()
        if profile_path is not None:
            config = build_config_from_profile(load_client_profile(profile_path), profile_path)
            print(f"{Colors.GREEN}✓ Fiche client importée: {profile_path}{Colors.ENDC}")
            return config

    print(f"{Colors.YELLOW}Le slug est l'identifiant unique de l'application.")
    print(f"Format: minuscules, chiffres et tirets uniquement (ex: mon-app, gestion-stock){Colors.ENDC}")
    app_slug = prompt_input(
        "APP_SLUG (identifiant unique)",
        validator=validate_slug,
        error_msg="Le slug doit contenir au moins 3 caractères, commencer par une lettre, "
                  "et ne contenir que des minuscules, chiffres et tirets."
    )

    print(f"\n{Colors.YELLOW}Le nom sera affiché dans l'interface et le Hub.{Colors.ENDC}")
    app_name = prompt_input("APP_NAME (nom affiché)", default=app_slug.replace("-", " ").title())

    print(f"\n{Colors.YELLOW}Description courte de l'application.{Colors.ENDC}")
    app_description = prompt_input("APP_DESCRIPTION", default=f"Application {app_name}")

    print(f"\n{Colors.BOLD}🔌 Configuration des ports{Colors.ENDC}")
    print(f"{Colors.YELLOW}Choisissez des ports non utilisés sur votre système.{Colors.ENDC}\n")

    api_port = prompt_input("API_PORT (port backend)", default="9045",
                            validator=validate_port,
                            error_msg="Port entre 1024 et 65535.")
    frontend_port = prompt_input("FRONTEND_PORT (port frontend)", default="4250",
                                 validator=validate_port,
                                 error_msg="Port entre 1024 et 65535.")

    print(f"\n{Colors.BOLD}🔗 Configuration du Hub{Colors.ENDC}")
    print(f"{Colors.YELLOW}Adresse du serveur Hub auquel cette app se connectera.{Colors.ENDC}\n")

    hub_host = prompt_input("HUB_HOST (IP/hostname du Hub)", default="192.0.2.11")
    hub_api_port = prompt_input("HUB_API_PORT", default="8000",
                                validator=validate_port,
                                error_msg="Port entre 1024 et 65535.")
    hub_frontend_port = prompt_input("HUB_FRONTEND_PORT", default="80",
                                     validator=lambda x: validate_port(x) or x == "80",
                                     error_msg="Port entre 1024 et 65535.")

    use_tailwind = '--tailwind' in parsed_options['args']
    clean_demo = '--clean' in parsed_options['args']
    if not use_tailwind and not clean_demo:
        print(f"\n{Colors.BOLD}🎨 Interface frontend{Colors.ENDC}")
        print(f"{Colors.YELLOW}Vous pouvez repartir sur une base React + Tailwind CSS propre.")
        print(f"Les composants de messagerie/notifications du Hub seront conservés.{Colors.ENDC}\n")
        use_tailwind = prompt_yes_no("Migrer vers React + Tailwind CSS", default=False)

    config = {
        'APP_KIND': app_kind,
        'APP_KIND_LABEL': APP_KIND_LABELS[app_kind],
        'APP_PROFILE_PATH': '',
        "APP_SLUG": app_slug,
        "APP_NAME": app_name,
        "APP_DESCRIPTION": app_description,
        "API_PORT": api_port,
        "FRONTEND_PORT": frontend_port,
        "HUB_HOST": hub_host,
        "HUB_API_PORT": hub_api_port,
        "HUB_FRONTEND_PORT": hub_frontend_port,
        "USE_TAILWIND": use_tailwind,
        'CLEAN_DEMO': clean_demo,
    }
    config.update(collect_license_info(app_kind))
    return config


def confirm_settings(config: dict) -> bool:
    print(f"\n{Colors.BOLD}📋 Récapitulatif de la configuration{Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 50}{Colors.ENDC}")
    print(f"  TYPE:             {Colors.GREEN}{config['APP_KIND_LABEL']}{Colors.ENDC}")
    print(f"  APP_SLUG:         {Colors.GREEN}{config['APP_SLUG']}{Colors.ENDC}")
    print(f"  APP_NAME:         {Colors.GREEN}{config['APP_NAME']}{Colors.ENDC}")
    print(f"  APP_DESCRIPTION:  {Colors.GREEN}{config['APP_DESCRIPTION']}{Colors.ENDC}")
    print(f"  API_PORT:         {Colors.GREEN}{config['API_PORT']}{Colors.ENDC}")
    print(f"  FRONTEND_PORT:    {Colors.GREEN}{config['FRONTEND_PORT']}{Colors.ENDC}")
    print(f"  HUB_HOST:         {Colors.GREEN}{config['HUB_HOST']}{Colors.ENDC}")
    print(f"  HUB_API_PORT:     {Colors.GREEN}{config['HUB_API_PORT']}{Colors.ENDC}")
    print(f"  HUB_FRONTEND_PORT:{Colors.GREEN}{config['HUB_FRONTEND_PORT']}{Colors.ENDC}")
    if config.get('APP_PROFILE_PATH'):
        print(f"  FICHE CLIENT:     {Colors.GREEN}{config['APP_PROFILE_PATH']}{Colors.ENDC}")
    if config['APP_KIND'] == APP_KIND_CLIENT:
        print(f"  CLIENT:           {Colors.GREEN}{config['CLIENT_NAME']}{Colors.ENDC}")
        print(f"  DEVIS:            {Colors.GREEN}{config['LICENSE_QUOTE_NUMBER']} ({config['LICENSE_QUOTE_DATE']}){Colors.ENDC}")
    if config.get('USE_TAILWIND'):
        print(f"  TAILWIND CSS:     {Colors.GREEN}Oui (React + Tailwind){Colors.ENDC}")
    if config.get('CLEAN_DEMO'):
        print(f"  NETTOYAGE DEMO:   {Colors.GREEN}Oui{Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 50}{Colors.ENDC}")
    response = input(f"\n{Colors.YELLOW}Confirmer ces paramètres ? (O/n): {Colors.ENDC}").strip().lower()
    return response in ('', 'o', 'oui', 'y', 'yes')


def update_file(filepath: Path, replacements: list, description: str) -> bool:
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
        print(f"  {Colors.YELLOW}○ Pas de changement: {filepath.name}{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur {filepath.name}: {e}{Colors.ENDC}")
        return False


# ============================================================
# MISE À JOUR DES FICHIERS DE CONFIG
# ============================================================

def create_env_file(root: Path, config: dict) -> bool:
    example_path = root / '.env.example'
    env_path = root / '.env'
    try:
        content = example_path.read_text(encoding='utf-8')
        frontend_port = int(config['FRONTEND_PORT'])
        replacements = [
            ('APP_SLUG=mon-app', f'APP_SLUG={config["APP_SLUG"]}'),
            ('APP_NAME=Mon Application', f'APP_NAME={config["APP_NAME"]}'),
            ('APP_DESCRIPTION=Application template avec authentification Hub',
             f'APP_DESCRIPTION={config["APP_DESCRIPTION"]}'),
            ('API_PORT=9045', f'API_PORT={config["API_PORT"]}'),
            ('FRONTEND_PORT=4250', f'FRONTEND_PORT={frontend_port}'),
            ('FRONTEND_HTTPS_PORT=4251', f'FRONTEND_HTTPS_PORT={frontend_port + 1}'),
            ('HUB_HOST=192.0.2.11', f'HUB_HOST={config["HUB_HOST"]}'),
            ('HUB_API_PORT=8000', f'HUB_API_PORT={config["HUB_API_PORT"]}'),
            ('HUB_FRONTEND_PORT=80', f'HUB_FRONTEND_PORT={config["HUB_FRONTEND_PORT"]}'),
            ('POSTGRES_HOST=mon-app-postgres',
             f'POSTGRES_HOST={config["APP_SLUG"]}-postgres'),
            ("# Configuration de l'application Template Hub",
             f"# Configuration de l'application {config['APP_NAME']} "
             f"(généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')})"),
            ('# Copier ce fichier vers .env et adapter les valeurs',
             '# Fichier généré automatiquement par ACTIONS/PYTHON/INITIALISE.py'),
        ]
        for old, new in replacements:
            content = content.replace(old, new)
        content = re.sub(r'^APP_VERSION=.*$', 'APP_VERSION=0.0.1', content, flags=re.MULTILINE)
        env_path.write_text(content, encoding='utf-8')
        print(f"  {Colors.GREEN}✓ Fichier .env créé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur création .env: {e}{Colors.ENDC}")
        return False


def update_env_example(root: Path, config: dict) -> bool:
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
            ("# Configuration de l'application Template Hub",
             f"# Configuration de l'application {config['APP_NAME']}"),
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
    filepath = root / 'backend' / 'config.py'
    replacements = [
        ('APP_SLUG: str = "mon-app"', f'APP_SLUG: str = "{config["APP_SLUG"]}"'),
        ('APP_NAME: str = "Mon Application"', f'APP_NAME: str = "{config["APP_NAME"]}"'),
        ("APP_DESCRIPTION: str = \"Template d'application avec authentification Hub\"",
         f'APP_DESCRIPTION: str = "{config["APP_DESCRIPTION"]}"'),
        ('API_PORT: int = 9045', f'API_PORT: int = {config["API_PORT"]}'),
        ('FRONTEND_PORT: int = 4250', f'FRONTEND_PORT: int = {config["FRONTEND_PORT"]}'),
        ('HUB_API_PORT: int = 8000', f'HUB_API_PORT: int = {config["HUB_API_PORT"]}'),
        ('HUB_FRONTEND_PORT: int = 80', f'HUB_FRONTEND_PORT: int = {config["HUB_FRONTEND_PORT"]}'),
    ]
    return update_file(filepath, replacements, "Config backend mise à jour")


def update_dockerfile_frontend(root: Path, config: dict) -> bool:
    filepath = root / 'Dockerfile.frontend'
    replacements = [
        ('ARG VITE_API_PORT=9045', f'ARG VITE_API_PORT={config["API_PORT"]}'),
        ('ARG VITE_HUB_API_PORT=8000', f'ARG VITE_HUB_API_PORT={config["HUB_API_PORT"]}'),
        ('ARG VITE_HUB_FRONTEND_PORT=80', f'ARG VITE_HUB_FRONTEND_PORT={config["HUB_FRONTEND_PORT"]}'),
        ('ARG VITE_APP_SLUG=mon-app', f'ARG VITE_APP_SLUG={config["APP_SLUG"]}'),
    ]
    return update_file(filepath, replacements, "Dockerfile frontend mis à jour")


def update_frontend_index(root: Path, config: dict) -> bool:
    filepath = root / 'frontend' / 'index.html'
    replacements = [
        ('<title>Template App - Hub Auth</title>', f'<title>{config["APP_NAME"]}</title>'),
    ]
    return update_file(filepath, replacements, "Titre HTML mis à jour")


def update_frontend_header(root: Path, config: dict) -> bool:
    filepath = root / 'frontend' / 'src' / 'components' / 'Header.jsx'
    replacements = [
        ('<h1>🔐 Template App - Hub Auth</h1>', f'<h1>🔐 {config["APP_NAME"]}</h1>'),
    ]
    return update_file(filepath, replacements, "Header frontend mis à jour")


def update_frontend_package_json(root: Path, config: dict) -> bool:
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
    filepath = root / 'frontend' / 'src' / 'config.js'
    replacements = [
        ("APP_SLUG: import.meta.env.VITE_APP_SLUG || 'mon-app'",
         f"APP_SLUG: import.meta.env.VITE_APP_SLUG || '{config['APP_SLUG']}'"),
    ]
    return update_file(filepath, replacements, "Config frontend (src) mise à jour")


def update_test_fixtures(root: Path, config: dict) -> bool:
    success = True
    conftest_path = root / 'backend' / 'tests' / 'conftest.py'
    if conftest_path.exists():
        try:
            content = conftest_path.read_text(encoding='utf-8')
            content = content.replace('{"mon-app": app_role}',
                                      '{' + f'"{config["APP_SLUG"]}": app_role' + '}')
            content = content.replace('{"mon-app": "service"}',
                                      '{' + f'"{config["APP_SLUG"]}": "service"' + '}')
            conftest_path.write_text(content, encoding='utf-8')
            print(f"  {Colors.GREEN}✓ conftest.py mis à jour{Colors.ENDC}")
        except Exception as e:
            print(f"  {Colors.RED}✗ Erreur conftest.py: {e}{Colors.ENDC}")
            success = False
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
    success = True
    obsolete_config = root / 'frontend' / 'config.js'
    if obsolete_config.exists():
        try:
            obsolete_config.unlink()
            print(f"  {Colors.GREEN}✓ Supprimé frontend/config.js (vestige inutilisé){Colors.ENDC}")
        except Exception as e:
            print(f"  {Colors.RED}✗ Erreur suppression frontend/config.js: {e}{Colors.ENDC}")
            success = False
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
    print(f"\n{Colors.BOLD}🧹 Nettoyage du contenu de démonstration...{Colors.ENDC}\n")
    success = True
    print(f"  {Colors.CYAN}Nettoyage backend/models.py...{Colors.ENDC}")
    success &= _clean_models(root)
    print(f"  {Colors.CYAN}Nettoyage backend/schemas.py...{Colors.ENDC}")
    success &= _clean_schemas(root)
    print(f"  {Colors.CYAN}Nettoyage backend/main.py...{Colors.ENDC}")
    success &= _clean_main(root, config)
    print(f"  {Colors.CYAN}Nettoyage routeurs backend de démo...{Colors.ENDC}")
    success &= _clean_demo_routes(root)
    print(f"  {Colors.CYAN}Nettoyage diagnostics backend...{Colors.ENDC}")
    success &= _clean_service_test_route(root)
    print(f"  {Colors.CYAN}Nettoyage composants frontend...{Colors.ENDC}")
    success &= _clean_frontend_components(root)
    print(f"  {Colors.CYAN}Réécriture App.jsx (squelette minimal)...{Colors.ENDC}")
    success &= _clean_app_jsx(root)
    print(f"  {Colors.CYAN}Nettoyage tests de démo...{Colors.ENDC}")
    success &= _clean_demo_tests(root)
    if success:
        print(f"\n  {Colors.GREEN}✅ Contenu de démo supprimé avec succès !{Colors.ENDC}")
    else:
        print(f"\n  {Colors.YELLOW}⚠ Nettoyage terminé avec des avertissements{Colors.ENDC}")
    return success


def _clean_models(root: Path) -> bool:
    filepath = root / 'backend' / 'models.py'
    content = '''"""
Modèles SQLAlchemy pour l\'application.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, BigInteger
from datetime import datetime, timezone

from database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    theme = Column(String(20), default="system")
    language = Column(String(5), default="fr")
    items_per_page = Column(Integer, default=20)
    email_notifications = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<UserPreference(username=\'{self.username}\')>"


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    relative_path = Column(String(500), nullable=False, unique=True, index=True)
    size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    hash = Column(String(64), nullable=False)
    category = Column(String(100), default="general", index=True)
    description = Column(Text, nullable=True)
    owner = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=True, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<UploadedFile(id={self.id}, filename=\'{self.filename}\', owner=\'{self.owner}\')>"

    def to_backup_dict(self) -> dict:
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
        print(f"    {Colors.GREEN}✓ models.py nettoyé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur models.py: {e}{Colors.ENDC}")
        return False


def _clean_schemas(root: Path) -> bool:
    filepath = root / 'backend' / 'schemas.py'
    content = '''"""
Schémas Pydantic pour la validation des données.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserPreferenceBase(BaseModel):
    theme: str = Field("system", pattern="^(light|dark|system)$")
    language: str = Field("fr", min_length=2, max_length=5)
    items_per_page: int = Field(20, ge=5, le=100)
    email_notifications: bool = True


class UserPreferenceUpdate(BaseModel):
    theme: Optional[str] = Field(None, pattern="^(light|dark|system)$")
    language: Optional[str] = Field(None, min_length=2, max_length=5)
    items_per_page: Optional[int] = Field(None, ge=5, le=100)
    email_notifications: Optional[bool] = None


class UserPreferenceResponse(UserPreferenceBase):
    username: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserInfo(BaseModel):
    username: str
    roles: list[str]
    app_role: Optional[str]
    is_service_account: bool


class TokenInfo(BaseModel):
    valid: bool
    username: Optional[str] = None
    app_role: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    per_page: int = 20
    pages: int = 1


class DiscoveredServiceResponse(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    api_url: str
    frontend_url: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    is_healthy: bool = True


class DiscoveredServiceDetailResponse(DiscoveredServiceResponse):
    ip: Optional[str] = None
    api_port: Optional[int] = None
    frontend_port: Optional[int] = None
    registered_at: Optional[str] = None
    last_seen: Optional[str] = None
    is_shared: bool = True


class ServiceDiscoveryResponse(BaseModel):
    count: int
    services: list[DiscoveredServiceResponse]
    cached_at: Optional[str] = None
    per_page: Optional[int] = None
    pages: Optional[int] = None


class UploadedFileBase(BaseModel):
    filename: str = Field(..., max_length=255)
    category: str = Field("general", max_length=100)
    description: Optional[str] = None


class UploadedFileCreate(UploadedFileBase):
    entity_type: Optional[str] = Field(None, max_length=50)
    entity_id: Optional[int] = None


class UploadedFileResponse(UploadedFileBase):
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


class BackupEstimate(BaseModel):
    total_preferences: int
    total_files: int
    database_size_bytes: int
    files_size_bytes: int
    total_size_bytes: int
    total_size_human: str
    estimated_duration_seconds: float
    estimated_duration_human: str
    files_by_category: dict = Field(default_factory=dict)
    files_by_mime_type: dict = Field(default_factory=dict)
    warning: Optional[str] = None


class BackupMetadata(BaseModel):
    backup_id: str
    app_slug: str
    app_version: str
    created_at: str
    created_by: str
    total_preferences: int
    total_files: int
    total_size_bytes: int
    total_size_human: str
    includes_files: bool = True
    checksum: str


class BackupResponse(BaseModel):
    success: bool
    message: str
    metadata: BackupMetadata
    download_url: Optional[str] = None


class RestoreRequest(BaseModel):
    backup_id: Optional[str] = None
    clear_existing: bool = False
    restore_preferences: bool = True
    restore_files: bool = True


class RestoreResponse(BaseModel):
    success: bool
    message: str
    preferences_restored: int = 0
    files_restored: int = 0
    files_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SyncToHubRequest(BaseModel):
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class SyncFromHubRequest(BaseModel):
    backup_id: Optional[str] = None
    clear_existing: bool = False
'''
    try:
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ schemas.py nettoyé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur schemas.py: {e}{Colors.ENDC}")
        return False


def _clean_main(root: Path, config: dict) -> bool:
    filepath = root / 'backend' / 'main.py'
    try:
        content = filepath.read_text(encoding='utf-8')
        for line in [
            'from routes.items import router as items_router\n',
            'from routes.test_data import router as test_data_router\n',
            'app.include_router(items_router)\n',
            'app.include_router(test_data_router)\n',
        ]:
            content = content.replace(line, '')
        content = content.replace(
            'from models import Item, UserPreference, TestData',
            'from models import UserPreference'
        )
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
        content = re.sub(r'\n@app\.get\("/api/public".*?\n    return \{[^}]+\}\n', '\n', content, flags=re.DOTALL)
        content = re.sub(r'\n@app\.get\("/api/protected".*?\n    return \{[^}]+\}\n', '\n', content, flags=re.DOTALL)
        content = re.sub(r'\n# ={5,}\n# ENDPOINTS PAR RÔLE.*?(?=\n# ={5,}\n# ENDPOINTS M2M)', '\n', content, flags=re.DOTALL)
        content = re.sub(r'\n# ={5,}\n# ENDPOINTS PAR RÔLE.*?(?=\n# ={5,}\n# POINT D\'ENTRÉE)', '\n', content, flags=re.DOTALL)
        content = content.replace(
            '''    return UserInfo(
        username=user.sub,
        app_role=user.get_app_role(settings.APP_SLUG),
        is_service_account=user.is_service_account()
    )''',
            '''    return UserInfo(
        username=user.sub,
        roles=sorted(set(user.apps.values())),
        app_role=user.get_app_role(settings.APP_SLUG),
        is_service_account=user.is_service_account()
    )'''
        )
        content = re.sub(
            r'\n@app\.post\("/api/m2m/test-call".*?\n    except Exception as e:\n        return \{"success": False, "error": str\(e\)\}\n',
            '\n', content, flags=re.DOTALL)
        content = re.sub(r'\n# ={5,}\n# CRUD ITEMS.*?(?=\n# ={5,}\n# DONNÉES DE TEST)', '\n', content, flags=re.DOTALL)
        content = re.sub(r'\n# ={5,}\n# DONNÉES DE TEST.*?(?=\n# ={5,}\n# PRÉFÉRENCES)', '\n', content, flags=re.DOTALL)
        content = re.sub(r'\n{4,}', '\n\n\n', content)
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ main.py nettoyé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur main.py: {e}{Colors.ENDC}")
        return False


def _clean_demo_routes(root: Path) -> bool:
    routes_dir = root / 'backend' / 'routes'
    success = True
    for route_file in ('items.py', 'test_data.py'):
        filepath = routes_dir / route_file
        if filepath.exists():
            try:
                filepath.unlink()
                print(f"    {Colors.GREEN}✓ Supprimé routes/{route_file}{Colors.ENDC}")
            except Exception as e:
                print(f"    {Colors.RED}✗ Erreur routes/{route_file}: {e}{Colors.ENDC}")
                success = False
    return success


def _clean_service_test_route(root: Path) -> bool:
    filepath = root / 'backend' / 'routes' / 'tests.py'
    try:
        content = filepath.read_text(encoding='utf-8')
        old = '''        # Test 3: Vérifier que les tables de backup existent localement
        from models import Item, UserPreference, TestData
        from sqlalchemy import select, func
        
        items_count = await db.scalar(select(func.count(Item.id))) or 0
        prefs_count = await db.scalar(select(func.count(UserPreference.username))) or 0
        testdata_count = await db.scalar(select(func.count(TestData.id))) or 0
        
        has_data_to_backup = items_count > 0 or prefs_count > 0 or testdata_count > 0'''
        new = '''        # Test 3: Vérifier que les tables de backup existent localement.
        # Le mode --clean retire les modèles de démonstration Item/TestData.
        from models import UserPreference, UploadedFile
        from sqlalchemy import select, func
        
        prefs_count = await db.scalar(select(func.count(UserPreference.username))) or 0
        files_count = await db.scalar(select(func.count(UploadedFile.id))) or 0
        
        has_data_to_backup = prefs_count > 0 or files_count > 0'''
        content = content.replace(old, new)
        content = content.replace(
            '''                "local_data": {
                    "items_count": items_count,
                    "preferences_count": prefs_count,
                    "test_data_count": testdata_count,
                    "has_data_to_backup": has_data_to_backup
                },''',
            '''                "local_data": {
                    "preferences_count": prefs_count,
                    "files_count": files_count,
                    "has_data_to_backup": has_data_to_backup
                },'''
        )
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ routes/tests.py adapté{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur routes/tests.py: {e}{Colors.ENDC}")
        return False


def _clean_frontend_components(root: Path) -> bool:
    demo_components = ['EndpointTests.jsx', 'M2MTests.jsx', 'DataTable.jsx', 'TokenCard.jsx', 'UserCard.jsx']
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
            <h2>Bienvenue {user?.username || user?.sub} !</h2>
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
        print(f"    {Colors.GREEN}✓ App.jsx réécrit{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur App.jsx: {e}{Colors.ENDC}")
        return False


def _clean_demo_tests(root: Path) -> bool:
    demo_tests = ['test_auth.py', 'test_items.py', 'test_backup.py']
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


# ============================================================
# VERSION / CHANGELOG / README
# ============================================================

def create_version_file(root: Path) -> bool:
    try:
        (root / 'VERSION').write_text('0.0.1\n', encoding='utf-8')
        print(f"  {Colors.GREEN}✓ VERSION réinitialisé à 0.0.1{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur VERSION: {e}{Colors.ENDC}")
        return False


def create_changelog(root: Path, config: dict) -> bool:
    today = datetime.now().strftime('%d %B %Y').lstrip('0')
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
- Type d'application : {config['APP_KIND_LABEL']}
- Intégration authentification Hub

---
"""
    try:
        (root / 'CHANGELOG.md').write_text(content, encoding='utf-8')
        print(f"  {Colors.GREEN}✓ CHANGELOG.md réinitialisé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur CHANGELOG.md: {e}{Colors.ENDC}")
        return False


def create_readme(root: Path, config: dict) -> bool:
    mode_summary = {
        APP_KIND_CLIENT: "Initialisée pour un client final, avec prise en charge d'une fiche client JSON ou d'une saisie assistée.",
        APP_KIND_TOOL: "Initialisée comme outil interne avec configuration guidée.",
        APP_KIND_OTHER: "Initialisée en mode libre avec saisie manuelle complète.",
    }[config['APP_KIND']]
    client_block = ""
    if config['APP_KIND'] == APP_KIND_CLIENT:
        client_block = f"""

## 🧾 Informations client

| Champ | Valeur |
|-------|--------|
| `Client` | `{config['CLIENT_NAME']}` |
| `Devis` | `{config['LICENSE_QUOTE_NUMBER']}` |
| `Date du devis` | `{config['LICENSE_QUOTE_DATE']}` |
"""

    content = f"""# {config['APP_NAME']}

{config['APP_DESCRIPTION']}

{mode_summary}

## 🚀 Démarrage rapide

### Prérequis

- Docker et Docker Compose
- Accès au Hub (authentification centralisée)

### Lancer l'application

```bash
# Linux / macOS
bash ACTIONS/LINUX/START.sh

# Windows
ACTIONS\\WINDOWS\\START.bat
```

### Accéder à l'application

- Frontend : http://localhost:{config['FRONTEND_PORT']}
- API : http://localhost:{config['API_PORT']}
- Documentation API : http://localhost:{config['API_PORT']}/docs

## 🛠️ Actions disponibles

Toutes les actions sont sous `ACTIONS/<OS>/` :

| Action          | Description                                    |
|-----------------|------------------------------------------------|
| `START [-fe\\|-be]` | down + build + up (full ou frontend/backend)|
| `STOP`          | docker compose down                            |
| `RESTART [-fe\\|-be]` | docker compose restart                    |
| `LOGS [-fe\\|-be\\|-db]` | logs (suit en TTY)                     |
| `STATUS`        | ps + health check API                          |
| `UPDATE`        | git pull + build + up                          |
| `BACKUP_DB`     | dump PostgreSQL → `./backups/`                 |
| `DELETE_DATA`   | down -v (DESTRUCTIF, confirmation requise)     |
| `SHELL_API`     | bash dans le conteneur api                     |
| `SHELL_DB`      | psql dans le conteneur postgres                |
| `TEST`          | pytest dans le conteneur api                   |
| `COMMIT`        | bump version + changelog + git commit          |

## 🔐 Authentification

Cette application utilise le système d'authentification centralisé du Hub.

## 🔧 Configuration

| Variable | Valeur |
|----------|--------|
| `APP_SLUG` | `{config['APP_SLUG']}` |
| `API_PORT` | `{config['API_PORT']}` |
| `FRONTEND_PORT` | `{config['FRONTEND_PORT']}` |
| `HUB_HOST` | `{config['HUB_HOST']}` |
{client_block}
"""
    try:
        (root / 'README.md').write_text(content, encoding='utf-8')
        print(f"  {Colors.GREEN}✓ README.md réinitialisé{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur README.md: {e}{Colors.ENDC}")
        return False


def create_license_file(root: Path, config: dict) -> bool:
    if config['APP_KIND'] == APP_KIND_CLIENT:
        content = f"""# LICENCE PROPRIÉTAIRE ET COMMERCIALE
**Copyright (c) {config['LICENSE_NOTICE_YEAR']} POULIDOR Audit & Développement. Tous droits réservés.**

Ce code source, incluant le socle technique (\"Hub\"), les modèles et les applications spécifiques développées, est la propriété intellectuelle exclusive de Valerian POULIDOR (POULIDOR Audit & Développement).

## 1. Droits accordés (Licence d'utilisation)
L'accès à ce code source est accordé exclusivement à l'entreprise **{config['CLIENT_NAME']}** (ci-après \"le Client\"), conformément au devis **{config['LICENSE_QUOTE_NUMBER']}** validé le **{config['LICENSE_QUOTE_DATE']}**, et sous réserve du paiement intégral des prestations.

Le Client titulaire de la licence est autorisé à :
- Utiliser le logiciel pour les besoins internes de son entreprise, sans limite de durée.
- Étudier, modifier et adapter le code source pour son usage interne exclusif.
- Permettre à ses employés ou prestataires techniques d'accéder au code uniquement dans le but de le maintenir ou de le développer pour le compte du Client.

## 2. Restrictions strictes
Il est STRICTEMENT INTERDIT, sans l'accord écrit, préalable et exprès de POULIDOR Audit & Développement, de :
- Vendre, revendre, louer ou sous-licencier le présent logiciel, son code source ou toute partie de celui-ci.
- Distribuer, publier ou rendre public le code source sur internet ou à des tiers non autorisés.
- Utiliser le code source, modifié ou non, pour créer un produit commercialisé sous une autre marque.
- Retirer, modifier ou masquer la présente mention de copyright et de licence.

Toute violation de ces conditions entraînera la révocation immédiate de la licence d'utilisation accordée à **{config['CLIENT_NAME']}** et des poursuites judiciaires.
"""
    else:
        content = f"""# LICENCE PROPRIÉTAIRE ET COMMERCIALE
**Copyright (c) {datetime.now().year} POULIDOR Audit & Développement. Tous droits réservés.**

Ce code source, incluant le socle technique (\"Hub\"), les modèles et les applications spécifiques développées, est la propriété intellectuelle exclusive de Valerian POULIDOR (POULIDOR Audit & Développement).

## 1. Droits accordés (Licence d'utilisation)
Cette application a été initialisée en mode **{config['APP_KIND_LABEL']}**.

Les droits d'utilisation finaux, les engagements de maintenance et les conditions de diffusion doivent être formalisés avant toute livraison à un tiers.

## 2. Restrictions strictes
Il est STRICTEMENT INTERDIT, sans l'accord écrit, préalable et exprès de POULIDOR Audit & Développement, de :
- Vendre, revendre, louer ou sous-licencier le présent logiciel, son code source ou toute partie de celui-ci.
- Distribuer, publier ou rendre public le code source sur internet ou à des tiers non autorisés.
- Utiliser le code source, modifié ou non, pour créer un produit commercialisé sous une autre marque.
- Retirer, modifier ou masquer la présente mention de copyright et de licence.
"""
    try:
        (root / 'LICENSE.md').write_text(content, encoding='utf-8')
        print(f"  {Colors.GREEN}✓ LICENSE.md généré pour le mode {config['APP_KIND']}{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"  {Colors.RED}✗ Erreur LICENSE.md: {e}{Colors.ENDC}")
        return False


# ============================================================
# MIGRATION TAILWIND CSS
# ============================================================

def setup_tailwind(root: Path, config: dict) -> bool:
    print(f"\n{Colors.BOLD}🎨 Migration vers React + Tailwind CSS...{Colors.ENDC}\n")
    success = True
    print(f"  {Colors.CYAN}Ajout des dépendances Tailwind...{Colors.ENDC}")
    success &= _tailwind_update_package_json(root, config)
    print(f"  {Colors.CYAN}Création vite.config.js (plugin Tailwind)...{Colors.ENDC}")
    success &= _tailwind_create_configs(root)
    print(f"  {Colors.CYAN}Réécriture index.css...{Colors.ENDC}")
    success &= _tailwind_rewrite_css(root)
    print(f"  {Colors.CYAN}Réécriture composants...{Colors.ENDC}")
    success &= _tailwind_rewrite_app_jsx(root)
    success &= _tailwind_rewrite_header_jsx(root, config)
    success &= _tailwind_rewrite_login_prompt_jsx(root)
    print(f"  {Colors.CYAN}Suppression composants de démo...{Colors.ENDC}")
    success &= _clean_frontend_components(root)
    if success:
        print(f"\n  {Colors.GREEN}✅ Migration Tailwind terminée !{Colors.ENDC}")
        print(f"  {Colors.YELLOW}💡 Pensez à exécuter 'npm install' dans le dossier frontend{Colors.ENDC}")
    return success


def _tailwind_update_package_json(root: Path, config: dict) -> bool:
    filepath = root / 'frontend' / 'package.json'
    try:
        content = json.loads(filepath.read_text(encoding='utf-8'))
        content['name'] = f'{config["APP_SLUG"]}-frontend'
        content['version'] = '0.0.1'
        content.setdefault('devDependencies', {})
        content['devDependencies']['tailwindcss'] = '^4.1.0'
        content['devDependencies']['@tailwindcss/vite'] = '^4.1.0'
        filepath.write_text(json.dumps(content, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f"    {Colors.GREEN}✓ package.json mis à jour (Tailwind ajouté){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur package.json: {e}{Colors.ENDC}")
        return False


def _tailwind_create_configs(root: Path) -> bool:
    frontend = root / 'frontend'
    vite_config = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 3000
  },
  build: {
    outDir: 'dist',
    sourcemap: false
  }
})
"""
    try:
        (frontend / 'vite.config.js').write_text(vite_config, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ vite.config.js mis à jour{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur vite.config.js: {e}{Colors.ENDC}")
        return False


def _tailwind_rewrite_css(root: Path) -> bool:
    filepath = root / 'frontend' / 'src' / 'styles' / 'index.css'
    try:
        original = filepath.read_text(encoding='utf-8')
        message_css = _extract_message_css(original)
        content = f"""@import "tailwindcss";
@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));

:root {{
  --bg-primary: #f5f5f5;
  --bg-secondary: #ffffff;
  --text-primary: #333;
  --text-secondary: #666;
  --accent: #4a90d9;
  --success: #28a745;
  --error: #dc3545;
  --warning: #ffc107;
  --border: #ddd;
}}

[data-theme="dark"] {{
  --bg-primary: #1a1a2e;
  --bg-secondary: #16213e;
  --text-primary: #eee;
  --text-secondary: #aaa;
  --accent: #4a90d9;
  --border: #333;
}}

/* Styles messagerie Hub — partagés entre apps, ne pas modifier */

{message_css}
"""
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ index.css réécrit{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur index.css: {e}{Colors.ENDC}")
        return False


def _extract_message_css(css_content: str) -> str:
    lines = css_content.split('\n')
    result = []
    in_message_section = False
    brace_depth = 0
    for line in lines:
        if '/* ============ Message Banner' in line or '/* ============ Message Archive' in line:
            in_message_section = True
        if not in_message_section and ('.message-banner' in line or '.message-archive' in line):
            in_message_section = True
        if not in_message_section and '@keyframes messageBanner' in line:
            in_message_section = True
        if not in_message_section and '@keyframes messageArchive' in line:
            in_message_section = True
        if in_message_section:
            result.append(line)
            brace_depth += line.count('{') - line.count('}')
            if brace_depth <= 0:
                brace_depth = 0
                in_message_section = False
    return '\n'.join(result)


def _tailwind_rewrite_app_jsx(root: Path) -> bool:
    filepath = root / 'frontend' / 'src' / 'App.jsx'
    content = '''import React, { useState, useEffect } from 'react'
import { useConfig } from './context/ConfigContext'
import { useAuth } from './context/AuthContext'
import Header from './components/Header'
import LoginPrompt from './components/LoginPrompt'
import MessageBanner from './components/MessageBanner'
import MessageArchive from './components/MessageArchive'

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
      <div className="flex items-center justify-center h-screen text-lg text-gray-500 dark:text-gray-400">
        <p>Chargement de la configuration...</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-slate-900 text-gray-900 dark:text-gray-100 transition-colors">
      <Header theme={theme} toggleTheme={toggleTheme} />
      
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {!isAuthenticated ? (
          <LoginPrompt />
        ) : (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-blue-600 dark:text-blue-400 mb-2">
              Bienvenue {user?.username || user?.sub} !
            </h2>
            <p className="text-gray-600 dark:text-gray-300">
              Votre application est prête. Commencez à développer ici.
            </p>
          </div>
        )}
      </main>

      <MessageBanner />
      <MessageArchive />
    </div>
  )
}

export default App
'''
    try:
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ App.jsx réécrit (Tailwind){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur App.jsx: {e}{Colors.ENDC}")
        return False


def _tailwind_rewrite_header_jsx(root: Path, config: dict) -> bool:
    filepath = root / 'frontend' / 'src' / 'components' / 'Header.jsx'
    content = f"""import React, {{ useState, useEffect }} from 'react'
import {{ useConfig }} from '../context/ConfigContext'
import {{ useAuth }} from '../context/AuthContext'

function Header({{ theme, toggleTheme }}) {{
  const config = useConfig()
  const {{ isAuthenticated, login, logout }} = useAuth()
  const [hubStatus, setHubStatus] = useState({{ online: false, checking: true }})

  useEffect(() => {{
    checkHubStatus()
  }}, [config.hubApiUrl])

  const checkHubStatus = async () => {{
    try {{
      const response = await fetch(`${{config.hubApiUrl}}/api/auth/public-key`)
      setHubStatus({{ online: response.ok, checking: false }})
    }} catch {{
      setHubStatus({{ online: false, checking: false }})
    }}
  }}

  return (
    <header className="bg-white dark:bg-slate-800 shadow-sm px-4 sm:px-6 py-3 flex items-center justify-between">
      <h1 className="text-xl font-bold text-blue-600 dark:text-blue-400">
        🔐 {config['APP_NAME']}
      </h1>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm">
          <span className={{`w-2.5 h-2.5 rounded-full ${{
            hubStatus.checking ? 'bg-gray-300' :
            hubStatus.online ? 'bg-green-500' : 'bg-red-500'
          }}`}} />
          <span className="text-gray-600 dark:text-gray-300 hidden sm:inline">
            {{hubStatus.checking ? 'Vérification...' : hubStatus.online ? 'Hub connecté' : 'Hub indisponible'}}
          </span>
        </div>
        <button
          className="text-2xl leading-none p-1 hover:opacity-75 transition-opacity"
          onClick={{toggleTheme}}
          title="Changer le thème"
        >
          🌓
        </button>
        {{isAuthenticated ? (
          <button
            className="px-3 py-1.5 text-sm rounded-md bg-red-500 hover:bg-red-600 text-white transition-colors"
            onClick={{logout}}
          >
            Déconnexion
          </button>
        ) : (
          <button
            className="px-3 py-1.5 text-sm rounded-md bg-blue-500 hover:bg-blue-600 text-white transition-colors"
            onClick={{login}}
          >
            Connexion
          </button>
        )}}
      </div>
    </header>
  )
}}

export default Header
"""
    try:
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ Header.jsx réécrit (Tailwind){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur Header.jsx: {e}{Colors.ENDC}")
        return False


def _tailwind_rewrite_login_prompt_jsx(root: Path) -> bool:
    filepath = root / 'frontend' / 'src' / 'components' / 'LoginPrompt.jsx'
    content = """import React from 'react'
import { useAuth } from '../context/AuthContext'

function LoginPrompt() {
  const { login } = useAuth()

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-8 text-center max-w-md mx-auto">
      <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-3">
        Bienvenue !
      </h2>
      <p className="text-gray-500 dark:text-gray-400 mb-6">
        Connectez-vous via le Hub pour accéder à l'application.
      </p>
      <button
        className="px-5 py-2.5 rounded-md bg-blue-500 hover:bg-blue-600 text-white font-medium transition-colors"
        onClick={login}
      >
        Se connecter via le Hub
      </button>
    </div>
  )
}

export default LoginPrompt
"""
    try:
        filepath.write_text(content, encoding='utf-8')
        print(f"    {Colors.GREEN}✓ LoginPrompt.jsx réécrit (Tailwind){Colors.ENDC}")
        return True
    except Exception as e:
        print(f"    {Colors.RED}✗ Erreur LoginPrompt.jsx: {e}{Colors.ENDC}")
        return False


# ============================================================
# GÉNÉRATION DES SCRIPTS D'ACTION
# ============================================================
# Chaque action est composée de :
#   - Un module Python sous ACTIONS/PYTHON/<NAME>.py (logique réelle)
#   - Un wrapper bash sous ACTIONS/LINUX/<NAME>.sh
#   - Un wrapper batch sous ACTIONS/WINDOWS/<NAME>.bat

ACTION_NAMES = [
    "START", "STOP", "RESTART", "LOGS", "STATUS",
    "DELETE_DATA", "UPDATE", "BACKUP_DB",
    "SHELL_API", "SHELL_DB", "TEST", "COMMIT",
]

WRAPPER_SH = """#!/usr/bin/env bash
set -e
exec python3 "$(dirname "$0")/../PYTHON/{name}.py" "$@"
"""

WRAPPER_BAT = """@echo off
python "%~dp0..\\PYTHON\\{name}.py" %*
exit /b %errorlevel%
"""

COMMON_PY = '''"""
Helpers partagés par tous les scripts d'action.

Tous les scripts sous ACTIONS/PYTHON/ supposent que ce module existe.
La racine du projet est ACTIONS/PYTHON/<X>.py -> remonter 2 niveaux.
"""
import os
import sys
import subprocess
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_env() -> dict:
    """Charge .env (clé=valeur) en dictionnaire. Pas de substitution."""
    env_path = project_root() / ".env"
    result = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def compose(*args, check=True, capture=False) -> subprocess.CompletedProcess:
    """Lance `docker compose <args>` depuis la racine du projet."""
    cmd = ["docker", "compose", *args]
    print(f"\\n\\033[96m$ {' '.join(cmd)}\\033[0m")
    return subprocess.run(
        cmd,
        cwd=str(project_root()),
        check=check,
        capture_output=capture,
        text=True if capture else None,
    )


def parse_service(argv) -> str | None:
    """Retourne 'api', 'frontend' ou None selon les flags --fe / --be."""
    for a in argv[1:]:
        if a in ("--fe", "-fe", "--frontend"):
            return "frontend"
        if a in ("--be", "-be", "--backend", "--api"):
            return "api"
    return None


def parse_logs_target(argv) -> str | None:
    """Retourne 'api', 'frontend', 'postgres' ou None."""
    for a in argv[1:]:
        if a in ("--fe", "-fe", "--frontend"):
            return "frontend"
        if a in ("--be", "-be", "--backend", "--api"):
            return "api"
        if a in ("--db", "-db", "--postgres"):
            return "postgres"
    return None


def has_flag(argv, *flags) -> bool:
    return any(a in flags for a in argv[1:])


def confirm_typed(expected: str) -> bool:
    """Demande à l'utilisateur de retaper `expected` pour confirmer."""
    print(f"\\n\\033[91m⚠  Action destructive — tapez '{expected}' pour confirmer (sinon Entrée pour annuler):\\033[0m")
    try:
        answer = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer == expected


def red(msg): print(f"\\033[91m{msg}\\033[0m")
def green(msg): print(f"\\033[92m{msg}\\033[0m")
def yellow(msg): print(f"\\033[93m{msg}\\033[0m")
def cyan(msg): print(f"\\033[96m{msg}\\033[0m")
'''


# Templates des actions générées (logique métier)
def _action_template(name: str) -> str:
    if name == "START":
        return '''"""START : down complet puis build + up -d.
Avec --fe / --be : down complet puis build + up -d --no-deps du service ciblé.
"""
import sys
from _common import compose, parse_service, cyan, green, red


def main():
    svc = parse_service(sys.argv)
    cyan("→ Arrêt complet de la stack")
    compose("down")
    if svc:
        cyan(f"→ Build du service '{svc}' uniquement")
        compose("build", svc)
        cyan(f"→ Démarrage du service '{svc}' (--no-deps)")
        compose("up", "-d", "--no-deps", svc)
    else:
        cyan("→ Build de toutes les images")
        compose("build")
        cyan("→ Démarrage de la stack complète")
        compose("up", "-d")
    green("✓ Démarrage terminé")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "STOP":
        return '''"""STOP : docker compose down."""
import sys
from _common import compose, green, red


def main():
    compose("down")
    green("✓ Stack arrêtée")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "RESTART":
        return '''"""RESTART [--fe|--be] : docker compose restart [service]."""
import sys
from _common import compose, parse_service, green, red, cyan


def main():
    svc = parse_service(sys.argv)
    if svc:
        cyan(f"→ Redémarrage du service '{svc}'")
        compose("restart", svc)
    else:
        cyan("→ Redémarrage de tous les services")
        compose("restart")
    green("✓ Redémarrage terminé")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "LOGS":
        return '''"""LOGS [--fe|--be|--db] : suit les logs (-f par défaut en TTY)."""
import sys
from _common import compose, parse_logs_target, has_flag, red


def main():
    target = parse_logs_target(sys.argv)
    follow = has_flag(sys.argv, "-f", "--follow") or sys.stdout.isatty()
    args = ["logs"]
    if follow:
        args.append("-f")
    args.extend(["--tail", "200"])
    if target:
        args.append(target)
    try:
        compose(*args)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "STATUS":
        return '''"""STATUS : docker compose ps + health check API."""
import sys
import urllib.request
import urllib.error
from _common import compose, load_env, green, red, yellow, cyan


def main():
    cyan("→ État des conteneurs")
    compose("ps")
    env = load_env()
    api_port = env.get("API_PORT", "9045")
    url = f"http://localhost:{api_port}/api/health"
    cyan(f"\\n→ Health check : {url}")
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            body = r.read().decode("utf-8", errors="replace")
            if r.status == 200:
                green(f"✓ API healthy ({r.status})")
                print(body)
            else:
                yellow(f"⚠ API HTTP {r.status}")
                print(body)
    except urllib.error.URLError as e:
        red(f"✗ API injoignable: {e}")
    except Exception as e:
        red(f"✗ Erreur health check: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "DELETE_DATA":
        return '''"""DELETE_DATA : docker compose down -v (DESTRUCTIF).
Confirmation : retaper APP_SLUG.
"""
import sys
from _common import compose, load_env, confirm_typed, red, yellow, green


def main():
    env = load_env()
    slug = env.get("APP_SLUG", "")
    if not slug:
        red("✗ Impossible de lire APP_SLUG dans .env")
        sys.exit(1)
    yellow(f"⚠  Cette action va SUPPRIMER les volumes Docker de '{slug}' :")
    yellow("   • postgres_data (toute la base de données)")
    yellow("   • uploads_data  (tous les fichiers uploadés)")
    if not confirm_typed(slug):
        red("✗ Annulé.")
        sys.exit(1)
    compose("down", "-v")
    green("✓ Volumes supprimés")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "UPDATE":
        return '''"""UPDATE : git pull --ff-only puis build + up -d."""
import sys
import subprocess
from _common import project_root, compose, cyan, green, red, yellow


def main():
    root = project_root()
    cyan("→ Vérification de l'état Git")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),
                            capture_output=True, text=True, check=True)
    if status.stdout.strip():
        red("✗ Working tree non propre, abort. Committez ou stashez d'abord.")
        print(status.stdout)
        sys.exit(1)
    cyan("→ git pull --ff-only")
    r = subprocess.run(["git", "pull", "--ff-only"], cwd=str(root))
    if r.returncode != 0:
        red("✗ git pull a échoué (conflits ou non fast-forward).")
        sys.exit(1)
    cyan("→ Build des images")
    compose("build")
    cyan("→ Up -d")
    compose("up", "-d")
    green("✓ Mise à jour terminée")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        red(f"✗ Commande échouée: {e}")
        sys.exit(e.returncode or 1)
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "BACKUP_DB":
        return '''"""BACKUP_DB : pg_dump → ./backups/<slug>-YYYYMMDD-HHMMSS.sql.gz"""
import sys
import gzip
import subprocess
from datetime import datetime
from _common import project_root, load_env, cyan, green, red


def main():
    env = load_env()
    slug = env.get("APP_SLUG", "app")
    pg_user = env.get("POSTGRES_USER", "app_user")
    pg_db = env.get("POSTGRES_DB", "app_db")
    backups_dir = project_root() / "backups"
    backups_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = backups_dir / f"{slug}-{ts}.sql.gz"
    cyan(f"→ Dump PostgreSQL → {out.name}")
    cmd = ["docker", "compose", "exec", "-T", "postgres",
           "pg_dump", "-U", pg_user, "-d", pg_db]
    proc = subprocess.Popen(cmd, cwd=str(project_root()),
                            stdout=subprocess.PIPE)
    try:
        with gzip.open(out, "wb") as gz:
            assert proc.stdout is not None
            for chunk in iter(lambda: proc.stdout.read(64 * 1024), b""):
                gz.write(chunk)
        rc = proc.wait()
    except Exception:
        proc.kill()
        raise
    if rc != 0:
        red(f"✗ pg_dump a échoué (code {rc})")
        out.unlink(missing_ok=True)
        sys.exit(rc)
    size_mb = out.stat().st_size / (1024 * 1024)
    green(f"✓ Backup créé: {out} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "SHELL_API":
        return '''"""SHELL_API : ouvre un shell dans le conteneur api (bash, fallback sh)."""
import sys
import subprocess
from _common import project_root, red


def main():
    root = str(project_root())
    for shell in ("bash", "sh"):
        r = subprocess.run(
            ["docker", "compose", "exec", "api", "which", shell],
            cwd=root, capture_output=True, text=True
        )
        if r.returncode == 0:
            subprocess.run(["docker", "compose", "exec", "api", shell], cwd=root)
            return
    red("✗ Aucun shell trouvé dans le conteneur api")
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "SHELL_DB":
        return '''"""SHELL_DB : psql dans le conteneur postgres."""
import sys
import subprocess
from _common import project_root, load_env, red


def main():
    env = load_env()
    pg_user = env.get("POSTGRES_USER", "app_user")
    pg_db = env.get("POSTGRES_DB", "app_db")
    subprocess.run(
        ["docker", "compose", "exec", "postgres", "psql", "-U", pg_user, "-d", pg_db],
        cwd=str(project_root())
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "TEST":
        return '''"""TEST : pytest dans le conteneur api. Args supplémentaires passés à pytest."""
import sys
import subprocess
from _common import project_root, red


def main():
    extra = sys.argv[1:]
    cmd = ["docker", "compose", "exec", "api", "python", "-m", "pytest", "-v", *extra]
    r = subprocess.run(cmd, cwd=str(project_root()))
    sys.exit(r.returncode)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    if name == "COMMIT":
        return r'''"""COMMIT : bump version + CHANGELOG.md + git commit.

Sources possibles du message de commit, dans l'ordre :
1. `-m/--message "..."`
2. variable d'environnement `AI_COMMIT_MESSAGE`
3. commande externe `AI_COMMIT_CMD` (reçoit le diff staged sur stdin)
4. saisie interactive
5. message fallback basé sur les fichiers modifiés

Exemples :
  python ACTIONS/PYTHON/COMMIT.py -m "feat: add billing page"
  python ACTIONS/PYTHON/COMMIT.py --minor -m "feat: add export module"
  AI_COMMIT_CMD='mods --format plain' python ACTIONS/PYTHON/COMMIT.py
"""
import os
import re
import sys
import tempfile
import subprocess
from datetime import datetime
from _common import project_root, green, red, yellow, cyan


MONTHS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}

CATEGORY_BY_TYPE = {
    "feat": "✨ Nouvelles fonctionnalités",
    "fix": "🐛 Corrections",
    "docs": "📝 Documentation",
    "refactor": "🔧 Modifications code",
    "perf": "🔧 Modifications code",
    "test": "🧪 Tests",
    "chore": "🔧 Modifications code",
    "build": "🔧 Modifications code",
    "ci": "🔧 Modifications code",
    "style": "🔧 Modifications code",
}


def usage():
    print("""Usage:
  COMMIT [-m "message"] [--patch|--minor|--major|--no-bump] [--no-stage] [--no-ai] [--dry-run] [--no-verify]

Par défaut :
  - stage tous les changements (`git add -A`)
  - génère/récupère le message si `-m` absent
  - incrémente VERSION en patch
  - alimente CHANGELOG.md avec le message final
  - synchronise les versions via scripts/bump_version.py
  - crée le commit Git

Variables IA optionnelles :
  AI_COMMIT_MESSAGE="feat: ..."        Message déjà généré par l'IA
  AI_COMMIT_CMD="commande ..."         Commande externe recevant le diff staged sur stdin
""")


def parse_args(argv):
    opts = {
        "messages": [],
        "bump": "patch",
        "stage": True,
        "use_ai": True,
        "dry_run": False,
        "no_verify": False,
    }
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            usage()
            sys.exit(0)
        if arg in ("-m", "--message"):
            i += 1
            if i >= len(argv):
                red("✗ -m/--message nécessite une valeur")
                sys.exit(1)
            opts["messages"].append(argv[i])
        elif arg == "--patch":
            opts["bump"] = "patch"
        elif arg == "--minor":
            opts["bump"] = "minor"
        elif arg == "--major":
            opts["bump"] = "major"
        elif arg == "--no-bump":
            opts["bump"] = None
        elif arg == "--no-stage":
            opts["stage"] = False
        elif arg == "--no-ai":
            opts["use_ai"] = False
        elif arg == "--dry-run":
            opts["dry_run"] = True
        elif arg == "--no-verify":
            opts["no_verify"] = True
        else:
            red(f"✗ Argument inconnu: {arg}")
            usage()
            sys.exit(1)
        i += 1
    return opts


def git(*args, capture=False, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=str(project_root()),
        capture_output=capture,
        text=True,
        check=check,
    )


def staged_has_changes() -> bool:
    return git("diff", "--cached", "--quiet", check=False).returncode != 0


def staged_diff_payload() -> str:
    stat = git("diff", "--cached", "--stat", capture=True).stdout
    names = git("diff", "--cached", "--name-status", capture=True).stdout
    patch = git("diff", "--cached", capture=True).stdout
    if len(patch) > 120000:
        patch = patch[:120000] + "\n\n[diff tronqué pour génération du message]"
    return (
        "Tu es un assistant de commit Git. Génère un message de commit clair, "
        "court, en anglais ou français selon le contexte, idéalement au format Conventional Commits.\n\n"
        "Contraintes : première ligne <= 72 caractères, corps optionnel, pas de markdown.\n\n"
        f"STAT:\n{stat}\n\nFILES:\n{names}\n\nDIFF:\n{patch}\n"
    )


def clean_ai_message(raw: str) -> str:
    msg = raw.strip()
    if not msg:
        return ""
    msg = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", msg)
    msg = re.sub(r"\n```$", "", msg)
    msg = re.sub(r"^(commit message|message de commit)\s*:\s*", "", msg, flags=re.I)
    return msg.strip().strip('"').strip("'")


def ai_message_from_command(payload: str) -> str | None:
    cmd = os.environ.get("AI_COMMIT_CMD", "").strip()
    if not cmd:
        return None
    cyan(f"→ Génération du message via AI_COMMIT_CMD: {cmd}")
    result = subprocess.run(
        cmd,
        cwd=str(project_root()),
        input=payload,
        capture_output=True,
        text=True,
        shell=True,
    )
    if result.returncode != 0:
        yellow("⚠ AI_COMMIT_CMD a échoué, fallback interactif/fichiers.")
        if result.stderr.strip():
            print(result.stderr.strip())
        return None
    return clean_ai_message(result.stdout)


def fallback_message() -> str:
    files = [line.strip() for line in git("diff", "--cached", "--name-only", capture=True).stdout.splitlines() if line.strip()]
    if not files:
        return "chore: update project"
    if len(files) == 1:
        return f"chore: update {files[0]}"
    return f"chore: update {len(files)} files"


def resolve_commit_message(opts) -> str:
    if opts["messages"]:
        return clean_ai_message("\n\n".join(opts["messages"]))
    env_message = os.environ.get("AI_COMMIT_MESSAGE", "").strip()
    if env_message:
        cyan("→ Message récupéré depuis AI_COMMIT_MESSAGE")
        return clean_ai_message(env_message)
    if opts["use_ai"]:
        generated = ai_message_from_command(staged_diff_payload())
        if generated:
            return generated
    if sys.stdin.isatty():
        try:
            typed = input("Message de commit (Entrée = fallback automatique): ").strip()
        except (EOFError, KeyboardInterrupt):
            typed = ""
        if typed:
            return clean_ai_message(typed)
    return fallback_message()


def read_version() -> str:
    version_file = project_root() / "VERSION"
    if not version_file.exists():
        return "0.0.0"
    return version_file.read_text(encoding="utf-8").strip()


def bump_version(current: str, bump_type: str | None) -> str:
    if bump_type is None:
        return current
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", current)
    if not match:
        red(f"✗ Version invalide dans VERSION: {current}")
        sys.exit(1)
    major, minor, patch = map(int, match.groups())
    if bump_type == "major":
        return f"{major + 1}.0.0"
    if bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def changelog_category(message: str) -> str:
    subject = first_subject_line(message)
    match = re.match(r"^([a-zA-Z]+)(\([^)]+\))?!?:\s+", subject)
    if not match:
        return "📝 Modifications"
    return CATEGORY_BY_TYPE.get(match.group(1).lower(), "📝 Modifications")


def first_subject_line(message: str) -> str:
    for line in message.splitlines():
        line = line.strip()
        if line:
            return line
    return "chore: update project"


def changelog_summary(message: str) -> str:
    subject = first_subject_line(message)
    subject = re.sub(r"^[a-zA-Z]+(\([^)]+\))?!?:\s+", "", subject).strip()
    return subject[:1].upper() + subject[1:] if subject else "Mise à jour du projet"


def today_fr() -> str:
    now = datetime.now()
    return f"{now.day} {MONTHS_FR[now.month]} {now.year}"


def add_entry_to_existing_version(content: str, version: str, category: str, bullet: str) -> str | None:
    section_match = re.search(rf"(## \[{re.escape(version)}\].*?)(?=\n---\n\n## \[|\n## \[|\Z)", content, flags=re.S)
    if not section_match:
        return None
    section = section_match.group(1)
    if bullet in section:
        return content
    header = f"### {category}"
    if header in section:
        new_section = section.replace(header, f"{header}\n\n{bullet}", 1)
    else:
        new_section = section.rstrip() + f"\n\n{header}\n\n{bullet}\n"
    return content[:section_match.start(1)] + new_section + content[section_match.end(1):]


def insert_new_changelog_section(content: str, section: str) -> str:
    unreleased = re.search(r"(## \[Unreleased\].*?\n---\n\n)", content, flags=re.S)
    if unreleased:
        return content[:unreleased.end(1)] + section + content[unreleased.end(1):]
    marker = "\n---\n\n"
    if marker in content:
        index = content.index(marker) + len(marker)
        return content[:index] + section + content[index:]
    return content.rstrip() + "\n\n" + section.rstrip() + "\n"


def update_changelog(version: str, message: str) -> None:
    changelog = project_root() / "CHANGELOG.md"
    if not changelog.exists():
        changelog.write_text("# Changelog\n\n---\n\n", encoding="utf-8")
    content = changelog.read_text(encoding="utf-8")
    category = changelog_category(message)
    bullet = f"- {changelog_summary(message)}"
    updated = add_entry_to_existing_version(content, version, category, bullet)
    if updated is None:
        section = f"## [{version}] - {today_fr()}\n\n### {category}\n\n{bullet}\n\n---\n\n"
        updated = insert_new_changelog_section(content, section)
    changelog.write_text(updated, encoding="utf-8")
    green(f"✓ CHANGELOG.md alimenté pour {version}")


def sync_version(bump_type: str | None) -> None:
    script = project_root() / "scripts" / "bump_version.py"
    if not script.exists():
        yellow("⚠ scripts/bump_version.py introuvable, VERSION/CHANGELOG seuls seront utilisés")
        return
    args = [sys.executable, str(script)]
    if bump_type is not None:
        args.append(bump_type)
    cyan(f"→ Synchronisation version: {' '.join(args)}")
    subprocess.run(args, cwd=str(project_root()), check=True)


def commit_with_message(message: str, no_verify: bool) -> int:
    commit_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    try:
        commit_file.write(message.strip() + "\n")
        commit_file.close()
        cmd = ["git", "commit", "-F", commit_file.name]
        if no_verify:
            cmd.append("--no-verify")
        return subprocess.run(cmd, cwd=str(project_root())).returncode
    finally:
        try:
            os.unlink(commit_file.name)
        except OSError:
            pass


def main():
    opts = parse_args(sys.argv)
    root = project_root()
    if not (root / ".git").exists():
        red("✗ Ce dossier n'est pas un dépôt Git")
        sys.exit(1)
    if opts["stage"]:
        cyan("→ Stage de tous les changements (git add -A)")
        git("add", "-A")
    if not staged_has_changes():
        red("✗ Aucun changement staged à committer")
        sys.exit(1)

    message = resolve_commit_message(opts)
    current_version = read_version()
    next_version = bump_version(current_version, opts["bump"])

    cyan("\nMessage de commit retenu:")
    print(message)
    cyan(f"\nVersion: {current_version} -> {next_version}")

    if opts["dry_run"]:
        yellow("--dry-run actif : aucun fichier modifié, aucun commit créé.")
        return

    update_changelog(next_version, message)
    sync_version(opts["bump"])
    git("add", "-A")

    rc = commit_with_message(message, opts["no_verify"])
    if rc != 0:
        red(f"✗ git commit a échoué (code {rc})")
        sys.exit(rc)
    green(f"✓ Commit créé pour la version {next_version}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        red(f"✗ Commande échouée: {e}")
        sys.exit(e.returncode or 1)
    except Exception as e:
        red(f"✗ Erreur: {e}")
        sys.exit(1)
'''
    raise ValueError(f"Aucun template pour {name}")


def _make_executable(path: Path) -> None:
    if sys.platform == "win32":
        return
    try:
        st = path.stat()
        path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass


def _generate_action_scripts(root: Path) -> bool:
    print(f"\n{Colors.BOLD}🛠️  Génération des scripts d'action...{Colors.ENDC}\n")
    py_dir = root / "ACTIONS" / "PYTHON"
    sh_dir = root / "ACTIONS" / "LINUX"
    bat_dir = root / "ACTIONS" / "WINDOWS"
    for d in (py_dir, sh_dir, bat_dir):
        d.mkdir(parents=True, exist_ok=True)
    success = True
    # _common.py
    try:
        common_path = py_dir / "_common.py"
        common_path.write_text(COMMON_PY, encoding="utf-8")
        print(f"  {Colors.GREEN}✓ ACTIONS/PYTHON/_common.py{Colors.ENDC}")
    except Exception as e:
        print(f"  {Colors.RED}✗ _common.py: {e}{Colors.ENDC}")
        success = False
    # Actions
    for name in ACTION_NAMES:
        try:
            (py_dir / f"{name}.py").write_text(_action_template(name), encoding="utf-8")
            (sh_dir / f"{name}.sh").write_text(WRAPPER_SH.format(name=name), encoding="utf-8")
            _make_executable(sh_dir / f"{name}.sh")
            (bat_dir / f"{name}.bat").write_text(WRAPPER_BAT.format(name=name), encoding="utf-8")
            print(f"  {Colors.GREEN}✓ {name}{Colors.ENDC} (.py + .sh + .bat)")
        except Exception as e:
            print(f"  {Colors.RED}✗ {name}: {e}{Colors.ENDC}")
            success = False
    return success


def _self_destruct(root: Path) -> None:
    print(f"\n{Colors.YELLOW}🗑️  Auto-suppression du script d'initialisation...{Colors.ENDC}")
    targets = [
        root / "INITIALISE.py",
        root / "INITIALISE.sh",
        root / "INITIALISE.bat",
        root / "ACTIONS" / "LINUX" / "INITIALISE.sh",
        root / "ACTIONS" / "WINDOWS" / "INITIALISE.bat",
        root / "ACTIONS" / "PYTHON" / "INITIALISE.py",
    ]
    for t in targets:
        try:
            if t.exists():
                t.unlink()
                print(f"  {Colors.GREEN}✓ Supprimé {t.relative_to(root)}{Colors.ENDC}")
        except Exception as e:
            # Sous Windows, INITIALISE.bat peut être verrouillé par cmd.exe.
            print(f"  {Colors.YELLOW}⚠ {t.relative_to(root)}: {e} — supprimez manuellement si nécessaire{Colors.ENDC}")


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        parsed_options = parse_cli_options(sys.argv[1:])
    except ValueError as exc:
        print(f"{Colors.RED}✗ {exc}{Colors.ENDC}")
        return 1

    clean_mode = '--clean' in parsed_options['args']
    tailwind_mode = '--tailwind' in parsed_options['args']

    print_header()

    if tailwind_mode:
        print(f"{Colors.YELLOW}🎨 Mode --tailwind : migration React + Tailwind CSS{Colors.ENDC}")
        print(f"{Colors.YELLOW}🧹 Le contenu de démonstration sera également supprimé{Colors.ENDC}\n")
    elif clean_mode:
        print(f"{Colors.YELLOW}🧹 Mode --clean : le contenu de démonstration sera supprimé{Colors.ENDC}\n")

    root = get_project_root()
    if not (root / 'docker-compose.yml').exists():
        print(f"{Colors.RED}✗ Erreur: docker-compose.yml introuvable depuis {root}{Colors.ENDC}")
        sys.exit(1)

    config = collect_app_info(parsed_options)

    clean_mode = clean_mode or config.get('CLEAN_DEMO', False)
    tailwind_mode = tailwind_mode or config.get('USE_TAILWIND', False)

    if not confirm_settings(config):
        print(f"\n{Colors.YELLOW}Opération annulée.{Colors.ENDC}")
        sys.exit(0)

    print(f"\n{Colors.BOLD}🔄 Application des modifications...{Colors.ENDC}\n")

    success = True
    print(f"{Colors.CYAN}[1/14] Création .env{Colors.ENDC}")
    success &= create_env_file(root, config)
    print(f"{Colors.CYAN}[2/14] Mise à jour .env.example{Colors.ENDC}")
    success &= update_env_example(root, config)
    print(f"{Colors.CYAN}[3/14] Mise à jour docker-compose.yml{Colors.ENDC}")
    success &= update_docker_compose(root, config)
    print(f"{Colors.CYAN}[4/14] Mise à jour backend/config.py{Colors.ENDC}")
    success &= update_backend_config(root, config)
    print(f"{Colors.CYAN}[5/14] Mise à jour Dockerfile.frontend{Colors.ENDC}")
    success &= update_dockerfile_frontend(root, config)
    print(f"{Colors.CYAN}[6/14] Mise à jour frontend/index.html{Colors.ENDC}")
    success &= update_frontend_index(root, config)
    print(f"{Colors.CYAN}[7/14] Mise à jour frontend/Header.jsx{Colors.ENDC}")
    success &= update_frontend_header(root, config)
    print(f"{Colors.CYAN}[8/14] Mise à jour frontend/package.json{Colors.ENDC}")
    success &= update_frontend_package_json(root, config)
    print(f"{Colors.CYAN}[9/14] Mise à jour frontend/src/config.js{Colors.ENDC}")
    success &= update_frontend_config_js(root, config)
    print(f"{Colors.CYAN}[10/14] Mise à jour fixtures de test{Colors.ENDC}")
    success &= update_test_fixtures(root, config)
    print(f"{Colors.CYAN}[11/14] Réinitialisation VERSION{Colors.ENDC}")
    success &= create_version_file(root)
    print(f"{Colors.CYAN}[12/14] Réinitialisation documentation{Colors.ENDC}")
    success &= create_changelog(root, config)
    success &= create_readme(root, config)
    print(f"{Colors.CYAN}[13/14] Nettoyage fichiers obsolètes{Colors.ENDC}")
    success &= cleanup_obsolete_files(root)
    print(f"{Colors.CYAN}[14/14] Génération LICENSE.md{Colors.ENDC}")
    success &= create_license_file(root, config)

    use_tailwind = config.get('USE_TAILWIND', False) or tailwind_mode
    if use_tailwind or clean_mode:
        success &= clean_demo_content(root, config)
    if use_tailwind:
        success &= setup_tailwind(root, config)

    if not success:
        print(f"\n{Colors.YELLOW}⚠ Initialisation terminée avec des avertissements.{Colors.ENDC}")
        print(f"{Colors.YELLOW}   Les scripts d'action ne seront PAS générés ni l'auto-suppression effectuée.{Colors.ENDC}")
        return 1

    # Génération des scripts d'action et auto-suppression (uniquement si tout OK)
    if not _generate_action_scripts(root):
        print(f"\n{Colors.YELLOW}⚠ Génération des scripts incomplète. Auto-suppression annulée.{Colors.ENDC}")
        return 1

    print(f"\n{'═' * 60}")
    print(f"""
{Colors.GREEN}✅ Initialisation terminée avec succès !{Colors.ENDC}

{Colors.BOLD}Prochaines étapes :{Colors.ENDC}

  1. Vérifier la configuration :
     {Colors.CYAN}cat .env{Colors.ENDC}

  2. Démarrer l'application :
     {Colors.CYAN}bash ACTIONS/LINUX/START.sh{Colors.ENDC}    (Linux/macOS)
     {Colors.CYAN}ACTIONS\\WINDOWS\\START.bat{Colors.ENDC}     (Windows)

  3. Accéder à l'application :
     • Frontend : {Colors.BLUE}http://localhost:{config['FRONTEND_PORT']}{Colors.ENDC}
     • API :      {Colors.BLUE}http://localhost:{config['API_PORT']}{Colors.ENDC}
     • Docs :     {Colors.BLUE}http://localhost:{config['API_PORT']}/docs{Colors.ENDC}

  4. Voir toutes les actions disponibles : {Colors.CYAN}ls ACTIONS/LINUX/{Colors.ENDC}
""")
    if use_tailwind:
        print(f"  {Colors.YELLOW}💡 Pour le développement local hors Docker : cd frontend && npm install{Colors.ENDC}\n")

    _self_destruct(root)
    return 0


if __name__ == '__main__':
    sys.exit(main())

