#!/usr/bin/env python3
"""Découverte et synchronisation de l'IP du Hub.

Appelé par `make sync-env` (mode --quiet, silencieux/non-bloquant) et par
`make sync-hub-host` (mode interactif, avec prompt de secours, ou --hub-host X
pour forcer). Interroge GET /api/config/hub-host du Hub.
"""
from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def read_env(path: Path) -> dict:
    """Parse un .env (clé=valeur). Ignore commentaires (#) et lignes vides."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def set_env_var(path: Path, key: str, value: str) -> bool:
    """Écrit key=value dans le .env. Retourne True si la valeur a changé."""
    lines = path.read_text().splitlines() if path.exists() else []
    found = False
    changed = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            if line != f"{key}={value}":
                lines[i] = f"{key}={value}"
                changed = True
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
        changed = True
    if changed:
        path.write_text("\n".join(lines) + "\n")
    return changed


def get_local_ip() -> str | None:
    """Détection IP locale via socket UDP vers 8.8.8.8.
    Exclut les IP en 172.x (interfaces internes Docker)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None
    if ip.startswith("172."):
        return None  # interface interne Docker
    return ip
