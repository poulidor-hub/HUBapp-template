"""Tests : register() pousse la version au hub même quand .hub_credentials existe.

Bug socle corrigé : register() court-circuitait quand les credentials existaient
déjà (fichier présent) et ne poussaient jamais la version → la carte du hub
affichait une version figée après chaque mise à jour de l'app.

Contrat :
- credentials avec version == APP_VERSION  → pas de ré-enregistrement (sync simple)
- credentials sans version (fichier legacy 2 lignes) → ré-enregistrement complet
- credentials avec version != APP_VERSION  → ré-enregistrement complet
- après _do_register(), le fichier sauvegardé contient la version (3e ligne)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import hub_client as hub_client_module
from hub_client import HubClient


def _write_credentials(path, client_id="cid", client_secret="sec", version=None):
    lines = [client_id, client_secret]
    if version is not None:
        lines.append(version)
    path.write_text("\n".join(lines))


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(hub_client_module, "CREDENTIALS_FILE", str(tmp_path / ".hub_credentials"))
    client = HubClient()
    # Empêche tout effet de bord réseau : register() ne doit pas faire d'HTTP
    # dans le chemin "credentials existants" ; _do_register est mocké.
    client._sync_state_to_hub = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_register_same_version_skips_reregister(tmp_path, monkeypatch):
    """Version identique → pas de ré-enregistrement, simple sync d'état."""
    _write_credentials(tmp_path / ".hub_credentials", version=hub_client_module.APP_VERSION)
    client = _make_client(tmp_path, monkeypatch)
    client._do_register = AsyncMock(return_value=True)

    assert await client.register() is True

    client._do_register.assert_not_awaited()
    client._sync_state_to_hub.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_legacy_file_without_version_triggers_reregister(tmp_path, monkeypatch):
    """Fichier legacy (2 lignes, sans version) → ré-enregistrement complet."""
    _write_credentials(tmp_path / ".hub_credentials")  # sans version
    client = _make_client(tmp_path, monkeypatch)
    client._do_register = AsyncMock(return_value=True)

    assert await client.register() is True

    client._do_register.assert_awaited_once()
    client._sync_state_to_hub.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_changed_version_triggers_reregister(tmp_path, monkeypatch):
    """Version stockée différente de APP_VERSION → ré-enregistrement complet."""
    _write_credentials(tmp_path / ".hub_credentials", version="0.0.1-old")
    client = _make_client(tmp_path, monkeypatch)
    client._do_register = AsyncMock(return_value=True)

    assert await client.register() is True

    client._do_register.assert_awaited_once()


@pytest.mark.asyncio
async def test_do_register_saves_version_in_credentials_file(tmp_path, monkeypatch):
    """Après _do_register() réussi, le fichier contient la version en 3e ligne."""
    import hub_client as hc

    client = _make_client(tmp_path, monkeypatch)

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "is_new": True,
        "credentials": {"client_id": "cid-new", "client_secret": "sec-new"},
    }
    mock_http = MagicMock()
    mock_http.post = AsyncMock(return_value=resp)
    monkeypatch.setattr(client, "_get_client", AsyncMock(return_value=mock_http))

    assert await client._do_register() is True

    lines = (tmp_path / ".hub_credentials").read_text().strip().split("\n")
    assert lines[0] == "cid-new"
    assert lines[1] == "sec-new"
    assert lines[2] == hc.APP_VERSION
