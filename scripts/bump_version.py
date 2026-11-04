#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
Script de gestion de version automatique.

Ce script synchronise le numéro de version depuis le fichier VERSION
vers tous les fichiers du projet qui en ont besoin.

Usage:
    python scripts/bump_version.py                  # Synchronise la version actuelle
    python scripts/bump_version.py patch            # 1.5.0 -> 1.5.1
    python scripts/bump_version.py minor            # 1.5.0 -> 1.6.0
    python scripts/bump_version.py major            # 1.5.0 -> 2.0.0
    python scripts/bump_version.py --set 2.0.0      # Force une version spécifique
    python scripts/bump_version.py --check          # Vérifie la cohérence des versions

Le script met à jour automatiquement :
    - VERSION (fichier source de vérité)
    - frontend/package.json
    - backend/main.py (version FastAPI)
    - .env.example et .env (APP_VERSION)
    - docs/API.md (badge de version)
    - Valide que CHANGELOG.md contient une entrée pour la version
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


# Chemin racine du projet (parent du dossier scripts)
ROOT_DIR = Path(__file__).parent.parent
VERSION_FILE = ROOT_DIR / "VERSION"


def read_version() -> str:
    """Lit la version depuis le fichier VERSION."""
    if not VERSION_FILE.exists():
        print(f"❌ Fichier VERSION introuvable à {VERSION_FILE}")
        sys.exit(1)
    return VERSION_FILE.read_text().strip()


