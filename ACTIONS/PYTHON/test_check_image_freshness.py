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
