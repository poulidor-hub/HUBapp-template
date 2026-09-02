#!/usr/bin/env python3
"""
Fusion automatique du .env après une mise à jour de template.

Compare les clés du .env existant avec celles du .env.example (version
courante du template) et AJOUTE les clés manquantes — sans jamais modifier
les valeurs existantes ni supprimer les clés propres à l'app (« orphelines »,
absentes de l'exemple : ex. HUB_INSTANCE_ID). Règle du parc : le .env se
FUSIONNE, il ne se régénère jamais.

Comportement :
  - Sauvegarde horodatée avant toute modification : .env.pre-update-<stamp>
  - Vérifie les variables requises par docker-compose.yml (syntaxe ${VAR:?...})
    et sort en erreur avec un message explicite si l'une reste absente/vide
  - Cas connus auto-remplis (uniquement si vides/absents) :
      FRONTEND_HTTPS_PORT = FRONTEND_PORT + 1
      APP_SUBNET          = subnet réel du réseau Docker de l'app (si détectable)
  - Clés orphelines conservées et signalées dans le rapport

Usage :
    python3 scripts/update_env.py                       # fusion réelle
    python3 scripts/update_env.py --dry-run             # simulation (aucune écriture)
    python3 scripts/update_env.py --example CHEMIN      # .env.example alternatif,
                                                        # ex : ../../HUBapp_TEMPLATE_base/.env.example
                                                        # (utile pendant une migration, avant que
                                                        #  le .env.example de l'app soit à jour)

Après la fusion : `make sync-env` (recalcul des valeurs dérivées), puis
`make up && make health` et vérifier l'accès aux données.
"""

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV_LINE = re.compile(r'^([A-Z_][A-Z0-9_]*)=(.*)$')
REQUIRED_VAR = re.compile(r'\$\{([A-Z_][A-Z0-9_]*):\?')


def read_env(path):
    """Retourne (lignes_brutes, dict clé→valeur) en préservant l'ordre."""
    lines, values = [], {}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            lines = fh.read().splitlines()
        for line in lines:
            match = ENV_LINE.match(line.strip())
            if match:
                values[match.group(1)] = match.group(2).strip()
    return lines, values


def find_required_vars(compose_path):
    """Clés exigées par le compose via la syntaxe ${VAR:?message}."""
    required = set()
    if os.path.exists(compose_path):
        with open(compose_path, encoding='utf-8') as fh:
            required = set(REQUIRED_VAR.findall(fh.read()))
    return required


