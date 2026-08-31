"""Tests de la re-synchro des certs HTTPS émis par la PKI du HUB."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cert_sync import _get_ssl_dir, _same_content, _write_if_changed, CERT_FILES

PEM_CERT = "-----BEGIN CERTIFICATE-----\nCERTPEM\n-----END CERTIFICATE-----\n"
PEM_KEY = "-----BEGIN PRIVATE KEY-----\nKEYPEM\n-----END PRIVATE KEY-----\n"
PEM_CA = "-----BEGIN CERTIFICATE-----\nCAPEM\n-----END CERTIFICATE-----\n"


def test_same_content_detects_difference(tmp_path):
    f = tmp_path / "a.pem"
    f.write_text("AAA")
    assert _same_content(tmp_path, "a.pem", "AAA") is True
    assert _same_content(tmp_path, "a.pem", "BBB") is False
    assert _same_content(tmp_path, "missing.pem", "AAA") is False


def test_write_if_changed_writes_and_reports(tmp_path):
    changed = _write_if_changed(tmp_path, "server.crt", "PEM1")
    assert changed is True and (tmp_path / "server.crt").read_text() == "PEM1"
    changed2 = _write_if_changed(tmp_path, "server.crt", "PEM1")
    assert changed2 is False


def test_ssl_dir_default_is_project_root_ssl(monkeypatch):
    """Sans SSL_DIR : <racine projet>/ssl (le ssl/ monté à la racine du dépôt)."""
    monkeypatch.delenv("SSL_DIR", raising=False)
    import cert_sync
    expected = Path(cert_sync.__file__).resolve().parent.parent / "ssl"
    assert _get_ssl_dir() == expected


def test_ssl_dir_env_override(monkeypatch):
    """En conteneur, SSL_DIR=/app/ssl (volume ./ssl:/app/ssl) doit être honoré."""
    monkeypatch.setenv("SSL_DIR", "/app/ssl")
    assert _get_ssl_dir() == Path("/app/ssl")


async def test_sync_certs_once_writes_then_noop(tmp_path, monkeypatch):
    """Intégration : 1er appel écrit les fichiers + reload, 2e appel ne fait rien."""
    import cert_sync

    cert_data = {"cert": PEM_CERT, "key": PEM_KEY, "ca": PEM_CA, "san": ["mon-app.local"]}

    monkeypatch.setattr(cert_sync, "_get_ssl_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "hub_client.hub_client.fetch_app_cert", AsyncMock(return_value=cert_data)
    )
    reload_calls = []
    monkeypatch.setattr(cert_sync, "_reload_nginx", lambda: reload_calls.append(1))

    # 1er appel : fichiers écrits, reload déclenché
    changed = await cert_sync.sync_certs_once()
    assert changed is True
    assert (tmp_path / "server.crt").read_text() == PEM_CERT
    assert (tmp_path / "server.key").read_text() == PEM_KEY
    assert (tmp_path / "ca.crt").read_text() == PEM_CA
    assert len(reload_calls) == 1

    # 2e appel : contenu identique → pas de réécriture ni reload
    changed2 = await cert_sync.sync_certs_once()
    assert changed2 is False
    assert len(reload_calls) == 1


async def test_sync_certs_once_no_cert_returns_false(tmp_path, monkeypatch):
    """Si le HUB ne renvoie pas de cert (erreur/réseau), on ne touche à rien."""
    import cert_sync

    monkeypatch.setattr(cert_sync, "_get_ssl_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "hub_client.hub_client.fetch_app_cert", AsyncMock(return_value=None)
    )
    reload_calls = []
    monkeypatch.setattr(cert_sync, "_reload_nginx", lambda: reload_calls.append(1))

    assert await cert_sync.sync_certs_once() is False
    assert not (tmp_path / "server.crt").exists()
    assert reload_calls == []
