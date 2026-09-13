"""Tests du client hub_transfert (opt-in, endpoints dispatch HFT)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config import get_settings
import hub_transfert
from hub_transfert import HubTransfertError, HubTransfertDisabledError


class _FakeService:
    def __init__(self, api_url):
        self.api_url = api_url


@pytest.fixture
def enabled(monkeypatch):
    """Force le flag opt-in à True pour la durée du test (env + reset cache lru_cache)."""
    monkeypatch.setenv("HUB_TRANSFERT_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def disabled(monkeypatch):
    """Force le flag opt-in à False pour la durée du test."""
    monkeypatch.setenv("HUB_TRANSFERT_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestOptInGuard:
    async def test_disabled_raises(self, disabled):
        with pytest.raises(HubTransfertDisabledError, match="HUB_TRANSFERT_ENABLED"):
            await hub_transfert.list_flux()

    async def test_enabled_passes_guard(self, enabled):
        # Settings reconstruits depuis l'env (flag True) — on mock la résolution
        # pour isoler le garde.
        with patch.object(hub_transfert, "_resolve",
                          AsyncMock(return_value=("http://hft:1", "tok"))):
            with patch.object(hub_transfert, "_request",
                              AsyncMock(return_value=MagicMock(json=lambda: []))):
                result = await hub_transfert.list_flux()
        assert result == []


class TestResolve:
    async def test_service_not_found(self, enabled):
        with patch("hub_transfert.hub_client") as fake:
            fake.get_service_by_slug = AsyncMock(return_value=None)
            with pytest.raises(HubTransfertError, match="introuvable"):
                await hub_transfert._resolve("exemple-app")

    async def test_service_resolved(self, enabled):
        with patch("hub_transfert.hub_client") as fake:
            fake.get_service_by_slug = AsyncMock(return_value=_FakeService("http://192.0.2.10:46655"))
            fake.get_m2m_token = AsyncMock(return_value="tok")
            api_url, token = await hub_transfert._resolve("exemple-app")
        assert api_url == "http://192.0.2.10:46655"
        assert token == "tok"
