#!/usr/bin/env python3
"""
Écriture MANUELLE de APP_SUBNET dans le .env existant d'une app socle.

Contexte : le Hub neuf (HUB_base) alloue ports + sous-réseau via
`POST /api/apps/allocate-ports` (pool APP_SUBNET_POOL, 10.50.0.0/16), appelé par
`make sync-env` → ACTIONS/PYTHON/allocate_ports.py. Le Hub legacy hub-legacy
(3.9.x, pré-H9) ne connaît PAS cet endpoint : sur un déploiement exemple-app,
APP_SUBNET reste vide et `docker compose up` échoue
(${APP_SUBNET:?APP_SUBNET manquant}).

Ce script comble le trou SANS toucher au socle ni au Hub : l'opérateur le lance
une fois par app, il choisit (ou vérifie) un /24 de la plage dédiée exemple-app
(10.220.0.0/16) et l'écrit dans le .env. Action 100 % manuelle, par convention :
le flux automatique `make sync-env` reste inchangé.

Plage dédiée exemple-app : 10.220.0.0/16 (un /24 par app) — disjointe par
convention du pool du Hub neuf (10.50.0.0/16), des ateliers hubctl
(10.210.0-63.0/24) et des plages prod usuelles (10.42/10.44/10.90).

Sécurités :
  - Vérifie la disjonction avec TOUS les sous-réseaux Docker actifs de la
    machine (`docker network inspect`) et les APP_SUBNET des apps voisines
    (../*/.env, best-effort) — jamais de « Pool overlaps ».
  - Ne modifie JAMAIS une valeur APP_SUBNET non vide sans --force (changer le
    subnet d'une app déjà montée exige de recréer son réseau Docker).
  - Sauvegarde horodatée avant toute écriture : .env.pre-subnet-<stamp>.

Usage :
    python3 scripts/set_app_subnet.py                          # auto: 1er /24 libre en 10.220
    python3 scripts/set_app_subnet.py --subnet 10.220.7.0/24   # /24 imposé
    python3 scripts/set_app_subnet.py --check                  # diagnostic sans écriture
    python3 scripts/set_app_subnet.py --force --subnet X       # écrase une valeur existante
    python3 scripts/set_app_subnet.py --env CHEMIN             # .env alternatif

Après écriture : `make up` (le réseau Docker de l'app est créé avec ce subnet).
"""

import argparse
import ipaddress
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV_LINE = re.compile(r'^([A-Z_][A-Z0-9_]*)=(.*)$')

# Plage dédiée exemple-app (voir docstring). Un /24 par app : 10.220.0.0/24 …
DEFAULT_BASE = "10.220"


def read_env(path):
    """Retourne le dict clé→valeur du .env (chaînes brutes, sans interprétation)."""
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            match = ENV_LINE.match(line.strip())
            if match:
                values[match.group(1)] = match.group(2).strip()
    return values


