#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
Tests de set_app_subnet.py — autonomes, sans Docker ni pytest.

Vérifie que l'écriture MANUELLE de APP_SUBNET est sûre : jamais d'écrasement
sans --force, jamais de subnet en conflit avec un réseau Docker existant ou un
.env voisin, jamais de clé dupliquée, backup horodaté avant modification.

Usage :
    python3 scripts/test_set_app_subnet.py          # 0 = succès
    python3 scripts/test_set_app_subnet.py -v       # détail des cas

Couverture :
   1. APP_SUBNET vide + --subnet explicite → écrit, 1 occurrence, backup créé
   2. Clé ABSENTE du .env → ajoutée UNE fois, en fin
   3. Idempotence : 2e exécution même valeur → no-op (aucun backup)
   4. Valeur existante différente SANS --force → refus, .env intact
   5. Valeur existante différente AVEC --force → écrasée + backup
   6. CIDR invalide → refus propre, aucune écriture
   7. Conflit réseau Docker actif → refus, aucune écriture
   8. Conflit .env voisin (app éteinte) → refus, aucune écriture
   9. Auto-allocation : premier /24 libre de 10.220.0.0/16 hors pris
  10. --check : aucune écriture, aucun backup
  11. .env inexistant → refus propre (exit 1, aucune création)
  12. Docker indisponible + voisin muet → dégradation OK (subnet alloué, warning)
