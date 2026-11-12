#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
Aligne APP_SOCLE_VERSION sur le socle construit localement.

App fine : Dockerfile.backend fait `FROM poulidor/socle-api:${SOCLE_VERSION}`.
Après un `./hubctl socle build` (nouvelle version du socle), le .env doit
suivre — sinon le build tente de puller sur Docker Hub une image qui
n'existe que localement (offline-first) : "pull access denied".

Appelé par `make sync-env` (donc make build / make up / make dev).
Fonctionne sur station de dev comme serveur de déploiement (structure
parc : APPS/<app>/ dans un stack contenant HUBsocle/).

Sécurités :
- HUBsocle absent (app standalone) → no-op silencieux ;
- docker indisponible → no-op avec note (l'app peut être buildée ailleurs) ;
- image poulidor/socle-api:<V> absente localement → message ACTIONNABLE
  ("lancez ./hubctl socle build") et exit 1 — un échec explicite vaut
  mieux que le message buildkit obscur 30 s plus tard ;
- idempotent : aucune écriture si déjà aligné ;
- app héritée : compose exige APP_SOCLE_VERSION mais le .env (pré-socle)
  ne l'a pas → détection par le compose (pas la seule clé du .env) et
  ajout automatique de la clé — sinon no-op puis échec ${APP_SOCLE_VERSION:?}
  au build (incident station 2026-11-11 : 5 apps legacy bloquées).
"""
import os
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = APP_DIR / ".env"
# Structure parc : APPS/<app>/ → racine stack (../../) → HUBsocle/
SOCLE_DIR = Path(os.environ.get("HUBSOCLE_DIR", APP_DIR.parent.parent / "HUBsocle"))
IMAGE = "poulidor/socle-api"
ENV_KEY = "APP_SOCLE_VERSION"


def socle_version() -> str | None:
    """VERSION du checkout HUBsocle du stack, ou None s'il est absent."""
    f = SOCLE_DIR / "VERSION"
    try:
        version = f.read_text(encoding="utf-8").strip()
        return version or None
    except OSError:
        return None


def image_exists(version: str) -> bool | None:
    """True si l'image socle est construite localement, None si docker
    est indisponible (on ne veut pas bloquer un build distant)."""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", f"{IMAGE}:{version}"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def compose_requires_socle() -> bool:
    """True si un docker-compose*.yml de l'app référence APP_SOCLE_VERSION.

    Signal de liaison socle indépendant du .env : une app migrée vers le
    compose socle-based peut avoir un .env hérité (pré-socle) sans la clé —
    la détection par la seule clé la faisait passer pour standalone (no-op),
    et le build échouait ensuite sur ${APP_SOCLE_VERSION:?}.
    """
    for path in sorted(APP_DIR.glob("docker-compose*.yml")):
        try:
            if ENV_KEY in path.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


def set_env_value(key: str, value: str) -> bool:
    """Remplace (ou ajoute en fin) la ligne key=value du .env. True si écrit."""
    if not ENV_PATH.exists():
        return False
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return replaced


def main() -> int:
    version = socle_version()
    if version is None:
        # Pas de socle dans ce stack (app standalone) — pas notre rôle.
        return 0

    if not ENV_PATH.exists():
        return 0
    env_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    has_env_key = any(line.startswith(f"{ENV_KEY}=") for line in env_lines)
    compose_needs_key = compose_requires_socle()

    # App réellement liée au socle = clé présente dans le .env OU exigée par
    # le compose. Sans l'un ni l'autre, l'image ne sert à rien : no-op (sinon
    # make dev/build/up échoue pour toute app scaffoldée sans image socle).
    # Cas .env sans la clé + compose qui l'exige (app héritée pré-socle) : on
    # poursuit — la clé sera ajoutée plus bas (sinon no-op puis échec
    # ${APP_SOCLE_VERSION:?} au build, cf. incident station 2026-11-11).
    if not has_env_key and not compose_needs_key:
        print(f"ℹ️  {ENV_KEY} absent du .env et du docker-compose — app non liée au socle, no-op.")
        return 0

    exists = image_exists(version)
    if exists is False:
        print(
            f"❌ Socle {IMAGE}:{version} attendu mais ABSENT de ce Docker.\n"
            f"   → Lancez : ./hubctl socle build   (depuis la racine du stack)\n"
            f"   APP_SOCLE_VERSION inchangé.",
            file=sys.stderr,
        )
        return 1

    current = None
    for line in env_lines:
        if line.startswith(f"{ENV_KEY}="):
            current = line.split("=", 1)[1].strip()
            break

    if current == version:
        return 0

    if set_env_value(ENV_KEY, version):
        print(f"🔄 {ENV_KEY}: {current} → {version} (socle construit localement)")
    elif compose_needs_key:
        print(f"➕ {ENV_KEY}={version} ajouté au .env (exigé par docker-compose.yml — app héritée pré-socle)")
    else:
        print(f"➕ {ENV_KEY}={version} ajouté au .env")
    print("ℹ️  Rebuild de l'image api requis pour appliquer le nouveau socle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