def set_env_var(path, key, value):
    """Remplace `key=value` en place, ou ajoute la clé en fin de fichier."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    found = False
    for i, line in enumerate(lines):
        if ENV_LINE.match(line.strip()) and line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def docker_subnets():
    """Sous-réseaux IPAM de tous les réseaux Docker actifs (lecture seule).

    Retourne (set de CIDR, docker_ok). docker_ok=False → Docker indisponible :
    les vérifications réseau sont silencieusement sautées (best-effort, comme
    INITIALISE.py find_free_subnet).
    """
    taken = set()
    try:
        ls = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.Name}}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return taken, False
    if ls.returncode != 0:
        return taken, False
    for name in [n for n in ls.stdout.split() if n]:
        try:
            ins = subprocess.run(
                ["docker", "network", "inspect", "--format",
                 "{{range .IPAM.Config}}{{.Subnet}} {{end}}", name],
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if ins.returncode == 0:
            taken.update(s for s in ins.stdout.split() if s)
    return taken, True


def neighbor_subnets(repo_root):
    """APP_SUBNET des .env des apps voisines (../*/.env), best-effort.

    Une app voisine éteinte n'a aucun réseau Docker actif : sans ce scan, son
    subnet (figé dans son .env) pourrait être réalloué à une autre app."""
    taken = set()
    neighbors = os.path.join(os.path.dirname(os.path.abspath(repo_root)),
                             "*", ".env")
    try:
        import glob
        for env_path in sorted(glob.glob(neighbors)):
            if os.path.abspath(env_path) == os.path.abspath(
                    os.path.join(repo_root, ".env")):
                continue
            value = read_env(env_path).get("APP_SUBNET", "").strip()
            if value:
                taken.add(value)
    except OSError:
        pass
    return taken


def find_free_subnet(taken_cidrs, base):
    """Premier /24 libre de la plage `{base}.0.0/16` hors taken_cidrs, sinon None."""
    for n in range(256):
        cidr = f"{base}.{n}.0/24"
        if not overlaps(cidr, taken_cidrs):
            return cidr
    return None


def overlaps(cidr, taken_cidrs):
    """True si cidr en recouvre au moins un des taken_cidrs (entrant invalide ignoré)."""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return True  # CIDR invalide : considéré conflictuel par prudence
    for other in taken_cidrs:
        try:
            if net.overlaps(ipaddress.ip_network(other, strict=False)):
                return True
        except ValueError:
            continue
    return False


def collect_taken(extra_env_path=None):
    """Union : réseaux Docker actifs + APP_SUBNET voisins (+ .env alternatif)."""
    taken, docker_ok = docker_subnets()
    taken |= neighbor_subnets(REPO_ROOT)
    if extra_env_path and os.path.exists(extra_env_path):
        value = read_env(extra_env_path).get("APP_SUBNET", "").strip()
        if value:
            taken.add(value)
    return taken, docker_ok


def main():
    parser = argparse.ArgumentParser(
        description="Écrit MANUELLEMENT APP_SUBNET (plage exemple-app 10.220.0.0/16) "
                    "dans le .env de l'app.")
    parser.add_argument("--subnet", metavar="CIDR",
                        help="/24 à écrire (ex : 10.220.7.0/24). Absent → auto "
                             "(premier /24 libre de la plage).")
    parser.add_argument("--base", default=DEFAULT_BASE, metavar="A.B",
                        help=f"plage /16 de l'auto-allocation (défaut : {DEFAULT_BASE})")
    parser.add_argument("--env", metavar="CHEMIN",
                        default=os.path.join(REPO_ROOT, ".env"),
                        help="chemin du .env (défaut : <repo>/.env)")
    parser.add_argument("--check", action="store_true",
                        help="diagnostic seulement : aucun fichier modifié")
    parser.add_argument("--force", action="store_true",
                        help="autorise l'écrasement d'une valeur APP_SUBNET non vide")
    args = parser.parse_args()

    env_path = os.path.abspath(args.env)
    if not os.path.exists(env_path):
        print(f"❌ .env introuvable : {env_path} — ce script patche un .env "
              f"EXISTANT (cf. .env.example pour en créer un).")
        return 1

    current = read_env(env_path).get("APP_SUBNET", "").strip()

    # ── Mode --check : état + suggestion, aucune écriture ──
    if args.check:
        taken, docker_ok = collect_taken(env_path)
        print(f"🔎 APP_SUBNET courant : {current or '— (vide)'}")
        if current and overlaps(current, taken - {current}):
            print("⚠️  Ce subnet entre en CONFLIT avec un réseau Docker actif "
                  "ou une app voisine !")
        print(f"🌐 Réseaux Docker actifs : "
              f"{len(taken)} subnet(s) vu(s)"
              + ("" if docker_ok else " (Docker indisponible — liste partielle)"))
        suggestion = find_free_subnet(taken, args.base)
        print(f"💡 Suggestion : {suggestion or f'plage {args.base}.0.0/16 épuisée'}")
        print("   (aucun fichier modifié : mode --check)")
        return 0

    # ── Validation du CIDR cible ──
    if args.subnet:
        try:
            net = ipaddress.ip_network(args.subnet, strict=False)
        except ValueError as exc:
            print(f"❌ CIDR invalide « {args.subnet} » : {exc}")
            return 1
        target = str(net)
    else:
        taken, docker_ok = collect_taken(env_path)
        target = find_free_subnet(taken, args.base)
        if not target:
            print(f"❌ Aucun /24 libre dans {args.base}.0.0/16 — passe "
                  f"--subnet explicitement ou vérifie `docker network ls`.")
            return 1

    # ── Garde anti-écrasement ──
    if current and current != target and not args.force:
        print(f"❌ APP_SUBNET déjà défini ({current}) — l'écraser exige de "
              f"recréer le réseau Docker de l'app (docker compose down && "
              f"docker network rm). Passe --force pour confirmer.")
        return 1

    if current == target:
        print(f"✅ APP_SUBNET déjà à jour ({target}) — rien à faire.")
        return 0

    # ── Vérification de disjonction (réseaux actifs + voisins) ──
    taken, docker_ok = collect_taken(env_path)
    taken.discard(current)  # notre ancienne valeur (si --force) ne compte pas
    if overlaps(target, taken):
        print(f"❌ {target} entre en conflit avec un sous-réseau existant "
              f"(réseau Docker actif ou .env voisin). Choisis un autre /24 : "
              f"`python3 scripts/set_app_subnet.py --check`.")
        return 1
    if not docker_ok:
        print("⚠️  Docker indisponible — disjonction vérifiée uniquement contre "
              "les .env voisins (à confirmer : docker network ls).")

    # ── Écriture (avec backup horodaté) ──
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{env_path}.pre-subnet-{stamp}"
    shutil.copy2(env_path, backup)
    set_env_var(env_path, "APP_SUBNET", target)
    print(f"✅ APP_SUBNET={target} écrit dans {env_path}")
    print(f"💾 Sauvegarde : {os.path.basename(backup)}")
    print("→ Applique avec `make up` (le réseau Docker de l'app est créé avec "
          "ce subnet).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
