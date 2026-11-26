#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""Pré-vol `make sync-env` : réconcilie les ports avec le Hub, puis écrit le .env.

Appelé par `make sync-env` AVANT `docker compose up`. Dès que APP_SLUG et
HUB_HOST sont présents, le Hub est consulté MÊME si les ports sont déjà figés
dans le .env : le body inclut alors api_port/frontend_port (ports souhaités),
pour enregistrer l'allocation côté Hub (table port_allocations) et récupérer
un subnet du pool Hub (APP_SUBNET_POOL, 10.50.0.0/16).

Contrat Hub moderne (POST /api/apps/allocate-ports, champs desired optionnels) :
- ports souhaités libres → allocation créée avec CES ports (+ subnet du pool),
  réponse reprise dans le .env ;
- allocation existante identique → reused=true : .env inchangé (no-op, sauf
  APP_SUBNET adopté du pool s'il manque) ;
- divergence/conflit → HTTP 409 : erreur bloquante, .env strictement intact.

Hub ancien (sans support desired : répond 200 avec SES propres ports) : les
ports locaux ne sont JAMAIS écrasés ; le subnet de la réponse est adopté si
le .env n'en a pas, et la mise à jour du Hub est recommandée.

Fallback hub legacy / injoignable (ex. HUB_EXEMPLE 3.9.x, pré-H9) : en
DERNIER recours uniquement, le sous-réseau est alloué LOCALEMENT dans la
plage dédiée hub_exemple (10.220.0.0/16) via scripts/set_app_subnet.py
(disjonction vérifiée contre les réseaux Docker actifs et les .env voisins).
Ports figés localement : seul le subnet peut manquer → allocation locale =
succès ; ports absents : l'allocation des ports reste bloquante (sortie
non-zéro).
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

