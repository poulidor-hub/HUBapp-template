"""Tests du support binaire de call_discovered_service (design §3)."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch

import hub_client as hub_client_module
from hub_client import hub_client


def _fake_service():
    svc = AsyncMock()
    svc.api_url = "http://peer:9000"
    return svc


def _response(status=200, content=b'{"ok": true}', headers=None):
    return httpx.Response(status, content=content, headers=headers or {},
                          request=httpx.Request("GET", "http://peer/x"))


class TestBinaryModes:
    async def test_json_default_unchanged(self):
        with patch.object(hub_client, "get_service_by_slug",
                          AsyncMock(return_value=_fake_service())), \
             patch.object(hub_client, "get_m2m_token",
                          AsyncMock(return_value="tok")), \
             patch.object(hub_client, "_get_client",
                          AsyncMock(return_value=httpx.AsyncClient(
                              transport=httpx.MockTransport(
                                  lambda r: _response(200, b'{"ok": true}'))))):
            result = await hub_client.call_discovered_service("peer", "/api/x")
        assert result == {"ok": True}

    async def test_bytes_mode(self):
        with patch.object(hub_client, "get_service_by_slug",
                          AsyncMock(return_value=_fake_service())), \
             patch.object(hub_client, "get_m2m_token",
                          AsyncMock(return_value="tok")), \
             patch.object(hub_client, "_get_client",
                          AsyncMock(return_value=httpx.AsyncClient(
                              transport=httpx.MockTransport(
                                  lambda r: _response(200, b"%PDF-1.4"))))):
            result = await hub_client.call_discovered_service(
                "peer", "/api/file", response_format="bytes")
        assert result == b"%PDF-1.4"

    async def test_invalid_response_format_raises(self):
        with pytest.raises(ValueError, match="response_format"):
            await hub_client.call_discovered_service("peer", "/api/x", response_format="byts")

    async def test_timeout_passed_to_request(self):
        seen = {}

        def handler(request):
            return _response(200, b"{}")

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        original_request = real_client.request

        async def spy_request(method, url, **kwargs):
            seen.update(kwargs)
            return await original_request(method, url, **kwargs)

        real_client.request = spy_request
        with patch.object(hub_client, "get_service_by_slug",
                          AsyncMock(return_value=_fake_service())), \
             patch.object(hub_client, "get_m2m_token",
                          AsyncMock(return_value="tok")), \
             patch.object(hub_client, "_get_client", AsyncMock(return_value=real_client)):
            await hub_client.call_discovered_service("peer", "/api/x", timeout=123.0)
        assert seen.get("timeout") == 123.0

    async def test_binary_no_outbox_on_5xx(self):
        enq = AsyncMock()
        with patch.object(hub_client, "get_service_by_slug",
                          AsyncMock(return_value=_fake_service())), \
             patch.object(hub_client, "get_m2m_token",
                          AsyncMock(return_value="tok")), \
             patch.object(hub_client, "_get_client",
                          AsyncMock(return_value=httpx.AsyncClient(
                              transport=httpx.MockTransport(
                                  lambda r: _response(500, b"boom"))))), \
             patch.object(hub_client_module.outbox_service, "enqueue", enq):
            result = await hub_client.call_discovered_service(
                "peer", "/api/file", response_format="bytes")
        assert result is None
        enq.assert_not_called()

    async def test_binary_401_resync_retries(self):
        responses = [_response(401), _response(200, b"BIN")]
        idx = {"i": 0}

        def handler(request):
            r = responses[idx["i"]]
            idx["i"] += 1
            return r

        with patch.object(hub_client, "get_service_by_slug",
                          AsyncMock(return_value=_fake_service())), \
             patch.object(hub_client, "get_m2m_token",
                          AsyncMock(return_value="tok")), \
             patch.object(hub_client, "_get_client",
                          AsyncMock(return_value=httpx.AsyncClient(
                              transport=httpx.MockTransport(handler)))), \
             patch.object(hub_client, "_auto_resync", AsyncMock(return_value=True)):
            result = await hub_client.call_discovered_service(
                "peer", "/api/file", response_format="bytes")
        assert result == b"BIN"


class TestStreamMode:
    async def test_stream_returns_httpx_response(self):
        with patch.object(hub_client, "get_service_by_slug",
                          AsyncMock(return_value=_fake_service())), \
             patch.object(hub_client, "get_m2m_token",
                          AsyncMock(return_value="tok")), \
             patch.object(hub_client, "_get_client",
                          AsyncMock(return_value=httpx.AsyncClient(
                              transport=httpx.MockTransport(
                                  lambda r: _response(200, b"CHUNK"))))):
            result = await hub_client.call_discovered_service(
                "peer", "/api/stream", response_format="stream")
        assert isinstance(result, httpx.Response)
        assert result.status_code == 200
        await result.aclose()

    async def test_stream_401_resync_retries_keeps_mode(self):
        responses = [_response(401), _response(200, b"STREAM-OK")]
        idx = {"i": 0}

        def handler(request):
            r = responses[idx["i"]]
            idx["i"] += 1
            return r

        with patch.object(hub_client, "get_service_by_slug",
                          AsyncMock(return_value=_fake_service())), \
             patch.object(hub_client, "get_m2m_token",
                          AsyncMock(return_value="tok")), \
             patch.object(hub_client, "_get_client",
                          AsyncMock(return_value=httpx.AsyncClient(
                              transport=httpx.MockTransport(handler)))), \
             patch.object(hub_client, "_auto_resync", AsyncMock(return_value=True)):
            result = await hub_client.call_discovered_service(
                "peer", "/api/stream", response_format="stream")
        assert isinstance(result, httpx.Response)
        assert result.status_code == 200
        await result.aclose()

    async def test_stream_request_error_no_outbox(self):
        enq = AsyncMock()

        def handler(request):
            raise httpx.ConnectError("peer down", request=request)

        with patch.object(hub_client, "get_service_by_slug",
                          AsyncMock(return_value=_fake_service())), \
             patch.object(hub_client, "get_m2m_token",
                          AsyncMock(return_value="tok")), \
             patch.object(hub_client, "_get_client",
                          AsyncMock(return_value=httpx.AsyncClient(
                              transport=httpx.MockTransport(handler)))), \
             patch.object(hub_client_module.outbox_service, "enqueue", enq):
            result = await hub_client.call_discovered_service(
                "peer", "/api/stream", response_format="stream")
        assert result is None
        enq.assert_not_called()
