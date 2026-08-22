#!/usr/bin/env python3
"""Garde de fraîcheur de l'image Docker api pour `make test-docker`.

Appelé par la cible Makefile `ensure-api-fresh` (avant test-docker /
test-docker-cov). Compare le mtime le plus récent des sources surveillées
(backend/**, Dockerfile.backend, VERSION — caches exclus) avec la date de
création de l'image Docker du service api.

En mode dev (backend monté dans /app via docker-compose.dev.yml), la garde
est ignorée : les tests exécutent la source montée, fraîche par construction.

Codes de sortie :
  0 — image à jour, ou mode dev détecté
  1 — image périmée ou absente → rebuild nécessaire
  2 — erreur bloquante (docker injoignable, réponse inattendue...)
"""
from __future__ import annotations

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
