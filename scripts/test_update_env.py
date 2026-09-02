#!/usr/bin/env python3
"""
Tests de non-duplication pour update_env.py — autonomes, sans Docker ni pytest.

Vérifie que la fusion B.0 ne crée JAMAIS de clé dupliquée et que le fix 2.20.2
(clés dérivées ABSENTES du .env désormais écrites) ne casse pas les cas où la
clé existe déjà avec une valeur.

Usage :
    python3 scripts/test_update_env.py          # 0 = succès
    python3 scripts/test_update_env.py -v       # détail des cas

Couverture :
  1. Clé présente AVEC valeur, dans l'exemple  → intouchée, 1 occurrence
  2. Clé présente AVEC valeur, orpheline       → intouchée, 1 occurrence
  3. Clé présente VIDE (FRONTEND_HTTPS_PORT=)  → remplacée EN PLACE, 1 occurrence
  4. Clé ABSENTE des deux côtés (fix 2.20.2)   → ajoutée UNE fois, en fin
  5a. Rien à faire (détecteur None, pas de FRONTEND_PORT) → aucune écriture/backup
  5b. Détecteur None + FRONTEND_PORT           → APP_SUBNET sauté, dérivée écrite
  6. Idempotence : 2e exécution = no-op (aucune écriture, aucun backup)
  7. Invariant global : chaque clé apparaît exactement une fois après fusion
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


def load_module(tmp_root):
    """Charge update_env.py avec REPO_ROOT pointant sur le bac à sable."""
    spec = importlib.util.spec_from_file_location(
        "update_env_under_test", os.path.join(HERE, "update_env.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.REPO_ROOT = tmp_root
    # Hermetique : jamais de docker dans les tests (fixe le subnet "réseau").
    mod.detect_app_subnet = lambda slug, repo: "10.99.0.0/24"
    return mod


def write_case(tmp_root, env, example, compose="services: {}\n"):
    with open(os.path.join(tmp_root, ".env"), "w") as fh:
        fh.write(env)
    with open(os.path.join(tmp_root, ".env.example"), "w") as fh:
        fh.write(example)
    with open(os.path.join(tmp_root, "docker-compose.yml"), "w") as fh:
        fh.write(compose)


def run_main(mod, tmp_root):
    import sys as _sys
    old_argv, old_root = _sys.argv, os.getcwd()
    _sys.argv = ["update_env.py"]
    try:
        return mod.main()
    finally:
        _sys.argv = old_argv
        os.chdir(old_root)


def read(tmp_root, name=".env"):
    with open(os.path.join(tmp_root, name)) as fh:
        return fh.read()


def occurrences(content, key):
    return sum(1 for line in content.splitlines()
               if line.split("=", 1)[0] == key)


def backups(tmp_root):
    return [f for f in os.listdir(tmp_root) if f.startswith(".env.pre-update-")]


def case(name):
    def deco(fn):
        def wrapper():
            if VERBOSE:
                print(f"--- {name}")
            tmp = tempfile.mkdtemp(prefix="updenv-test-")
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


@case("1. clé présente avec valeur, dans l'exemple → intouchée")
def _(tmp):
    mod = load_module(tmp)
    write_case(tmp,
               env="API_PORT=9000\nFRONTEND_PORT=4250\nIS_SHARED=true\n",
               example="API_PORT=1234\nFRONTEND_PORT=\nIS_SHARED=false\nFRONTEND_HTTPS_PORT=\n")
    assert run_main(mod, tmp) == 0
    content = read(tmp)
    assert "API_PORT=9000" in content, "valeur existante écrasée !"
    assert occurrences(content, "API_PORT") == 1, "duplication API_PORT"
    assert occurrences(content, "FRONTEND_HTTPS_PORT") == 1, "duplication FRONTEND_HTTPS_PORT"
    assert "FRONTEND_HTTPS_PORT=4251" in content, "dérivée FRONTEND_HTTPS_PORT incorrecte"


@case("2. clé présente avec valeur, orpheline (absente de l'exemple) → intouchée")
def _(tmp):
    mod = load_module(tmp)
    write_case(tmp,
               env="API_PORT=9000\nHUB_HTTPS_ENABLED=true\nAPP_VERSION=1.2.3\n",
               example="API_PORT=1234\nFRONTEND_PORT=4250\nFRONTEND_HTTPS_PORT=\n")
    assert run_main(mod, tmp) == 0
    content = read(tmp)
    assert "HUB_HTTPS_ENABLED=true" in content, "orpheline supprimée/modifiée !"
    assert occurrences(content, "HUB_HTTPS_ENABLED") == 1
    assert "APP_VERSION=1.2.3" in content and occurrences(content, "APP_VERSION") == 1


@case("3. clé présente VIDE → remplacée en place, pas de duplication")
def _(tmp):
    mod = load_module(tmp)
    write_case(tmp,
               env="FRONTEND_PORT=4250\nFRONTEND_HTTPS_PORT=\n",   # vide, pas absente
               example="FRONTEND_PORT=4250\nFRONTEND_HTTPS_PORT=\n")
    assert run_main(mod, tmp) == 0
    lines = read(tmp).splitlines()
    front = [l for l in lines if l.startswith("FRONTEND_HTTPS_PORT=")]
    assert len(front) == 1, f"duplication FRONTEND_HTTPS_PORT : {front}"
    assert front[0] == "FRONTEND_HTTPS_PORT=4251", "dérivée incorrecte"
    # Remplacement EN PLACE : la ligne garde sa position (index 1), elle n'est
    # pas ré-appendée en fin de fichier.
    assert lines[1] == "FRONTEND_HTTPS_PORT=4251", \
        f"remplacement pas en place : {lines}"


@case("4. clé ABSENTE des deux côtés (régression fix 2.20.2) → ajoutée une seule fois")
def _(tmp):
    mod = load_module(tmp)
    write_case(tmp,
               env="API_PORT=9000\nFRONTEND_PORT=4250\n",          # APP_SUBNET absent
               example="API_PORT=9000\nFRONTEND_PORT=4250\n")      # et absente de l'exemple
    assert run_main(mod, tmp) == 0
    content = read(tmp)
    assert occurrences(content, "APP_SUBNET") == 1, "clé absente non écrite ou dupliquée"
    assert "APP_SUBNET=10.99.0.0/24" in content, "mauvaise valeur dérivée"
    # Re-cas historique du bug : le rapport annonçait « fusionné » sans écrire.


@case("5a. rien à faire (pas de FRONTEND_PORT, détecteur None) → aucune écriture")
def _(tmp):
    mod = load_module(tmp)
    mod.detect_app_subnet = lambda slug, repo: None
    write_case(tmp,
               env="API_PORT=9000\n",                               # ni FRONTEND_PORT ni APP_SUBNET
               example="API_PORT=9000\n")
    assert run_main(mod, tmp) == 0
    assert read(tmp) == "API_PORT=9000\n", ".env modifié alors que rien n'était à faire"
    assert backups(tmp) == [], "backup créé alors que rien n'a changé"


@case("5b. détecteur réseau None → APP_SUBNET sauté, FRONTEND_HTTPS_PORT quand même dérivé")
def _(tmp):
    mod = load_module(tmp)
    mod.detect_app_subnet = lambda slug, repo: None
    write_case(tmp,
               env="API_PORT=9000\nFRONTEND_PORT=4250\n",
               example="API_PORT=9000\nFRONTEND_PORT=4250\n")
    assert run_main(mod, tmp) == 0
    content = read(tmp)
    assert "APP_SUBNET" not in content, "APP_SUBNET écrit malgré un détecteur None"
    assert "FRONTEND_HTTPS_PORT=4251" in content, "dérivée hors-Docker perdue"
    assert occurrences(content, "FRONTEND_HTTPS_PORT") == 1


@case("6. idempotence : 2e exécution = no-op (aucune écriture, aucun backup)")
def _(tmp):
    mod = load_module(tmp)
    write_case(tmp,
               env="API_PORT=9000\nFRONTEND_PORT=4250\nIS_SHARED=true\n",
               example="API_PORT=1234\nFRONTEND_PORT=\nIS_SHARED=false\nFRONTEND_HTTPS_PORT=\n")
    assert run_main(mod, tmp) == 0
    snapshot = read(tmp)
    nb_backups = len(backups(tmp))
    assert run_main(mod, tmp) == 0
    assert read(tmp) == snapshot, "2e exécution a modifié le .env (pas idempotent)"
    assert len(backups(tmp)) == nb_backups, "2e exécution a créé un backup inutile"


@case("7. invariant : chaque clé exactement une fois après fusion")
def _(tmp):
    mod = load_module(tmp)
    write_case(tmp,
               env="API_PORT=9000\nFRONTEND_PORT=4250\nPOSTGRES_PASSWORD=secret\n"
                   "HUB_INTERNAL_HOST=\n",                          # vide, orpheline
               example="API_PORT=1234\nFRONTEND_PORT=\nIS_SHARED=false\n"
                       "FRONTEND_HTTPS_PORT=\nAPP_SUBNET=\n")
    assert run_main(mod, tmp) == 0
    content = read(tmp)
    keys = [l.split("=", 1)[0] for l in content.splitlines()
            if l and not l.startswith("#") and "=" in l]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"clés dupliquées après fusion : {dupes}"
    assert "POSTGRES_PASSWORD=secret" in content, "secret existant écrasé !"
    assert "HUB_INTERNAL_HOST=" in content, "orpheline vide supprimée"


def main():
    for _, test in CASES:
        test()
    print()
    if FAILURES:
        print(f"❌ {len(FAILURES)} échec(s) :")
        for failure in FAILURES:
            print(f"   - {failure}")
        return 1
    print(f"✅ {len(CASES)} cas OK — update_env.py ne duplique rien, "
          "fix 2.20.2 couvert (clé absente écrite une fois, existantes intouchées).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
