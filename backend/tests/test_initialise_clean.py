# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
Cohérence du mode --clean d'INITIALISE (suite directe du lot 2.32.0).

Une app scaffoldée en --clean ne doit pas emporter de tests pour du code
retiré : test_services.py couvre les endpoints démo /api/tests/* (désactivés
par défaut, ENABLE_DEMO_ENDPOINTS=false) — il doit suivre le sort des autres
tests démo. La migration 001 ne doit plus altérer la table démo `items`
(absente en --clean → warning au boot) ; l'ALTER items migre en 010 avec
ALTER TABLE IF EXISTS (splitter SQL naïf sur ';' : pas de DO block).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# Repo : <repo>/backend/migrations ; conteneur : /app/migrations (COPY backend/).
_HERE = Path(__file__).resolve()
for _candidate in (_HERE.parents[2] / "backend" / "migrations", _HERE.parents[1] / "migrations"):
    if (_candidate / "001_fix_datetime_timezone.sql").is_file():
        MIGRATIONS_DIR = _candidate
        break
else:
    pytest.skip("migrations introuvables", allow_module_level=True)


def test_migration_001_no_longer_alters_demo_items_table():
    sql_001 = (MIGRATIONS_DIR / "001_fix_datetime_timezone.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE items\n" not in sql_001, \
        "001 ne doit plus altérer la table démo items (absente en --clean)"

    sql_010 = (MIGRATIONS_DIR / "010_fix_items_tz_clean_safe.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE IF EXISTS items" in sql_010, \
        "l'ALTER items migre en 010, protégé par IF EXISTS (splitter SQL naïf : pas de DO block)"
    assert "begin;" not in sql_010.lower(), "pas de DO block : statements simples uniquement"


# Repo : <repo>/ACTIONS/PYTHON/INITIALISE.py — absent de l'image api
# (script de scaffold) : test repo-only.
ACTIONS_INIT = _HERE.parents[2] / "ACTIONS" / "PYTHON" / "INITIALISE.py"
if not ACTIONS_INIT.is_file():
    pytest.skip("INITIALISE.py absent de l'image api — test repo-only", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("initmod", ACTIONS_INIT)
initmod = importlib.util.module_from_spec(_spec)
sys.modules["initmod"] = initmod
_spec.loader.exec_module(initmod)


def test_clean_demo_tests_removes_services_tests(tmp_path):
    tests_dir = tmp_path / "backend" / "tests"
    tests_dir.mkdir(parents=True)
    demo_tests = [
        "test_auth.py", "test_items.py", "test_backup.py", "test_services.py",
        "test_backup_stats.py", "test_backup_streaming.py",
        "test_hub_data.py", "test_backup_restore_order.py",
    ]
    for name in demo_tests:
        (tests_dir / name).write_text("# demo\n", encoding="utf-8")

    assert initmod._clean_demo_tests(tmp_path) is True
    for name in demo_tests:
        assert not (tests_dir / name).exists(), \
            f"test démo {name} doit partir en --clean (code démo retiré de l'app)"


def test_manifest_non_dict_actionable(tmp_path, capsys):
    """F4 (revue 2.32.0) : JSON valide mais non-objet → exit 1 actionnable, pas de traceback."""
    scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import update_design_system as uds

    src = tmp_path / "HUBCSS"
    src.mkdir()
    (src / "manifest.json").write_text("[1,2,3]", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        uds.load_manifest(src)
    assert excinfo.value.code == 1
    assert "invalide" in capsys.readouterr().err
