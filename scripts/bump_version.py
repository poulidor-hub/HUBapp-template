#!/usr/bin/env python3
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
    """Met à jour la version dans backend/main.py (FastAPI app)."""
    main_path = ROOT_DIR / "backend" / "main.py"
    if not main_path.exists():
        print(f"⚠️  main.py non trouvé, ignoré")
        return False
    
    content = main_path.read_text(encoding='utf-8')
    
    # Pattern pour trouver version="X.Y.Z" dans FastAPI
    pattern = r'(version\s*=\s*["\'])[\d]+\.[\d]+\.[\d]+(["\'])'
    new_content = re.sub(pattern, rf'\g<1>{version}\g<2>', content)
    
    if content == new_content:
        print(f"⚠️  backend/main.py: pattern de version non trouvé")
        return False
    
    main_path.write_text(new_content, encoding='utf-8')
    print(f"✅ backend/main.py: version={version}")
    return True


def update_api_docs(version: str) -> bool:
    """Met à jour la version dans docs/API.md."""
    api_path = ROOT_DIR / "docs" / "API.md"
    if not api_path.exists():
        print(f"⚠️  docs/API.md non trouvé, ignoré")
        return False
    
    content = api_path.read_text(encoding='utf-8')
    
    # Pattern pour le badge de version ou le header
    # Cherche "Version: X.Y.Z" ou "**Version**: X.Y.Z" ou badge markdown
    patterns = [
        (r'(\*\*Version\*\*\s*:\s*)[\d]+\.[\d]+\.[\d]+', rf'\g<1>{version}'),
        (r'(Version\s*:\s*)[\d]+\.[\d]+\.[\d]+', rf'\g<1>{version}'),
        (r'(version-)([\d]+\.[\d]+\.[\d]+)(-)', rf'\g<1>{version}\g<3>'),
    ]
    
    updated = False
    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            content = new_content
            updated = True
    
    if updated:
        api_path.write_text(content, encoding='utf-8')
        print(f"✅ docs/API.md: version={version}")
    else:
        # Ajouter le badge de version en haut du fichier si absent
        lines = content.split('\n')
        if lines and lines[0].startswith('# '):
            # Insérer après le titre
            badge = f"\n![Version](https://img.shields.io/badge/version-{version}-blue)"
            lines.insert(1, badge)
            api_path.write_text('\n'.join(lines), encoding='utf-8')
            print(f"✅ docs/API.md: badge ajouté (version={version})")
            updated = True
        else:
            print(f"⚠️  docs/API.md: impossible d'ajouter le badge de version")
    
    return updated


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
    update_api_docs(version)
    check_changelog(version)
    
    print(f"\n✅ Synchronisation terminée!")
    print(f"   N'oubliez pas de mettre à jour le CHANGELOG.md si ce n'est pas fait.")


def show_usage():
    """Affiche l'aide du script."""
    print(__doc__)


def generate_changelog_template(version: str) -> None:
    """Affiche un template de changelog pour la version."""
    today = datetime.now().strftime("%-d %B %Y")
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
