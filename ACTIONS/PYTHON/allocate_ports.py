#!/usr/bin/env python3
"""Pré-vol : demande les ports au Hub si absents du .env, puis les y écrit.

Appelé par `make sync-env` AVANT `docker compose up`. Idempotent côté Hub :
un même (slug, host) reçoit toujours les mêmes ports.

Fallback hub legacy (ex. hub-legacy 3.9.x, pré-H9) : le Hub ne connaît pas
`POST /api/apps/allocate-ports`. Si l'appel échoue (404, hub injoignable)
ou si les ports sont déjà figés dans le .env mais APP_SUBNET reste vide,
le sous-réseau est alloué LOCALEMENT dans la plage dédiée exemple-app
(10.220.0.0/16) via scripts/set_app_subnet.py (disjonction vérifiée contre
les réseaux Docker actifs et les .env voisins). Sur un Hub neuf, l'allocation
par le Hub a la priorité — comportement inchangé.

Sortie non-zéro = échec bloquant (l'app ne peut pas démarrer sans ports).
"""
import json
import sys
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

# Plage dédiée exemple-app (cf. scripts/set_app_subnet.py — même convention).
SUBNET_BASE = "10.220"


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


def _load_subnet_module():
    """Charge scripts/set_app_subnet.py (logique partagée, pas de duplication)."""
    import importlib.util
    script = Path(__file__).resolve().parents[2] / "scripts" / "set_app_subnet.py"
    if not script.exists():
        return None
    spec = importlib.util.spec_from_file_location("set_app_subnet", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def allocate_subnet_locally(env_path: Path, base: str = SUBNET_BASE,
                            loader=None) -> bool:
    """Alloue APP_SUBNET localement (fallback hub sans allocate-ports).

    Retourne True si le .env a été complété. Best-effort : un échec n'excède
    jamais le rôle de ce script (l'allocation des ports reste l'erreur bloquante).
    """
    mod = (loader or _load_subnet_module)()
    if mod is None:
        print("⚠️  scripts/set_app_subnet.py absent — allocation locale du "
              "sous-réseau impossible.")
        return False
    try:
        taken, docker_ok = mod.collect_taken(str(env_path))
        subnet = mod.find_free_subnet(taken, base)
        if not subnet:
            print(f"⚠️  Aucun /24 libre dans {base}.0.0/16 — "
                  f"lance `python3 scripts/set_app_subnet.py --check`.")
            return False
        mod.set_env_var(str(env_path), "APP_SUBNET", subnet)
    except Exception as exc:  # le fallback ne doit jamais masquer l'erreur ports
        print(f"⚠️  Allocation locale du sous-réseau échouée : {exc}")
        return False
    if not docker_ok:
        print("⚠️  Docker indisponible — disjonction vérifiée uniquement "
              "contre les .env voisins.")
    print(f"⚠️  Hub sans allocate-ports (legacy ?) → APP_SUBNET={subnet} "
          f"alloué LOCALEMENT (plage exemple-app {base}.0.0/16).")
    return True


def main() -> int:
    env = read_env(ENV_PATH)

    api_port = env.get("API_PORT", "").strip()
    frontend_port = env.get("FRONTEND_PORT", "").strip()
    subnet = env.get("APP_SUBNET", "").strip()
    if api_port and frontend_port and subnet:
        print(f"✅ Ports et sous-réseau déjà définis (API={api_port}, FRONTEND={frontend_port}, SUBNET={subnet}) — pas d'allocation.")
        return 0

    # Hub legacy (ex. exemple-app) : ports figés manuellement dans le .env, seul le
    # sous-réseau manque — inutile d'interroger un Hub qui ne peut pas répondre.
    if api_port and frontend_port:
        if allocate_subnet_locally(ENV_PATH):
            return 0
        return 1

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

    # CAS 1 (APP_HOST vide = app sur le même serveur que le Hub) : l'endpoint
    # n'accepte que des IP réseaux Docker (whitelist anti-abus) — depuis
    # l'hôte via HUB_HOST=<IP LAN>, la source vue par hub-api est hors
    # whitelist → 403. Le repli localhost (port publié) présente la gateway
    # Docker comme source → accepté. CAS 2 (app distante) : pas de repli.
    candidates = [url]
    if not host:
        candidates.append(f"http://localhost:{hub_api_port}/api/apps/allocate-ports")
    candidates = list(dict.fromkeys(candidates))  # dédoublonne si HUB_HOST=localhost

    payload = json.dumps(body).encode()
    data = None
    last_err: Exception | None = None
    for candidate in candidates:
        print(f"🎰 Demande d'allocation de ports au Hub: {candidate} (slug={slug}, host={host or 'auto'})")
        req = urllib.request.Request(
            candidate,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            break
        except Exception as e:
            last_err = e
            if candidate != candidates[-1]:
                print(f"⚠️  {candidate} indisponible ({e}) — nouvel essai via {candidates[-1]}")
    if data is None:
        # Hub injoignable ou sans endpoint d'allocation : on prépare au
        # moins le sous-réseau localement (fallback legacy), mais les ports
        # manquants restent bloquants.
        allocate_subnet_locally(ENV_PATH)
        print(f"❌ Échec de l'allocation des ports auprès du Hub: {last_err}")
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
    else:
        # Hub neuf qui ne renvoie pas son champ subnet : même fallback local.
        allocate_subnet_locally(ENV_PATH)

    print(f"✅ Ports alloués par le Hub: API={api}, FRONTEND={frontend}, HTTPS={https}, SUBNET={subnet or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
