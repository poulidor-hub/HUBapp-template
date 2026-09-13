"""Tests du client hub_transfert (opt-in, endpoints dispatch HFT)."""
import httpx
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


class TestUploadFile:
    async def test_push_simple(self, enabled, tmp_path):
        pdf = tmp_path / "contrat.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")

        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["app_slug"] = request.headers.get("X-App-Slug")
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(201, json={"transfer_id": "t-1", "status": "pending"})

        transport = httpx.MockTransport(handler)
        fake_client = httpx.AsyncClient(transport=transport)

        with patch.object(hub_transfert, "_resolve",
                          AsyncMock(return_value=("http://hft", "tok"))), \
             patch.object(hub_transfert.hub_client, "_get_client",
                          AsyncMock(return_value=fake_client)):
            result = await hub_transfert.upload_file("flux-1", pdf)

        assert result == {"transfer_id": "t-1", "status": "pending"}
        assert captured["method"] == "POST"
        assert captured["url"].endswith("/api/dispatch/m2m/flux/flux-1/push")
        assert captured["app_slug"] == get_settings().APP_SLUG
        assert captured["auth"] == "Bearer tok"

    async def test_disabled_raises(self, disabled, tmp_path):
        with pytest.raises(HubTransfertDisabledError):
            await hub_transfert.upload_file("flux-1", tmp_path / "x.pdf")

    async def test_missing_file_raises(self, enabled, tmp_path):
        with pytest.raises(FileNotFoundError):
            await hub_transfert.upload_file("flux-1", tmp_path / "absent.pdf")


class TestUploadChunked:
    async def test_large_file_uses_sessions(self, enabled, tmp_path):
        big = tmp_path / "gros.pdf"
        chunk = b"x" * 1024
        big.write_bytes(chunk * 4)  # 4 KiB — seuil abaissé pour le test

        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.method == "POST" and request.url.path.endswith("/upload-sessions"):
                return httpx.Response(201, json={
                    "id": "sess-1", "chunk_size": 1024, "status": "uploading",
                    "files": [{"id": 7, "total_chunks": 4, "filename": "gros.pdf"}]})
            if request.method == "PUT" and "/chunks/" in request.url.path:
                return httpx.Response(200, json={
                    "session_id": "sess-1", "file_id": 7, "chunk_index": 0,
                    "size": 1024, "hash": "h", "received_chunks": 1,
                    "missing_chunks": [], "file_complete": False})
            if request.method == "POST" and request.url.path.endswith("/complete"):
                return httpx.Response(200, json={"id": 42, "status": "pending",
                                                 "filename": "gros.pdf"})
            return httpx.Response(404)

        fake_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.object(hub_transfert, "_resolve",
                          AsyncMock(return_value=("http://hft", "tok"))), \
             patch.object(hub_transfert.hub_client, "_get_client",
                          AsyncMock(return_value=fake_client)):
            result = await hub_transfert.upload_file("flux-1", big,
                                                     chunk_threshold=2048)
        assert result["id"] == 42
        # 1 create + 4 chunks + 1 complete
        assert sum(1 for m, _ in calls if m == "PUT") == 4
        assert any(p.endswith("/complete") for _, p in calls)

    async def test_chunk_failure_raises(self, enabled, tmp_path):
        big = tmp_path / "gros.pdf"
        big.write_bytes(b"x" * 4096)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and request.url.path.endswith("/upload-sessions"):
                return httpx.Response(201, json={
                    "id": "sess-1", "chunk_size": 1024, "files": [{"id": 7, "total_chunks": 4}]})
            return httpx.Response(500, text="boom")

        fake_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.object(hub_transfert, "_resolve",
                          AsyncMock(return_value=("http://hft", "tok"))), \
             patch.object(hub_transfert.hub_client, "_get_client",
                          AsyncMock(return_value=fake_client)):
            with pytest.raises(HubTransfertError):
                await hub_transfert.upload_file("flux-1", big, chunk_threshold=2048)


class TestDownload:
    async def test_download_streams_to_file(self, enabled, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/transfers/t-9/download")
            return httpx.Response(200, content=b"PDFDATA")

        fake_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        dest = tmp_path / "out.pdf"
        with patch.object(hub_transfert, "_resolve",
                          AsyncMock(return_value=("http://hft", "tok"))), \
             patch.object(hub_transfert.hub_client, "_get_client",
                          AsyncMock(return_value=fake_client)):
            result = await hub_transfert.download_file("t-9", dest)
        assert result == dest
        assert dest.read_bytes() == b"PDFDATA"


class TestWaitTransfer:
    async def test_wait_until_delivered(self, enabled):
        statuses = [{"status": "pending"}, {"status": "dispatching"},
                    {"status": "delivered"}]
        calls = {"n": 0}

        async def fake_status(transfer_id):
            s = statuses[min(calls["n"], len(statuses) - 1)]
            calls["n"] += 1
            return s

        with patch.object(hub_transfert, "transfer_status", fake_status), \
             patch.object(hub_transfert.asyncio, "sleep", AsyncMock()):
            result = await hub_transfert.wait_transfer("t-1", timeout=10, poll=0)
        assert result["status"] == "delivered"

    async def test_wait_timeout(self, enabled):
        async def fake_status(transfer_id):
            return {"status": "pending"}

        with patch.object(hub_transfert, "transfer_status", fake_status), \
             patch.object(hub_transfert.asyncio, "sleep", AsyncMock()):
            with pytest.raises(HubTransfertError, match="timeout"):
                await hub_transfert.wait_transfer("t-1", timeout=0.2, poll=0)