def write_version(version: str) -> None:
    """Écrit la version dans le fichier VERSION."""
    VERSION_FILE.write_text(f"{version}\n")
    print(f"✅ VERSION: {version}")


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse une version semver en tuple (major, minor, patch)."""
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version)
    if not match:
        print(f"❌ Version invalide: {version} (format attendu: X.Y.Z)")
        sys.exit(1)
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(current: str, bump_type: str) -> str:
    """Incrémente la version selon le type (major, minor, patch)."""
    major, minor, patch = parse_version(current)
    
    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        print(f"❌ Type de bump invalide: {bump_type}")
        sys.exit(1)


def update_package_json(version: str) -> bool:
    """Met à jour la version dans frontend/package.json."""
    package_path = ROOT_DIR / "frontend" / "package.json"
    if not package_path.exists():
        print(f"⚠️  package.json non trouvé, ignoré")
        return False
    
    with open(package_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    old_version = data.get("version", "0.0.0")
    data["version"] = version
    
    with open(package_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    
    print(f"✅ frontend/package.json: {old_version} -> {version}")
    return True


def update_main_py(version: str) -> bool:
    """Met à jour la version dans backend/main.py (FastAPI app).
    
    Note: Si la version est définie via APP_VERSION (lu depuis le fichier VERSION),
    ce fichier n'a pas besoin d'être modifié — la synchronisation est automatique.
    """
    main_path = ROOT_DIR / "backend" / "main.py"
    if not main_path.exists():
        print(f"⚠️  main.py non trouvé, ignoré")
        return False
    
    content = main_path.read_text(encoding='utf-8')
    
    # Pattern pour trouver version="X.Y.Z" en dur dans FastAPI
    pattern = r'(version\s*=\s*["\'])[\d]+\.[\d]+\.[\d]+(["\'])'
    new_content = re.sub(pattern, rf'\g<1>{version}\g<2>', content)
    
    if content == new_content:
        # Vérifier si la version est définie via APP_VERSION (variable)
        if "version=APP_VERSION" in content or "version = APP_VERSION" in content:
            print(f"✅ backend/main.py: version via APP_VERSION (fichier VERSION)")
            return True
        print(f"⚠️  backend/main.py: pattern de version non trouvé")
        return False
    
    main_path.write_text(new_content, encoding='utf-8')
    print(f"✅ backend/main.py: version={version}")
    return True


def update_api_docs(version: str) -> bool:
    """Met à jour la version dans docs/API.md.
    
    Gère le badge de version en haut du fichier :
    - Si un ou plusieurs badges existent, les remplace par un seul avec la nouvelle version
    - Si aucun badge n'existe, en ajoute un après le titre
    """
    api_path = ROOT_DIR / "docs" / "API.md"
    if not api_path.exists():
        print(f"⚠️  docs/API.md non trouvé, ignoré")
        return False
    
    content = api_path.read_text(encoding='utf-8')
    
    # Supprimer TOUS les badges de version existants (y compris les doublons)
    # et les lignes vides autour
    badge_pattern = r'\n*!\[Version\]\(https://img\.shields\.io/badge/version-[\d]+\.[\d]+\.[\d]+-blue\)\s*'
    content_cleaned = re.sub(badge_pattern, '\n', content)
    
    # Mettre à jour les patterns textuels "Version: X.Y.Z" ou "**Version**: X.Y.Z"
    patterns = [
        (r'(\*\*Version\*\*\s*:\s*)[\d]+\.[\d]+\.[\d]+', rf'\g<1>{version}'),
        (r'(Version\s*:\s*)[\d]+\.[\d]+\.[\d]+', rf'\g<1>{version}'),
    ]
    
    for pattern, replacement in patterns:
        content_cleaned = re.sub(pattern, replacement, content_cleaned)
    
    # Réinsérer UN SEUL badge après le titre
    lines = content_cleaned.split('\n')
    badge_line = f"![Version](https://img.shields.io/badge/version-{version}-blue)"
    
    if lines and lines[0].startswith('# '):
        # Insérer après le titre avec une ligne vide
        lines.insert(1, '')
        lines.insert(2, badge_line)
        # Nettoyer les lignes vides multiples consécutives
        result_lines = []
        prev_empty = False
        for line in lines:
            is_empty = line.strip() == ''
            if is_empty and prev_empty:
                continue
            result_lines.append(line)
            prev_empty = is_empty
        content_cleaned = '\n'.join(result_lines)
    
    api_path.write_text(content_cleaned, encoding='utf-8')
    print(f"✅ docs/API.md: version={version}")
    return True


def update_env_versions(version: str) -> bool:
    """Synchronise APP_VERSION dans .env.example et .env si présents."""
    updated_any = False

    for filename in (".env.example", ".env"):
        env_path = ROOT_DIR / filename
        if not env_path.exists():
            continue

        content = env_path.read_text(encoding='utf-8')
        if re.search(r'^APP_VERSION=.*$', content, flags=re.MULTILINE):
            new_content = re.sub(r'^APP_VERSION=.*$', f'APP_VERSION={version}', content, flags=re.MULTILINE)
        else:
            insertion = f"\n# === VERSION ===\n# Synchronisé automatiquement depuis le fichier VERSION\nAPP_VERSION={version}\n"
            if "APP_DESCRIPTION=" in content:
                new_content = re.sub(
                    r'^(APP_DESCRIPTION=.*)$',
                    rf'\1{insertion.rstrip()}',
                    content,
                    flags=re.MULTILINE
                )
            else:
                new_content = content.rstrip() + insertion

        if new_content != content:
            env_path.write_text(new_content, encoding='utf-8')

        print(f"✅ {filename}: APP_VERSION={version}")
        updated_any = True

    if not updated_any:
        print("⚠️  Aucun fichier .env.example/.env trouvé pour synchroniser APP_VERSION")

    return updated_any


def check_changelog(version: str) -> bool:
    """Vérifie que le CHANGELOG.md contient une entrée pour cette version."""
    changelog_path = ROOT_DIR / "CHANGELOG.md"
    if not changelog_path.exists():
        print(f"⚠️  CHANGELOG.md non trouvé")
        return False
    
    content = changelog_path.read_text(encoding='utf-8')
    
    # Cherche ## [X.Y.Z] dans le changelog
    pattern = rf'##\s*\[{re.escape(version)}\]'
    if re.search(pattern, content):
        print(f"✅ CHANGELOG.md: entrée ['{version}'] trouvée")
        return True
    else:
        print(f"⚠️  CHANGELOG.md: aucune entrée pour [{version}]")
        print(f"   💡 Ajoutez une section '## [{version}] - {datetime.now().strftime('%d %B %Y')}' dans CHANGELOG.md")
        return False


def check_version_consistency() -> bool:
    """Vérifie que toutes les versions sont cohérentes."""
    version = read_version()
    print(f"\n🔍 Vérification de cohérence pour version {version}\n")
    
    all_ok = True
    
    # Check package.json
    package_path = ROOT_DIR / "frontend" / "package.json"
    if package_path.exists():
        with open(package_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        pkg_version = data.get("version", "?")
        if pkg_version == version:
            print(f"✅ frontend/package.json: {pkg_version}")
        else:
            print(f"❌ frontend/package.json: {pkg_version} (attendu: {version})")
            all_ok = False
    
    # Check main.py
    main_path = ROOT_DIR / "backend" / "main.py"
    if main_path.exists():
        content = main_path.read_text(encoding='utf-8')
        match = re.search(r'version\s*=\s*["\'](\d+\.\d+\.\d+)["\']', content)
        if match:
            main_version = match.group(1)
            if main_version == version:
                print(f"✅ backend/main.py: {main_version}")
            else:
                print(f"❌ backend/main.py: {main_version} (attendu: {version})")
                all_ok = False
        elif "version=APP_VERSION" in content or "version = APP_VERSION" in content:
            print(f"✅ backend/main.py: version via APP_VERSION (fichier VERSION)")

    env_example_path = ROOT_DIR / ".env.example"
    if env_example_path.exists():
        env_example = env_example_path.read_text(encoding='utf-8')
        match = re.search(r'^APP_VERSION=(.+)$', env_example, flags=re.MULTILINE)
        if match and match.group(1).strip() == version:
            print(f"✅ .env.example: APP_VERSION={version}")
        else:
            print(f"❌ .env.example: APP_VERSION incohérent (attendu: {version})")
            all_ok = False
    
    # Check changelog
    if not check_changelog(version):
        all_ok = False
    
    print()
    if all_ok:
        print("✅ Toutes les versions sont synchronisées!")
    else:
        print("❌ Incohérences détectées. Exécutez 'python scripts/bump_version.py' pour synchroniser.")
    
    return all_ok


def sync_all(version: str) -> None:
    """Synchronise la version dans tous les fichiers."""
    print(f"\n📦 Synchronisation vers version {version}\n")
    
    update_package_json(version)
    update_main_py(version)
    update_env_versions(version)
    update_api_docs(version)
    check_changelog(version)
    
    print(f"\n✅ Synchronisation terminée!")
    print(f"   N'oubliez pas de mettre à jour le CHANGELOG.md si ce n'est pas fait.")


def show_usage():
    """Affiche l'aide du script."""
    print(__doc__)


