from pathlib import Path
from unittest.mock import patch

import pytest

from hub_client import HubClient


def test_load_depends_yaml_returns_empty_when_absent(tmp_path):
    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", tmp_path / "nonexistent.yaml"):
        assert client._load_depends_yaml() == []


def test_load_depends_yaml_reads_entries(tmp_path):
    f = tmp_path / "depends.yaml"
    f.write_text(
        "depends_on:\n"
        "  - slug: exemple-app-2\n"
        "    note: Catalogue\n"
        "  - slug: exemple-app\n"
    )
    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", f):
        result = client._load_depends_yaml()
    assert result == [
        {"slug": "exemple-app-2", "note": "Catalogue"},
        {"slug": "exemple-app"},
    ]


def test_load_depends_yaml_returns_empty_when_no_depends_on_key(tmp_path):
    f = tmp_path / "depends.yaml"
    f.write_text("# just a comment\n")
    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", f):
        assert client._load_depends_yaml() == []


def test_load_depends_yaml_returns_empty_on_corrupted_yaml(tmp_path):
    f = tmp_path / "depends.yaml"
    f.write_text("depends_on: [[unclosed")
    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", f):
        assert client._load_depends_yaml() == []


async def _async_true():
    return True


@pytest.mark.asyncio
async def test_register_sends_dependencies_to_hub(monkeypatch, tmp_path):
    """register() réussit puis envoie le depends.yaml au hub via call_hub_endpoint."""
    f = tmp_path / "depends.yaml"
    f.write_text("depends_on:\n  - slug: exemple-app-2\n")

    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", f):
        monkeypatch.setattr(client, "_do_register", lambda: _async_true())
        monkeypatch.setattr(client, "_load_credentials_from_file", lambda: False)

        calls = []
        async def fake_call(endpoint, method="GET", **kwargs):
            calls.append((endpoint, method, kwargs))
            return {"status_code": 200}
        monkeypatch.setattr(client, "call_hub_endpoint", fake_call)

        result = await client.register()
        assert result is True

    dep_calls = [c for c in calls if c[0] == "/api/apps/dependencies"]
    assert len(dep_calls) == 1
    assert dep_calls[0][1] == "POST"
    assert dep_calls[0][2]["json"] == {"depends_on": [{"slug": "exemple-app-2"}]}


@pytest.mark.asyncio
async def test_register_does_not_crash_if_depends_send_fails(monkeypatch, tmp_path):
    """Si l'envoi échoue, register() a quand même réussi (non bloquant)."""
    f = tmp_path / "depends.yaml"
    f.write_text("depends_on:\n  - slug: exemple-app-2\n")

    client = HubClient()
    with patch("hub_client.DEPENDS_FILE", f):
        monkeypatch.setattr(client, "_do_register", lambda: _async_true())
        monkeypatch.setattr(client, "_load_credentials_from_file", lambda: False)

        async def failing_call(endpoint, method="GET", **kwargs):
            raise Exception("network down")
        monkeypatch.setattr(client, "call_hub_endpoint", failing_call)

        result = await client.register()
        assert result is True


@pytest.mark.asyncio
async def test_report_sync_calls_endpoint(monkeypatch):
    client = HubClient()
    calls = []
    async def fake_call(endpoint, method="GET", **kwargs):
        calls.append((endpoint, method, kwargs))
        return {"status_code": 200}
    monkeypatch.setattr(client, "call_hub_endpoint", fake_call)

    await client.report_sync("exemple-app-2")

    assert len(calls) == 1
    assert calls[0][0] == "/api/apps/sync-report"
    assert calls[0][1] == "POST"
    assert calls[0][2]["json"] == {"target": "exemple-app-2"}


@pytest.mark.asyncio
async def test_report_sync_swallows_exceptions(monkeypatch):
    """report_sync ne lève jamais (best-effort)."""
    client = HubClient()
    async def failing_call(endpoint, method="GET", **kwargs):
        raise Exception("network down")
    monkeypatch.setattr(client, "call_hub_endpoint", failing_call)

    # Ne doit pas lever
    await client.report_sync("exemple-app-2")