def detect_app_subnet(slug, repo_dir):
    """Subnet réel du réseau Docker de l'app (lecture seule), sinon None."""
    if not slug:
        return None
    try:
        names = subprocess.run(
            ['docker', 'network', 'ls', '--format', '{{.Name}}'],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.split()
    except Exception:
        return None
    slug = slug.lower()
    candidates = [n for n in names if slug in n.lower() and 'app-network' in n.lower()]
    candidates += [n for n in names if slug in n.lower() and n not in candidates]
    for network in candidates:
        try:
            out = subprocess.run(
                ['docker', 'network', 'inspect', network,
                 '--format', '{{range .IPAM.Config}}{{.Subnet}}{{end}}'],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout.strip()
            if out:
                return out
        except Exception:
            continue
    return None


def main():
    args = sys.argv[1:]
    dry_run = '--dry-run' in args
    example_path = os.path.join(REPO_ROOT, '.env.example')
    if '--example' in args:
        example_path = os.path.abspath(args[args.index('--example') + 1])

    env_path = os.path.join(REPO_ROOT, '.env')
    compose_path = os.path.join(REPO_ROOT, 'docker-compose.yml')
    if not os.path.exists(env_path):
        print(f'❌ {env_path} introuvable — rien à fusionner.')
        return 1
    if not os.path.exists(example_path):
        print(f'❌ {example_path} introuvable — référence de fusion indisponible.')
        return 1

    env_lines, env = read_env(env_path)
    _, example = read_env(example_path)
    required = find_required_vars(compose_path)
    slug = env.get('APP_SLUG', '').strip()

    added, filled, warnings = [], [], []

    # --- Clés du template absentes du .env → ajout (les valeurs DÉRIVÉES sont
    #     recalculées plutôt que reprises de l'exemple)
    new_lines = []
    for key, value in example.items():
        if key in env:
            continue
        if key == 'FRONTEND_HTTPS_PORT':
            port = env.get('FRONTEND_PORT', '').strip()
            if port.isdigit():
                value = str(int(port) + 1)
        elif key == 'APP_SUBNET':
            subnet = detect_app_subnet(slug, REPO_ROOT)
            if subnet:
                value = subnet
                warnings.append(f'APP_SUBNET auto-rempli depuis le réseau Docker existant : {subnet}')
        new_lines.append(f'# [update-env] clé ajoutée depuis le template (défaut .env.example)')
        new_lines.append(f'{key}={value}')
        added.append((key, value))
        env[key] = value

    # --- Slots présents mais vides : compléter seulement pour les cas connus
    for key in ('FRONTEND_HTTPS_PORT', 'APP_SUBNET'):
        if env.get(key, '').strip():
            continue
        if key == 'FRONTEND_HTTPS_PORT':
            port = env.get('FRONTEND_PORT', '').strip()
            if port.isdigit():
                filled.append((key, str(int(port) + 1)))
        elif key == 'APP_SUBNET':
            subnet = detect_app_subnet(slug, REPO_ROOT)
            if subnet:
                filled.append((key, subnet))
                warnings.append(f'APP_SUBNET auto-rempli depuis le réseau Docker existant : {subnet}')

    # --- Variables requises par le compose encore absentes/vides
    missing_required = [
        key for key in sorted(required)
        if not env.get(key, '').strip() and key not in {k for k, _ in filled}
    ]

    orphans = sorted(set(env) - set(example))

    # --- Rapport
    print(f"📄 .env : {len(env)} clés | référence : {os.path.relpath(example_path, REPO_ROOT)}")
    if added:
        print(f'\n➕ {len(added)} clé(s) ajoutée(s) :')
        for key, value in added:
            shown = value if value else '(vide)'
            print(f'   {key}={shown}')
    else:
        print('\n✅ Aucune clé manquante — .env déjà à jour.')
    for key, value in filled:
        print(f'🧩 {key} complété (était vide) : {key}={value}')
    if orphans:
        print(f'\n🔒 {len(orphans)} clé(s) propre(s) à l\'app, conservée(s) telle(s) quelle(s) :')
        print(f'   {", ".join(orphans)}')
    for warning in warnings:
        print(f'ℹ️  {warning}')
    if missing_required:
        print('\n❌ Variables requises par docker-compose.yml toujours vides :')
        for key in missing_required:
            print(f'   {key}')
        print('\n   Complète-les manuellement dans .env puis relance ce script.')
        print('   Indice : APP_SUBNET réel → docker network inspect <réseau-app> ;'
              ' FRONTEND_HTTPS_PORT → FRONTEND_PORT + 1.')
        return 1

    # --- Écriture
    if dry_run:
        print('\n🧪 --dry-run : aucune modification écrite.')
        return 0
    if not added and not filled:
        return 0

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = f'{env_path}.pre-update-{stamp}'
    shutil.copy2(env_path, backup_path)
    print(f'\n💾 Sauvegarde : {os.path.basename(backup_path)}')

    content = '\n'.join(env_lines)
    for key, value in filled:
        content = re.sub(rf'^{key}=.*$', f'{key}={value}', content, flags=re.MULTILINE)
    if new_lines:
        content = content.rstrip('\n') + '\n\n' + '\n'.join(new_lines) + '\n'
    with open(env_path, 'w', encoding='utf-8') as fh:
        fh.write(content)

    print('✅ .env fusionné — valeurs existantes inchangées.')
    print('➡️  Enchaîne : make sync-env && make up && make health, puis vérifie l\'accès aux données.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
