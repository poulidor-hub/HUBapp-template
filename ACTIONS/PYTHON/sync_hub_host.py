#!/usr/bin/env python3
"""Découverte et synchronisation de l'IP du Hub.

Appelé par `make sync-env` (mode --quiet, silencieux/non-bloquant) et par
`make sync-hub-host` (mode interactif, avec prompt de secours, ou --hub-host X
pour forcer). Interroge GET /api/config/hub-host du Hub.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
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


def query_hub_host_full(host: str, port: str, timeout: float = 1.5) -> dict | None:
    """GET http://{host}:{port}/api/config/hub-host → dict de la réponse, ou None."""
    url = f"http://{host}:{port}/api/config/hub-host"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def query_hub_host(host: str, port: str, timeout: float = 1.5) -> str | None:
    """Compat : champ 'host' de la réponse hub-host."""
    data = query_hub_host_full(host, port, timeout)
    if not data:
        return None
    host_val = data.get("host")
    return host_val.strip() if isinstance(host_val, str) and host_val.strip() else None


def discover_hub_host(candidates: list[str], hub_api_port: str, timeout: float = 1.5) -> dict | None:
    """Itère les candidats dans l'ordre, retourne le 1er dict avec 'host' valide. None si tous injoignables."""
    for host in candidates:
        if not host or not host.strip():
            continue
        result = query_hub_host_full(host.strip(), hub_api_port, timeout)
        if result and isinstance(result.get("host"), str):
            return result
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Découverte/synchronisation de l'IP du Hub via GET /api/config/hub-host."
    )
    parser.add_argument("--quiet", action="store_true",
                        help="mode silencieux non-bloquant (utilisé par sync-env)")
    parser.add_argument("--hub-host", default=None,
                        help="force l'IP/hostname ; saute la découverte")
    args = parser.parse_args(argv)

    # Garde : ne jamais créer de .env de zéro (rôle de INITIALISE.py / make dev qui
    # bootstrappe depuis .env.example). Sans .env on s'abstient proprement.
    if not ENV_PATH.exists():
        if not args.quiet:
            print(
                f"ℹ️ Aucun .env trouvé ({ENV_PATH.name}). Lancez `make dev` ou `make up` "
                f"pour le créer depuis .env.example, ou copiez-le manuellement."
            )
        return 0

    env = read_env(ENV_PATH)
    hub_api_port = (env.get("HUB_API_PORT") or "8000").strip() or "8000"
    current = (env.get("HUB_HOST") or "").strip()

    # --- Override explicite : écriture directe, découverte sautée ---
    if args.hub_host is not None:
        new = args.hub_host.strip()
        if not new:
            print("❌ --hub-host vide ignoré")
            return 1
        if new != current:
            set_env_var(ENV_PATH, "HUB_HOST", new)
            print(f"🔄 HUB_HOST forcé: {current or '(vide)'} → {new}")
        elif not args.quiet:
            print(f"✅ HUB_HOST déjà à jour ({new})")
        return 0

    # --- Découverte via candidats ordonnés ---
    local_ip = get_local_ip()
    raw_candidates = [current, "localhost", "127.0.0.1", local_ip, "host.docker.internal"]
    seen: set[str] = set()
    candidates: list[str] = []
    for c in raw_candidates:
        if c and c.strip() and c not in seen:
            seen.add(c)
            candidates.append(c)

    discovered = discover_hub_host(candidates, hub_api_port)

    # Compat : retour legacy (str, anciens mocks/callers de discover_hub_host) normalisé en dict
    if isinstance(discovered, str):
        discovered = {"host": discovered}

    if discovered:
        hub_host_val = discovered.get("host")
        if isinstance(hub_host_val, str):
            hub_host_val = hub_host_val.strip()
        # Garde compat hub legacy (3.9.x) : le champ `host` annoncé peut être
        # l'IP docker INTERNE du conteneur hub (ex. 172.26.0.3), injoignable
        # depuis le réseau dédié de l'app. Si le Hub répond déjà via le
        # HUB_HOST courant, on le CONSERVE — ne pas casser ce qui marche.
        if (current and hub_host_val and hub_host_val != current
                and query_hub_host_full(current, hub_api_port) is not None):
            print(f"✅ HUB_HOST conservé ({current}) — le Hub y répond déjà "
                  f"(annonce « {hub_host_val} » ignorée)")
            hub_host_val = current
        # Garde anti-IP-morte (complément du garde ci-dessus) : si HUB_HOST
        # courant est vide ou mort, l'annonce injoignable ne doit pas être
        # écrite non plus — fallback : IP LAN de l'hôte si le Hub y répond
        # (port publié sur 0.0.0.0) ; sinon aucune écriture.
        if (hub_host_val and hub_host_val != current
                and not query_hub_host_full(hub_host_val, hub_api_port)):
            fallback = None
            lan = get_local_ip()
            if lan and query_hub_host_full(lan, hub_api_port):
                fallback = lan
            if fallback:
                print(f"⚠️ Hub annonce {hub_host_val} (injoignable) — adoption "
                      f"de {fallback} (joignable) ; corrigez l'IP configurée du Hub")
                hub_host_val = fallback
            else:
                print(f"⚠️ Hub annonce {hub_host_val} (injoignable), aucun candidat "
                      f"joignable — HUB_HOST inchangé")
                hub_host_val = current
        if hub_host_val and hub_host_val != current:
            set_env_var(ENV_PATH, "HUB_HOST", hub_host_val)
            print(f"🔄 HUB_HOST mis à jour: {current or '(vide)'} → {hub_host_val}")
        elif not args.quiet:
            print(f"✅ HUB_HOST déjà à jour ({hub_host_val})")

        # --- Garde d'instance + propagation des ports (hub ≥ annonce api_port) ---
        announced_api = discovered.get("api_port")
        announced_front = discovered.get("frontend_port")
        instance = (discovered.get("instance_id") or "").strip() if isinstance(discovered.get("instance_id"), str) else ""

        if announced_api is None and instance == "":
            if not args.quiet:
                print("⚠️ Hub sans annonce de ports/instance (version antérieure) — "
                      "propagation de l'IP seule ; vérifiez manuellement HUB_API_PORT.")
            return 0

        stored_instance = (env.get("HUB_INSTANCE_ID") or "").strip()
        if stored_instance and instance and stored_instance != instance:
            print(f"❌ Le Hub contacté ({current or '?'}) n'est PAS celui du dernier sync "
                  f"(mémorisé {stored_instance} ≠ détecté {instance}) — aucune écriture effectuée.")
            print("   • Mauvaise cible ? Vérifiez HUB_HOST et HUB_API_PORT dans le .env.")
            print("   • Changement de Hub VOLONTAIRE ? Corrigez HUB_HOST puis supprimez la ligne "
                  "HUB_INSTANCE_ID du .env, et relancez `make sync-env` "
                  "(la nouvelle instance sera mémorisée).")
            return 1

        # Ports annoncés vs configurés
        mismatches = []
        if isinstance(announced_api, int) and str(announced_api) != hub_api_port:
            set_env_var(ENV_PATH, "HUB_API_PORT", str(announced_api))
            mismatches.append(f"HUB_API_PORT {hub_api_port} → {announced_api}")
        if isinstance(announced_front, int):
            front = (env.get("HUB_FRONTEND_PORT") or "80").strip() or "80"
            if str(announced_front) != front:
                set_env_var(ENV_PATH, "HUB_FRONTEND_PORT", str(announced_front))
                mismatches.append(f"HUB_FRONTEND_PORT {front} → {announced_front}")
        if instance:
            set_env_var(ENV_PATH, "HUB_INSTANCE_ID", instance)
        if mismatches:
            print(f"⚠️ Mismatch de ports corrigé ({'; '.join(mismatches)}) — "
                  f"RECRÉEZ les conteneurs de l'app (make up, ou ACTION UPDATE) "
                  f"pour que le proxy nginx et le backend prennent le nouveau port.")
        elif not args.quiet:
            print("✅ Ports et instance du Hub alignés")
        return 0

    # --- Hub injoignable ---
    if args.quiet:
        return 0  # silence, on garde current

    # mode interactif : prompt de secours
    try:
        saisie = input(
            f"❌ Hub injoignable via {candidates}. "
            f"Saisissez la nouvelle IP/hostname (Entrée = garder '{current}', Ctrl+C = annuler) : "
        ).strip()
    except EOFError:
        print("❌ Pas de TTY interactif. Relancez avec : make sync-hub-host HUB_HOST=<ip>")
        return 1
    if saisie and saisie != current:
        set_env_var(ENV_PATH, "HUB_HOST", saisie)
        print(f"🔄 HUB_HOST mis à jour: {current or '(vide)'} → {saisie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
