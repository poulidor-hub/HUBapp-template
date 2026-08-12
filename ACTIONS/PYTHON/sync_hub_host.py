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


def query_hub_host(host: str, port: str, timeout: float = 1.5) -> str | None:
    """GET http://{host}:{port}/api/config/hub-host → retourne le champ 'host', ou None."""
    url = f"http://{host}:{port}/api/config/hub-host"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        host_val = data.get("host")
        if isinstance(host_val, str) and host_val.strip():
            return host_val.strip()
        return None
    except Exception:
        return None


def discover_hub_host(candidates: list[str], hub_api_port: str, timeout: float = 1.5) -> str | None:
    """Itère les candidats dans l'ordre, retourne le 1er 'host' non-None. None si tous injoignables."""
    for host in candidates:
        if not host or not host.strip():
            continue
        result = query_hub_host(host.strip(), hub_api_port, timeout)
        if result:
            return result
    return None