"""

import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VERBOSE = "-v" in sys.argv

FAILURES = []
CASES = []


def load_module(tmp_root, docker_subnets=([], True), neighbor_subnets=frozenset()):
    """Charge set_app_subnet.py avec REPO_ROOT sur le bac à sable, Docker mocké."""
    spec = importlib.util.spec_from_file_location(
        "set_app_subnet_under_test", os.path.join(HERE, "set_app_subnet.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.REPO_ROOT = tmp_root
    mod.docker_subnets = lambda: (set(docker_subnets[0]), docker_subnets[1])
    mod.neighbor_subnets = lambda root: set(neighbor_subnets)
    return mod


def write_env(tmp_root, content, name=".env"):
    path = os.path.join(tmp_root, name)
    with open(path, "w") as fh:
        fh.write(content)
    return path


def run_main(mod, *argv):
    old_argv = sys.argv
    sys.argv = ["set_app_subnet.py", *argv]
    try:
        return mod.main()
    finally:
        sys.argv = old_argv


def read(path):
    with open(path) as fh:
        return fh.read()


def occurrences(content, key):
    return sum(1 for line in content.splitlines()
               if line.split("=", 1)[0] == key)


def backups(tmp_root):
    return [f for f in os.listdir(tmp_root) if f.startswith(".env.pre-subnet-")]


def case(name):
    def deco(fn):
        def wrapper():
            if VERBOSE:
                print(f"--- {name}")
            tmp = tempfile.mkdtemp(prefix="subnet-test-")
            try:
                fn(tmp)
                if VERBOSE:
                    print(f"    ✅ {name}")
            except AssertionError as exc:
                FAILURES.append(f"{name} : {exc}")
                print(f"    ❌ {name} : {exc}")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        CASES.append((name, wrapper))
        return wrapper
    return deco


@case("1. APP_SUBNET vide + --subnet explicite → écrit, 1 occurrence, backup")
def _(tmp):
    mod = load_module(tmp)
    env = write_env(tmp, "APP_SLUG=test-app\nAPP_SUBNET=\nAPI_PORT=9000\n")
    assert run_main(mod, "--env", env, "--subnet", "10.220.7.0/24") == 0
    content = read(env)
    assert "APP_SUBNET=10.220.7.0/24" in content, "subnet non écrit"
    assert occurrences(content, "APP_SUBNET") == 1, "clé dupliquée"
    assert "API_PORT=9000" in content, "ligne voisine altérée"
    assert len(backups(tmp)) == 1, "backup horodaté manquant"


@case("2. clé ABSENTE du .env → ajoutée une fois, en fin")
def _(tmp):
    mod = load_module(tmp)
    env = write_env(tmp, "APP_SLUG=test-app\nAPI_PORT=9000\n")
    assert run_main(mod, "--env", env, "--subnet", "10.220.2.0/24") == 0
    content = read(env)
    assert occurrences(content, "APP_SUBNET") == 1, "duplication APP_SUBNET"
    assert "APP_SUBNET=10.220.2.0/24" in content, "clé non ajoutée"
    assert content.splitlines()[-1] == "APP_SUBNET=10.220.2.0/24", "ajout non en fin"


@case("3. idempotence : 2e exécution même valeur → no-op")
def _(tmp):
    mod = load_module(tmp)
    env = write_env(tmp, "APP_SUBNET=10.220.3.0/24\n")
    assert run_main(mod, "--env", env, "--subnet", "10.220.3.0/24") == 0
    assert len(backups(tmp)) == 0, "backup créé sur un no-op"


@case("4. valeur existante différente SANS --force → refus, .env intact")
def _(tmp):
    mod = load_module(tmp)
    env = write_env(tmp, "APP_SUBNET=10.220.4.0/24\n")
    assert run_main(mod, "--env", env, "--subnet", "10.220.5.0/24") != 0, \
        "écrasement accepté sans --force !"
    assert "APP_SUBNET=10.220.4.0/24" in read(env), ".env modifié malgré le refus"
    assert len(backups(tmp)) == 0, "backup créé sans écriture"


@case("5. valeur existante différente AVEC --force → écrasée + backup")
def _(tmp):
    mod = load_module(tmp)
    env = write_env(tmp, "APP_SUBNET=10.220.4.0/24\n")
    assert run_main(mod, "--env", env, "--force", "--subnet", "10.220.5.0/24") == 0
    content = read(env)
    assert "APP_SUBNET=10.220.5.0/24" in content, "valeur non écrasée"
    assert occurrences(content, "APP_SUBNET") == 1, "duplication APP_SUBNET"
    assert len(backups(tmp)) == 1, "backup horodaté manquant"


@case("6. CIDR invalide → refus propre, aucune écriture")
def _(tmp):
    mod = load_module(tmp)
    env = write_env(tmp, "APP_SUBNET=\n")
    assert run_main(mod, "--env", env, "--subnet", "10.220.300.0/24") != 0
    assert "APP_SUBNET=" in read(env), "valeur écrite malgré CIDR invalide"


@case("7. conflit réseau Docker actif → refus, aucune écriture")
def _(tmp):
    mod = load_module(tmp, docker_subnets=(["10.220.6.0/24", "172.17.0.0/16"], True))
    env = write_env(tmp, "APP_SUBNET=\n")
    assert run_main(mod, "--env", env, "--subnet", "10.220.6.0/24") != 0, \
        "subnet en conflit accepté !"
    assert "APP_SUBNET=" in read(env), ".env modifié malgré le conflit"


@case("8. conflit .env voisin (app éteinte) → refus, aucune écriture")
def _(tmp):
    mod = load_module(tmp, neighbor_subnets={"10.220.9.0/24"})
    env = write_env(tmp, "APP_SUBNET=\n")
    assert run_main(mod, "--env", env, "--subnet", "10.220.9.0/24") != 0, \
        "subnet d'une app voisine réalloué !"
    assert "APP_SUBNET=" in read(env), ".env modifié malgré le conflit"


@case("9. auto-allocation : premier /24 libre de 10.220.0.0/16 hors pris")
def _(tmp):
    mod = load_module(tmp, docker_subnets=(["10.220.0.0/24", "10.220.1.0/24"], True))
    env = write_env(tmp, "APP_SUBNET=\n")
    assert run_main(mod, "--env", env) == 0
    assert "APP_SUBNET=10.220.2.0/24" in read(env), "mauvais /24 alloué (attendu 10.220.2.0/24)"


@case("10. --check : aucune écriture, aucun backup")
def _(tmp):
    mod = load_module(tmp)
    env = write_env(tmp, "APP_SUBNET=10.220.4.0/24\n")
    assert run_main(mod, "--env", env, "--check") == 0
    assert "APP_SUBNET=10.220.4.0/24" in read(env), ".env modifié en --check"
    assert len(backups(tmp)) == 0, "backup créé en --check"


@case("11. .env inexistant → refus propre, aucune création")
def _(tmp):
    mod = load_module(tmp)
    env = os.path.join(tmp, ".env")
    assert run_main(mod, "--env", env, "--subnet", "10.220.1.0/24") != 0
    assert not os.path.exists(env), ".env créé malgré l'absence"


@case("12. Docker indisponible + voisins muets → allocation quand même, warning")
def _(tmp):
    mod = load_module(tmp, docker_subnets=([], False), neighbor_subnets=set())
    env = write_env(tmp, "APP_SUBNET=\n")
    assert run_main(mod, "--env", env) == 0, "Docker absent doit rester best-effort"
    assert "APP_SUBNET=10.220.0.0/24" in read(env), "subnet non alloué sans Docker"


def main():
    for _, fn in CASES:
        fn()
    if FAILURES:
        print(f"\n❌ {len(FAILURES)} échec(s) :")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"✅ {len(CASES)} cas OK — set_app_subnet.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
