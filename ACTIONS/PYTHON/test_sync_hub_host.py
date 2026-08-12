#!/usr/bin/env python3
"""Tests unitaires de sync_hub_host.py — stdlib uniquement (pas de dépendance pytest externe)."""
import json
import socket
from unittest.mock import MagicMock

import sync_hub_host


# --- read_env ---

def test_read_env_parses_pairs(tmp_path):
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=1.2.3.4\nHUB_API_PORT=8000\n")
    result = sync_hub_host.read_env(env)
    assert result == {"HUB_HOST": "1.2.3.4", "HUB_API_PORT": "8000"}


def test_read_env_ignores_comments_and_blank(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# un commentaire\n\nHUB_HOST=1.2.3.4\n  \n")
    result = sync_hub_host.read_env(env)
    assert result == {"HUB_HOST": "1.2.3.4"}


def test_read_env_missing_file_returns_empty(tmp_path):
    result = sync_hub_host.read_env(tmp_path / "absent.env")
    assert result == {}


# --- set_env_var ---

def test_set_env_var_updates_existing_returns_true(tmp_path):
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=old\n")
    changed = sync_hub_host.set_env_var(env, "HUB_HOST", "new")
    assert changed is True
    assert env.read_text() == "HUB_HOST=new\n"


def test_set_env_var_no_change_returns_false(tmp_path):
    env = tmp_path / ".env"
    env.write_text("HUB_HOST=same\n")
    changed = sync_hub_host.set_env_var(env, "HUB_HOST", "same")
    assert changed is False
    assert env.read_text() == "HUB_HOST=same\n"


def test_set_env_var_appends_missing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("API_PORT=8000\n")
    changed = sync_hub_host.set_env_var(env, "HUB_HOST", "1.2.3.4")
    assert changed is True
    content = env.read_text()
    assert "API_PORT=8000" in content
    assert "HUB_HOST=1.2.3.4" in content


# --- get_local_ip ---

def test_get_local_ip_returns_ip(monkeypatch):
    fake_sock = MagicMock()
    fake_sock.getsockname.return_value = ("192.0.2.12", 12345)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake_sock)
    assert sync_hub_host.get_local_ip() == "192.0.2.12"


def test_get_local_ip_excludes_docker_172(monkeypatch):
    fake_sock = MagicMock()
    fake_sock.getsockname.return_value = ("172.17.0.1", 12345)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake_sock)
    assert sync_hub_host.get_local_ip() is None


def test_get_local_ip_none_on_oserror(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(socket, "socket", boom)
    assert sync_hub_host.get_local_ip() is None