def generate_changelog_template(version: str) -> None:
    """Affiche un template de changelog pour la version."""
    today = datetime.now().strftime("%d %B %Y").lstrip("0")
    template = f"""
## [{version}] - {today}

### ✨ Nouvelles fonctionnalités
- **Nouveau** : Description de la fonctionnalité

### 🐛 Corrections
- **Fix** : Description de la correction

### 📝 Modifications
| Fichier | Modification |
|---------|--------------|
| `fichier.py` | Description du changement |

### 🔧 Modifications code
- Refactoring de X
- Optimisation de Y

### 📋 Checklist pour agents IA
- [ ] Item 1
- [ ] Item 2

---
"""
    print(f"\n📋 Template de changelog pour [{version}]:\n")
    print(template)


def main():
    """Point d'entrée principal."""
    args = sys.argv[1:]
    
    if not args:
        # Synchronise avec la version actuelle
        version = read_version()
        sync_all(version)
        return
    
    if args[0] == "--help" or args[0] == "-h":
        show_usage()
        return
    
    if args[0] == "--check":
        success = check_version_consistency()
        sys.exit(0 if success else 1)
    
    if args[0] == "--set" and len(args) > 1:
        new_version = args[1]
        parse_version(new_version)  # Valide le format
        write_version(new_version)
        sync_all(new_version)
        return
    
    if args[0] == "--template":
        version = read_version()
        generate_changelog_template(version)
        return
    
    if args[0] in ("major", "minor", "patch"):
        current = read_version()
        new_version = bump_version(current, args[0])
        print(f"\n🔼 Bump {args[0]}: {current} -> {new_version}\n")
        write_version(new_version)
        sync_all(new_version)
        generate_changelog_template(new_version)
        return
    
    print(f"❌ Argument inconnu: {args[0]}")
    show_usage()
    sys.exit(1)


if __name__ == "__main__":
    main()
