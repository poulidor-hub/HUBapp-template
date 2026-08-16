#!/usr/bin/env python3
"""Pré-vol : demande les ports au Hub si absents du .env, puis les y écrit.

Appelé par `make sync-env` AVANT `docker compose up`. Idempotent côté Hub :
un même (slug, host) reçoit toujours les mêmes ports.

Sortie non-zéro = échec bloquant (l'app ne peut pas démarrer sans ports).
"""
import json
import sys
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def read_env(path: Path) -> dict:
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


def set_env_var(path: Path, key: str, value: str) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    env = read_env(ENV_PATH)

    api_port = env.get("API_PORT", "").strip()
    frontend_port = env.get("FRONTEND_PORT", "").strip()
    subnet = env.get("APP_SUBNET", "").strip()
    if api_port and frontend_port and subnet:
        print(f"✅ Ports et sous-réseau déjà définis (API={api_port}, FRONTEND={frontend_port}, SUBNET={subnet}) — pas d'allocation.")
        return 0

    hub_host = env.get("HUB_HOST", "").strip()
    hub_api_port = env.get("HUB_API_PORT", "8000").strip() or "8000"
    slug = env.get("APP_SLUG", "").strip()
    host = env.get("APP_HOST", "").strip()

    if not hub_host or not slug:
        print("❌ HUB_HOST ou APP_SLUG manquant dans .env — allocation impossible.")
        return 1

    url = f"http://{hub_host}:{hub_api_port}/api/apps/allocate-ports"
    body = {"slug": slug}
    if host:
        body["host"] = host

    print(f"🎰 Demande d'allocation de ports au Hub: {url} (slug={slug}, host={host or 'auto'})")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"❌ Échec de l'allocation des ports auprès du Hub: {e}")
        return 1

    api = str(data["api_port"])
    frontend = str(data["frontend_port"])
    https = str(data["frontend_https_port"])
    subnet = str(data.get("subnet") or "").strip()

    set_env_var(ENV_PATH, "API_PORT", api)
    set_env_var(ENV_PATH, "FRONTEND_PORT", frontend)
    set_env_var(ENV_PATH, "FRONTEND_HTTPS_PORT", https)
    if subnet:
        set_env_var(ENV_PATH, "APP_SUBNET", subnet)

    print(f"✅ Ports alloués par le Hub: API={api}, FRONTEND={frontend}, HTTPS={https}, SUBNET={subnet or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
