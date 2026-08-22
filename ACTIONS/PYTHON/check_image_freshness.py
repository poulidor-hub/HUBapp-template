#!/usr/bin/env python3
"""Garde de fraîcheur de l'image Docker api pour `make test-docker`.

Appelé par la cible Makefile `ensure-api-fresh` (avant test-docker /
test-docker-cov). Compare le mtime le plus récent des sources surveillées
(backend/**, Dockerfile.backend, VERSION — caches exclus) avec la date du
dernier rebuild assuré : le stamp `.api-image.stamp` (posé par le Makefile
après un rebuild réussi), avec repli sur la date de création de l'image
Docker (`.Created`) si le stamp est absent.

Le stamp est nécessaire car BuildKit réutilise le cache quand le contenu
des sources ne change pas (ex. `touch` seul) : l'image re-buildée garde
alors son ancien `.Created` et la comparaison mtime/`.Created` bouclerait
sur du rebuild infini alors que l'image est, à contenu identique, à jour.

En mode dev (backend monté dans /app via docker-compose.dev.yml), la garde
est ignorée : les tests exécutent la source montée, fraîche par construction.

Codes de sortie :
  0 — image à jour, ou mode dev détecté
  1 — image périmée ou absente → rebuild nécessaire
  2 — erreur bloquante (docker injoignable, réponse inattendue...)
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_BASE = ["docker", "compose", "-f", "docker-compose.yml"]

# Artefacts exclus du calcul de fraîcheur (sinon faux positifs permanents)
EXCLUDED_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "htmlcov",
    ".venv",
    "venv",
    "node_modules",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_NAME_PREFIXES = (".coverage",)

# Sources hors backend/ qui influencent l'image api
EXTRA_WATCHED = ("Dockerfile.backend", "VERSION")

# Stamp posé par le Makefile (ensure-api-fresh / build) après un rebuild réussi.
STAMP_FILE = ".api-image.stamp"


def is_excluded(path: Path) -> bool:
    """True si le chemin est un artefact/cache à ignorer."""
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    if path.name.startswith(EXCLUDED_NAME_PREFIXES):
        return True
    return any(part in EXCLUDED_DIRS for part in path.parts)


def find_newest_source(root: Path) -> tuple[Path, float] | None:
    """Source la plus récente parmi backend/** (exclusions appliquées),
    Dockerfile.backend et VERSION. Retourne (chemin, mtime) ou None."""
    candidates: list[Path] = []
    backend = root / "backend"
    if backend.is_dir():
        candidates.extend(
            p for p in backend.rglob("*") if p.is_file() and not is_excluded(p)
        )
    for name in EXTRA_WATCHED:
        p = root / name
        if p.is_file():
            candidates.append(p)
    if not candidates:
        return None
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    return newest, newest.stat().st_mtime


def parse_rfc3339(value: str) -> datetime:
    """Parse une date docker (.Created, RFC3339 avec nanosecondes possibles).

    fromisoformat (3.11) refuse plus de 6 chiffres fractionnaires → on tronque.
    """
    if "." in value:
        head, _, tail = value.partition(".")
        digits = tail[: len(tail) - len(tail.lstrip("0123456789"))]
        tz_suffix = tail[len(digits):]
        value = f"{head}.{digits[:6]}{tz_suffix}"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def run(cmd: list[str]) -> str:
    """Exécute une commande, retourne stdout stripé. RuntimeError si échec."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"échec : {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def container_is_dev(root: Path, container_id: str) -> bool:
    """True si le conteneur api monte ./backend vers /app (overlay dev)."""
    mounts_json = run(["docker", "inspect", "--format", "{{json .Mounts}}", container_id])
    for mount in json.loads(mounts_json) or []:
        if mount.get("Destination") == "/app":
            try:
                if Path(mount.get("Source", "")).resolve() == (root / "backend").resolve():
                    return True
            except OSError:
                continue
    return False


def image_created_ts(image_id: str) -> float:
    """Timestamp Unix de création de l'image (docker image inspect .Created)."""
    created = run(["docker", "image", "inspect", "--format", "{{.Created}}", image_id])
    return parse_rfc3339(created).timestamp()


def main() -> int:
    try:
        newest = find_newest_source(ROOT)
    except OSError as exc:
        print(f"❌ Erreur fs : {exc}", file=sys.stderr)
        return 2
    if newest is None:
        print("⚠️  Aucune source surveillée (backend/ absent ?) — garde ignorée.")
        return 0

    try:
        # Conteneur api existant (running ou arrêté) ? → détection mode dev
        container_id = run([*COMPOSE_BASE, "ps", "-aq", "api"])
        if container_id and container_is_dev(ROOT, container_id):
            print("🧪 Mode dev détecté (backend monté dans /app) — garde ignorée.")
            return 0

        image_id = run([*COMPOSE_BASE, "images", "-q", "api"])
        if not image_id:
            print("📦 Image api introuvable (jamais buildée ou conteneur non créé) — rebuild requis.")
            return 1

        # Référence de fraîcheur : stamp du dernier rebuild assuré (fiable même
        # si BuildKit réutilise le cache), sinon .Created de l'image.
        stamp = ROOT / STAMP_FILE
        if stamp.is_file():
            ref_ts = stamp.stat().st_mtime
            ref_origin = "rebuild assuré"
        else:
            ref_ts = image_created_ts(image_id)
            ref_origin = "build image"
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"❌ Erreur docker : {exc}", file=sys.stderr)
        return 2

    src_path, src_ts = newest
    if src_ts > ref_ts:
        src_dt = datetime.fromtimestamp(src_ts, tz=timezone.utc)
        ref_dt = datetime.fromtimestamp(ref_ts, tz=timezone.utc)
        print(f"🔨 Image api périmée — source plus récente : {src_path.relative_to(ROOT)}")
        print(f"   Source : {src_dt.isoformat(timespec='seconds')}")
        print(f"   Référence ({ref_origin}) : {ref_dt.isoformat(timespec='seconds')}")
        print("♻️  Rebuild automatique avant les tests…")
        return 1

    ref_dt = datetime.fromtimestamp(ref_ts, tz=timezone.utc)
    print(f"✅ Image api à jour ({ref_origin} {ref_dt.isoformat(timespec='seconds')}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
