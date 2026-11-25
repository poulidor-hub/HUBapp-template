# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
Makefile : le compose lancé par `make` doit lire .env À CHAUD, pas le snapshot de make.

`include .env` + `export` (en-tête du Makefile) figent les valeurs AU PARSING.
`sync-env` — prérequis de build, up, dev, up-dev, et appelé par ensure-api-fresh —
réécrit .env pendant la même invocation (APP_SOCLE_VERSION, APP_VERSION, ports…).
Les valeurs exportées étaient donc périmées et, l'environnement du shell primant sur
.env pour l'interpolation compose, `make build` construisait l'API sur la version de
socle précédente à chaque montée (il fallait lancer le build deux fois).

Le Makefile retire les clés du .env de l'environnement de compose : il relit le fichier.

Ces tests exécutent le VRAI Makefile dans un bac à sable (tmp_path), sans build réel :
`sync-env` est remplacé par un `sed` (même effet d'écriture sur .env) et `docker` par un
stub en échec fermé qui enregistre ce que compose reçoit. Ils tournent sur l'hôte
(`make test`) ; sans `make` ni Makefile dans l'image api → ignorés en conteneur.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
# Local : <repo>/Makefile ; conteneur (/app/tests/) : pas de Makefile dans l'image → ignorés.
MAKEFILE = _HERE.parents[2] / "Makefile"

pytestmark = pytest.mark.skipif(
    shutil.which("make") is None or not MAKEFILE.is_file(),
    reason="ni make ni Makefile sur cet hôte (conteneur api) — test du Makefile non applicable",
)

# Clés que le sync-env simulé fait passer de 1.0.0 à 2.0.0 : elles ne doivent JAMAIS
# arriver à compose par l'environnement de make.
_STALE_KEYS = ("APP_SOCLE_VERSION", "APP_VERSION")

_COMPOSE = """\
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        - APP_VERSION=${APP_VERSION:-0.0.0}
        - SOCLE_VERSION=${APP_SOCLE_VERSION:?APP_SOCLE_VERSION manquant}
    ports:
      - "${API_PORT:-9045}:8000"

networks:
  default:
    ipam:
      config:
        - subnet: ${APP_SUBNET:?APP_SUBNET manquant}
"""

_ENV = """\
# .env tel que le parc l'écrit : valeurs non entre guillemets, espaces, commentaires
APP_SLUG=mon-app
APP_NAME=Mon Application
APP_VERSION=1.0.0
APP_SOCLE_VERSION=1.0.0

API_PORT=9045
APP_SUBNET=10.50.0.0/24
"""

# .env d'une app dont l'allocation n'a pas encore eu lieu : clés VIDES, comme dans
# .env.example (ou ajoutées vides par `make update-env`). sync-env les remplit.
_ENV_PORTS_VIDES = """\
APP_SLUG=mon-app
APP_VERSION=1.0.0
APP_SOCLE_VERSION=1.0.0

API_PORT=
APP_SUBNET=
"""

# sync-env simulé : même effet d'écriture que sync_socle_version.py + le sed APP_VERSION
# du Makefile (1.0.0 → 2.0.0), sans Hub ni image socle.
_OVERRIDE = """\
sync-env:
\t@test -f .env || printf 'APP_VERSION=1.0.0\\nAPP_SOCLE_VERSION=1.0.0\\nAPI_PORT=9045\\nAPP_SUBNET=10.50.0.0/24\\n' > .env; \\
\tsed -i 's/^APP_SOCLE_VERSION=.*/APP_SOCLE_VERSION=2.0.0/; s/^APP_VERSION=.*/APP_VERSION=2.0.0/' .env
"""

# sync-env simulé (variante) : allocation du port et du sous-réseau par allocate_ports.py.
_OVERRIDE_PORTS = """\
sync-env:
\t@sed -i 's/^API_PORT=.*/API_PORT=46904/; s|^APP_SUBNET=.*|APP_SUBNET=10.50.7.0/24|' .env
"""

_STUB_DOCKER = '''#!/usr/bin/env python3
"""Stub docker de test — AUCUN build réel ne peut partir (échec fermé).

`docker compose -f A.yml [-f B.yml …] build|up [options] [services…]` :
  STUB_MODE=record → enregistre {argv, env} dans $STUB_OUT/<n>.json, exit 0 ;
  STUB_MODE=config → lance le VRAI `docker compose -f … config --format json`
                     (résolution côté client, sans daemon), enregistre la sortie.
Tout le reste est refusé (exit 99).
"""
import json
import os
import pathlib
import subprocess
import sys


def refuse(argv):
    print("[stub-docker] REFUS (échec fermé) : docker " + " ".join(argv), file=sys.stderr)
    sys.exit(99)


argv = sys.argv[1:]
if not argv or argv[0] != "compose":
    refuse(argv)
files, rest = [], argv[1:]
while rest and rest[0] == "-f":
    if len(rest) < 2:
        refuse(argv)
    files.append(rest[1])
    rest = rest[2:]
mode, services = "", []
SANS_ARGUMENT = {"-d", "--build", "--no-cache", "--pull", "--force-recreate", "--follow"}
while rest:
    token = rest.pop(0)
    if token in ("build", "up", "logs") and not mode:
        mode = token
    elif token in SANS_ARGUMENT and mode:
        pass
    elif token == "-f" and mode == "logs":
        pass
    elif mode and token.replace("-", "").isalnum():
        services.append(token)
    else:
        refuse(argv)
if not mode:
    refuse(argv)

out = pathlib.Path(os.environ["STUB_OUT"])
out.mkdir(parents=True, exist_ok=True)
dest = out / f"{len(list(out.glob('*.json'))) + 1}.json"

if os.environ.get("STUB_MODE", "record") == "record":
    # JAMAIS l'environnement complet : un dict affiché par pytest fuirait les secrets
    # de l'hôte. Uniquement les clés demandées par le test (STUB_KEYS).
    wanted = set(os.environ.get("STUB_KEYS", "").split(","))
    recorded = {"argv": argv, "env": {k: v for k, v in os.environ.items() if k in wanted}}
    dest.write_text(json.dumps(recorded), encoding="utf-8")
    sys.exit(0)

self_dir = pathlib.Path(__file__).resolve().parent
real = next(
    (str(pathlib.Path(p) / "docker") for p in os.environ["PATH"].split(os.pathsep)
     if p and pathlib.Path(p).resolve() != self_dir
     and (pathlib.Path(p) / "docker").is_file() and os.access(pathlib.Path(p) / "docker", os.X_OK)),
    None,
)
if real is None:
    refuse(argv)
command = [real, "compose"] + [arg for f in files for arg in ("-f", f)] + ["config", "--format", "json"]
with open(dest, "w", encoding="utf-8") as fh:
    sys.exit(subprocess.call(command, stdout=fh))
'''

# Variables de l'hôte qui pourraient fausser le test : options de make héritées et
# clés manipulées ici.
_SCRUB = _STALE_KEYS + (
    "APP_SLUG", "APP_NAME", "API_PORT", "APP_SUBNET", "COMPOSE_PROJECT_NAME", "DOCKER_HOST",
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sandbox(
    tmp_path: Path,
    env_text: str | None = _ENV,
    files: dict[str, str] | None = None,
    override: str = _OVERRIDE,
) -> Path:
    """Bac à sable : .env + compose minimes, `sync-env` simulé, `docker` stubbé."""
    box = tmp_path / "app"
    if env_text is not None:
        _write(box / ".env", env_text)
    _write(box / "docker-compose.yml", _COMPOSE)
    _write(box / "Dockerfile", "FROM busybox\n")
    _write(box / "override.mk", override)
    # Le Makefile du bac à sable inclut le vrai + la surcharge : les sous-makes
    # (ensure-api-fresh → `$(MAKE) sync-env`) le trouvent ainsi sans option -f.
    _write(box / "Makefile", f"include {MAKEFILE}\ninclude override.mk\n")
    stub = box / "bin" / "docker"
    _write(stub, _STUB_DOCKER)
    stub.chmod(0o755)
    for rel, content in (files or {}).items():
        _write(box / rel, content)
    return box


def _run_make(box: Path, *goals: str, mode: str = "record") -> tuple[subprocess.CompletedProcess, list[dict]]:
    """`make <goals>` dans le bac à sable ; renvoie le processus et ce que le stub a
    enregistré (un bloc par appel compose)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MAKE", "MFLAGS", "GNUMAKEFLAGS"))}
    for key in _SCRUB:
        env.pop(key, None)
    env["PATH"] = f"{box / 'bin'}{os.pathsep}{env.get('PATH', os.defpath)}"
    env["STUB_OUT"] = str(box / "stub-out")
    env["STUB_MODE"] = mode
    env["STUB_KEYS"] = ",".join(_SCRUB)
    proc = subprocess.run(
        ["make", *goals],
        cwd=box, env=env, capture_output=True, text=True, timeout=180,
    )
    out = box / "stub-out"
    # En mode config, un compose en échec laisse un fichier vide : le code retour de
    # make (assertion du test) porte alors le diagnostic, pas une JSONDecodeError.
    records = (
        [json.loads(text) for p in sorted(out.glob("*.json"), key=lambda p: int(p.stem))
         if (text := p.read_text(encoding="utf-8")).strip()]
        if out.is_dir() else []
    )
    return proc, records


def _env_values(box: Path) -> dict[str, str]:
    """Clés-Version du .env du bac à sable (celles que le sync-env simulé réécrit)."""
    values = {}
    for line in (box / ".env").read_text(encoding="utf-8").splitlines():
        for key in _STALE_KEYS:
            if line.startswith(f"{key}="):
                values[key] = line.split("=", 1)[1]
    return values


def _assert_compose_sans_snapshot(calls: list[dict]) -> None:
    for call in calls:
        for key in _STALE_KEYS:
            assert key not in call["env"], (
                f"{key} figé au parsing ({call['env'].get(key)}) transmis à "
                f"`docker {' '.join(call['argv'])}` — compose l'aurait préféré au .env"
            )


@pytest.mark.parametrize("goal", ["build", "up", "up-dev", "dev"])
def test_compose_n_herite_pas_du_env_figure_au_parsing(tmp_path, goal):
    """build/up/dev : sync-env réécrit .env, compose ne reçoit pas les valeurs d'avant."""
    box = _sandbox(tmp_path, files={"scripts/generate-ssl.sh": "#!/bin/sh\nexit 0\n"})
    proc, calls = _run_make(box, goal)
    assert proc.returncode == 0, proc.stderr
    assert calls, "aucun appel compose intercepté"
    assert _env_values(box) == {"APP_SOCLE_VERSION": "2.0.0", "APP_VERSION": "2.0.0"}
    _assert_compose_sans_snapshot(calls)


def test_ensure_api_fresh_rebuild_avec_env_a_jour(tmp_path):
    """ensure-api-fresh (rebuild déclenché par make test-docker) : même protection —
    le sous-make de sync-env ne rafraîchit pas l'environnement du make parent."""
    box = _sandbox(tmp_path, files={
        "ACTIONS/PYTHON/check_image_freshness.py": "raise SystemExit(1)  # image périmée → rebuild\n",
    })
    proc, calls = _run_make(box, "ensure-api-fresh")
    assert proc.returncode == 0, proc.stderr
    assert [" ".join(c["argv"][3:]) for c in calls] == ["build api", "up -d api"]
    _assert_compose_sans_snapshot(calls)


def test_premiere_execution_sans_env(tmp_path):
    """Premier démarrage (pas de .env au parsing : créé par sync-env) : build OK, rien à retirer."""
    box = _sandbox(tmp_path, env_text=None)
    proc, calls = _run_make(box, "build")
    assert proc.returncode == 0, proc.stderr
    assert _env_values(box)["APP_SOCLE_VERSION"] == "2.0.0"
    assert len(calls) == 1
    _assert_compose_sans_snapshot(calls)


def test_surecharge_ligne_de_commande_reste_prioritaire(tmp_path):
    """`make build APP_VERSION=9.9.9` : la valeur explicite reste transmise à compose
    (comportement inchangé), le reste du .env est relu à chaud."""
    box = _sandbox(tmp_path)
    proc, calls = _run_make(box, "build", "APP_VERSION=9.9.9")
    assert proc.returncode == 0, proc.stderr
    assert len(calls) == 1
    assert calls[0]["env"]["APP_VERSION"] == "9.9.9"
    assert "APP_SOCLE_VERSION" not in calls[0]["env"]


def test_config_du_cli_compose_reste_transmise(tmp_path):
    """COMPOSE_*/DOCKER_*… : configuration du CLI et de compose, jamais réécrite par
    sync-env — elle reste transmise telle quelle, comme avant (des .env du parc en
    portent : COMPOSE_FILE, COMPOSE_PROJECT_NAME, DOCKER_HOST…)."""
    box = _sandbox(tmp_path, env_text=_ENV + "COMPOSE_PROJECT_NAME=mon-projet\nDOCKER_HOST=tcp://127.0.0.1:1\n")
    proc, calls = _run_make(box, "build")
    assert proc.returncode == 0, proc.stderr
    assert calls[0]["env"]["COMPOSE_PROJECT_NAME"] == "mon-projet"
    assert calls[0]["env"]["DOCKER_HOST"] == "tcp://127.0.0.1:1"
    assert "APP_SOCLE_VERSION" not in calls[0]["env"]


def test_cles_vides_remplies_par_sync_env_ne_sont_pas_transmises_vides(tmp_path):
    """Clés d'allocation VIDES au parsing (API_PORT=, APP_SUBNET=), remplies par
    sync-env : compose ne doit pas les recevoir vides. Une valeur vide dans
    l'environnement compte comme « définie » pour l'interpolation compose."""
    box = _sandbox(tmp_path, env_text=_ENV_PORTS_VIDES, override=_OVERRIDE_PORTS)
    proc, calls = _run_make(box, "build")
    assert proc.returncode == 0, proc.stderr
    assert len(calls) == 1
    assert "API_PORT" not in calls[0]["env"]
    assert "APP_SUBNET" not in calls[0]["env"]


def _docker_compose_available() -> bool:
    try:
        return subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _docker_compose_available(), reason="docker compose indisponible sur cet hôte")
def test_compose_construit_sur_la_version_a_jour_du_env(tmp_path):
    """Bout en bout (vrai `docker compose config`) : après sync-env, les args de build
    sont ceux du .env réécrit — SOCLE_VERSION pilote le FROM de Dockerfile.backend."""
    box = _sandbox(tmp_path)
    proc, models = _run_make(box, "build", mode="config")
    assert proc.returncode == 0, proc.stderr
    assert len(models) == 1
    assert models[0]["services"]["api"]["build"]["args"] == {
        "APP_VERSION": "2.0.0", "SOCLE_VERSION": "2.0.0",
    }


@pytest.mark.skipif(not _docker_compose_available(), reason="docker compose indisponible sur cet hôte")
def test_compose_resout_l_allocation_faite_pendant_l_invocation(tmp_path):
    """Bout en bout (vrai `docker compose config`) : les port et sous-réseau alloués
    par sync-env pendant l'invocation sont résolus. Avant correctif, compose recevait
    API_PORT= et APP_SUBNET= vides depuis l'environnement de make : `${API_PORT:-9045}`
    retombait sur 9045 et `${APP_SUBNET:?}` faisait échouer le build (« APP_SUBNET
    manquant ») — même classe que le contournement hubctl 0.25.1 sur
    FRONTEND_HTTPS_PORT (clés écrites avant tout make)."""
    box = _sandbox(tmp_path, env_text=_ENV_PORTS_VIDES, override=_OVERRIDE_PORTS)
    proc, models = _run_make(box, "build", mode="config")
    assert proc.returncode == 0, proc.stderr
    assert len(models) == 1
    assert models[0]["services"]["api"]["ports"][0]["published"] == "46904"
    assert models[0]["networks"]["default"]["ipam"]["config"][0]["subnet"] == "10.50.7.0/24"
