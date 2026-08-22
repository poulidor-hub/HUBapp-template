#!/usr/bin/env python3
"""Tests unitaires de check_image_freshness.py — stdlib + pytest, docker mocké."""
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import check_image_freshness as cif


def _set_mtime(path, ts):
    """Fixe atime/mtime explicites (tests déterministes)."""
    os.utime(path, (ts, ts))


# --- find_newest_source ---

def test_find_newest_backend_file(tmp_path):
    backend = tmp_path / "backend"
    (backend / "tests").mkdir(parents=True)
    main = backend / "main.py"
    main.touch()
    test_x = backend / "tests" / "test_x.py"
    test_x.touch()
    _set_mtime(main, 1000)
    _set_mtime(test_x, 2000)
    newest, ts = cif.find_newest_source(tmp_path)
    assert newest == test_x
    assert ts == 2000


def test_find_newest_excludes_artifacts(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    main = backend / "main.py"
    main.touch()
    _set_mtime(main, 100)
    for rel in [
        "__pycache__/x.pyc",
        ".pytest_cache/CACHEDIR.TAG",
        "htmlcov/index.html",
        ".venv/lib.py",
        "venv/lib.py",
        ".coverage",
        ".coverage.123",
    ]:
        p = backend / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        _set_mtime(p, 99999)
    newest, ts = cif.find_newest_source(tmp_path)
    assert newest == main
    assert ts == 100


def test_find_newest_version_wins(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    main = backend / "main.py"
    main.touch()
    version = tmp_path / "VERSION"
    version.write_text("1.2.3\n")
    _set_mtime(main, 1000)
    _set_mtime(version, 3000)
    newest, ts = cif.find_newest_source(tmp_path)
    assert newest == version
    assert ts == 3000


def test_find_newest_dockerfile_wins(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "main.py").touch()
    _set_mtime(backend / "main.py", 1000)
    dockerfile = tmp_path / "Dockerfile.backend"
    dockerfile.write_text("FROM python:3.11-slim\n")
    _set_mtime(dockerfile, 4000)
    newest, ts = cif.find_newest_source(tmp_path)
    assert newest == dockerfile
    assert ts == 4000


def test_find_newest_empty_root_returns_none(tmp_path):
    assert cif.find_newest_source(tmp_path) is None


# --- parse_rfc3339 ---

def test_parse_rfc3339_plain_utc():
    dt = cif.parse_rfc3339("2026-08-22T14:35:02Z")
    assert dt == datetime(2026, 8, 22, 14, 35, 2, tzinfo=timezone.utc)


def test_parse_rfc3339_nanoseconds_truncated():
    dt = cif.parse_rfc3339("2026-08-22T14:35:02.123456789Z")
    assert dt.microsecond == 123456
    assert dt.tzinfo is not None


# --- couche docker (mockée) ---

def _make_fake_run(script):
    """Fabrique un fake de cif.run piloté par un dictionnaire {fragment: sortie}."""
    def fake_run(cmd):
        for fragment, out in script.items():
            if fragment in cmd:
                if isinstance(out, Exception):
                    raise out
                return out
        raise AssertionError(f"commande inattendue: {cmd}")
    return fake_run


def test_run_raises_on_nonzero():
    fake = type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()
    with patch.object(cif, "subprocess") as mock_sp:
        mock_sp.run.return_value = fake
        with pytest.raises(RuntimeError, match="boom"):
            cif.run(["docker", "ps"])


def test_main_fresh_returns_0(tmp_path, capsys):
    src = tmp_path / "backend" / "main.py"
    fake = _make_fake_run({
        "ps": "",
        "images": "sha256:abc",
        "image": "2026-08-22T14:35:02.123456789Z",
    })
    with patch.object(cif, "ROOT", tmp_path), \
         patch.object(cif, "find_newest_source", return_value=(src, 100.0)), \
         patch.object(cif, "run", side_effect=fake):
        assert cif.main() == 0
    assert "à jour" in capsys.readouterr().out


def test_main_stale_returns_1(tmp_path, capsys):
    src = tmp_path / "backend" / "main.py"
    fake = _make_fake_run({
        "ps": "",
        "images": "sha256:abc",
        "image": "1970-01-01T00:00:01Z",
    })
    with patch.object(cif, "ROOT", tmp_path), \
         patch.object(cif, "find_newest_source", return_value=(src, 100.0)), \
         patch.object(cif, "run", side_effect=fake):
        assert cif.main() == 1
    assert "périmée" in capsys.readouterr().out


def test_main_image_missing_returns_1(tmp_path, capsys):
    src = tmp_path / "backend" / "main.py"
    fake = _make_fake_run({"ps": "", "images": ""})
    with patch.object(cif, "ROOT", tmp_path), \
         patch.object(cif, "find_newest_source", return_value=(src, 100.0)), \
         patch.object(cif, "run", side_effect=fake):
        assert cif.main() == 1
    assert "introuvable" in capsys.readouterr().out


def test_main_dev_mode_returns_0(tmp_path, capsys):
    src = tmp_path / "backend" / "main.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.touch()
    _set_mtime(src, 9999999999)  # périmé si la garde s'appliquait
    import json
    mounts = json.dumps([
        {"Type": "bind", "Source": str(tmp_path / "backend"), "Destination": "/app"}
    ])
    fake = _make_fake_run({"ps": "abc123", "inspect": mounts})
    with patch.object(cif, "ROOT", tmp_path), \
         patch.object(cif, "run", side_effect=fake):
        assert cif.main() == 0
    assert "Mode dev" in capsys.readouterr().out


def test_main_docker_error_returns_2(tmp_path, capsys):
    src = tmp_path / "backend" / "main.py"
    fake = _make_fake_run({"ps": RuntimeError("docker: Cannot connect to the daemon")})
    with patch.object(cif, "ROOT", tmp_path), \
         patch.object(cif, "find_newest_source", return_value=(src, 100.0)), \
         patch.object(cif, "run", side_effect=fake):
        assert cif.main() == 2
    captured = capsys.readouterr()
    assert "erreur" in (captured.out + captured.err).lower()


def test_main_fs_error_returns_2(tmp_path, capsys):
    """TOCTOU : fichier source supprimé entre rglob et stat → OSError, pas exit 1."""
    with patch.object(cif, "ROOT", tmp_path), \
         patch.object(cif, "find_newest_source", side_effect=OSError("race")):
        assert cif.main() == 2
    captured = capsys.readouterr()
    assert "race" in (captured.out + captured.err)


def test_container_is_dev_null_mounts_returns_false(tmp_path):
    """docker inspect rend "null" pour un conteneur sans mounts → pas de crash."""
    fake = _make_fake_run({"inspect": "null"})
    with patch.object(cif, "run", side_effect=fake):
        assert cif.container_is_dev(tmp_path, "abc123") is False
