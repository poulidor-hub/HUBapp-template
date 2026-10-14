"""Tests du cycle de vie du client HTTP du HubClient.

Bug 2.30.2 : httpx.AsyncClient n'expose plus close() mais aclose() —
hub_client.close() levait AttributeError au shutdown de l'API
(« Application shutdown failed »).
"""
import httpx
import pytest

from hub_client import HubClient

pytestmark = pytest.mark.asyncio


class TestHubClientClose:
    async def test_close_disposes_shared_http_client(self):
        """close() ferme le client httpx partagé sans lever (aclose, pas close)."""
        client = HubClient()
        client._http_client = httpx.AsyncClient(timeout=1.0)

        await client.close()  # AttributeError avant fix (httpx >= 0.28)

        assert client._http_client is None

    async def test_close_idempotent_without_client(self):
        """close() sans client initialisé ne doit ni lever ni créer de client."""
        client = HubClient()
        await client.close()
        assert client._http_client is None