# Plage dédiée hub_exemple (cf. scripts/set_app_subnet.py — même convention).
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
                            loader=None, reason: str = "Hub injoignable") -> bool:
    """Alloue APP_SUBNET localement (DERNIER recours, plage hub_exemple).

    `reason` décrit pourquoi ce repli est emprunté (Hub injoignable, Hub sans
    champ subnet, Hub non configuré…). Retourne True si le .env a été complété.
    Best-effort : un échec n'excède jamais le rôle de ce script (l'allocation
    des ports reste l'erreur bloquante).
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
    print(f"⚠️  {reason} → APP_SUBNET={subnet} alloué LOCALEMENT "
          f"(plage de dernier recours {base}.0.0/16).")
    return True


def main() -> int:
    env = read_env(ENV_PATH)

    api_port = env.get("API_PORT", "").strip()
    frontend_port = env.get("FRONTEND_PORT", "").strip()
    local_subnet = env.get("APP_SUBNET", "").strip()

    hub_host = env.get("HUB_HOST", "").strip()
    hub_api_port = env.get("HUB_API_PORT", "8000").strip() or "8000"
    slug = env.get("APP_SLUG", "").strip()
    host = env.get("APP_HOST", "").strip()

    if not hub_host or not slug:
        # Pas d'appel Hub possible : comportement local historique.
        if api_port and frontend_port:
            if local_subnet:
                print(f"✅ Ports et sous-réseau déjà définis (API={api_port}, "
                      f"FRONTEND={frontend_port}, SUBNET={local_subnet}) — pas d'allocation.")
                return 0
            if allocate_subnet_locally(
                    ENV_PATH, reason="Hub non configuré (HUB_HOST/APP_SLUG absents)"):
                return 0
            return 1
        print("❌ HUB_HOST ou APP_SLUG manquant dans .env — allocation impossible.")
        return 1

    # Réconciliation : ports figés ou non, le Hub fait autorité sur
    # l'allocation (sinon elle n'est jamais enregistrée côté Hub).
    url = f"http://{hub_host}:{hub_api_port}/api/apps/allocate-ports"
    body = {"slug": slug}
    if host:
        body["host"] = host
    desired = None
    if api_port and frontend_port:
        try:
            desired = {"api_port": int(api_port), "frontend_port": int(frontend_port)}
        except ValueError:
            desired = None  # ports non numériques : on laisse le Hub décider
    if desired:
        body.update(desired)

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
    conflict: Exception | None = None
    last_err: Exception | None = None
    for candidate in candidates:
        print(f"🎰 Demande d'allocation de ports au Hub: {candidate} "
              f"(slug={slug}, host={host or 'auto'}"
              + (f", souhaités API={api_port}/FRONTEND={frontend_port}" if desired else "")
              + ")")
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
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 409:
                # Réponse définitive du Hub (divergence/conflit) : inutile de
                # réessayer via un autre candidat, et aucune écriture.
                conflict = e
                break
            if candidate != candidates[-1]:
                print(f"⚠️  {candidate} indisponible ({e}) — nouvel essai via {candidates[-1]}")
        except Exception as e:
            last_err = e
            if candidate != candidates[-1]:
                print(f"⚠️  {candidate} indisponible ({e}) — nouvel essai via {candidates[-1]}")

    if conflict is not None:
        print(f"❌ Le Hub signale un conflit d'allocation (HTTP 409) : ports "
              f"pris ou divergents pour (slug={slug}, host={host or 'auto'}) — "
              "aucune écriture du .env. Vérifiez les allocations côté Hub.")
        return 1

    if data is None:
        # Hub injoignable ou sans endpoint d'allocation sur tous les candidats.
        if api_port and frontend_port:
            # Ports figés localement : seul le subnet peut manquer.
            if local_subnet:
                print(f"⚠️  Hub injoignable ({last_err}) — configuration locale "
                      f"complète (API={api_port}, FRONTEND={frontend_port}, "
                      f"SUBNET={local_subnet}) ; réconciliation reportée.")
                return 0
            if allocate_subnet_locally(
                    ENV_PATH,
                    reason=(f"Hub injoignable ({last_err}) — ports figés "
                            f"localement conservés (API={api_port}, "
                            f"FRONTEND={frontend_port})")):
                return 0
            return 1
        # Ports absents : best-effort subnet, mais l'allocation reste bloquante.
        allocate_subnet_locally(
            ENV_PATH,
            reason="Hub injoignable — sous-réseau alloué localement, ports toujours manquants")
        print(f"❌ Échec de l'allocation des ports auprès du Hub: {last_err}")
        return 1

    resp_api = str(data["api_port"])
    resp_frontend = str(data["frontend_port"])
    resp_https = str(data["frontend_https_port"])
    resp_subnet = str(data.get("subnet") or "").strip()
    reused = bool(data.get("reused"))

    if desired is None:
        # Ports absents du .env : adoption complète de la réponse (historique).
        set_env_var(ENV_PATH, "API_PORT", resp_api)
        set_env_var(ENV_PATH, "FRONTEND_PORT", resp_frontend)
        set_env_var(ENV_PATH, "FRONTEND_HTTPS_PORT", resp_https)
        if resp_subnet:
            set_env_var(ENV_PATH, "APP_SUBNET", resp_subnet)
        else:
            # Hub neuf qui ne renvoie pas son champ subnet : même fallback local.
            allocate_subnet_locally(ENV_PATH,
                                    reason="Hub neuf sans champ subnet dans la réponse")
        print(f"✅ Ports alloués par le Hub: API={resp_api}, FRONTEND={resp_frontend}, "
              f"HTTPS={resp_https}, SUBNET={resp_subnet or '—'}")
        return 0

    if resp_api == api_port and resp_frontend == frontend_port:
        if reused:
            # Le Hub avait déjà exactement cette allocation : no-op, sauf le
            # subnet (pool Hub) si le .env n'en a pas.
            if resp_subnet and not local_subnet:
                set_env_var(ENV_PATH, "APP_SUBNET", resp_subnet)
                print(f"✅ Déjà aligné avec le Hub (API={api_port}, "
                      f"FRONTEND={frontend_port}) — APP_SUBNET={resp_subnet} "
                      "adopté du pool Hub.")
            else:
                print(f"✅ Déjà aligné avec le Hub (API={api_port}, "
                      f"FRONTEND={frontend_port}) — aucune modification.")
            return 0
        # Allocation fraîche créée sur les ports souhaités : adoption complète.
        set_env_var(ENV_PATH, "API_PORT", resp_api)
        set_env_var(ENV_PATH, "FRONTEND_PORT", resp_frontend)
        set_env_var(ENV_PATH, "FRONTEND_HTTPS_PORT", resp_https)
        if resp_subnet and not local_subnet:
            set_env_var(ENV_PATH, "APP_SUBNET", resp_subnet)
        elif not resp_subnet and not local_subnet:
            allocate_subnet_locally(ENV_PATH,
                                    reason="Hub neuf sans champ subnet dans la réponse")
        print(f"✅ Ports alloués par le Hub aux valeurs souhaitées: "
              f"API={resp_api}, FRONTEND={resp_frontend}, HTTPS={resp_https}, "
              f"SUBNET={resp_subnet or '—'}")
        return 0

    # Hub ancien : desired ignorés, allocation créée sur SES propres ports.
    # Les ports locaux (source de vérité du déploiement) ne sont PAS touchés.
    if resp_subnet and not local_subnet:
        set_env_var(ENV_PATH, "APP_SUBNET", resp_subnet)
    print(f"⚠️  Le Hub a enregistré une allocation sur d'autres ports "
          f"(API={resp_api}, FRONTEND={resp_frontend}) : les ports souhaités "
          f"(API={api_port}, FRONTEND={frontend_port}) ont été ignorés par ce "
          "Hub — ports locaux CONSERVÉS. Mettez le Hub à jour (support des "
          "ports souhaités) puis relancez `make sync-env`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
