"""
T2a (self-healing M2M) : _recover_credentials doit passer par le
ré-enregistrement trusted (POST /api/apps/register) et non par
regenerate-secret (voie morte : exige un token M2M valide, or le secret
est précisément ce qu'on a perdu).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from hub_client import HubClient


def _register_ok_response():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "is_new": False,
        "credentials": {
            "client_id": "sa_test123",
            "client_secret": "secret_test456",
        },
    }
    return response


class TestRecoverCredentialsViaRegister:
    @pytest.mark.asyncio
    async def test_recover_calls_register_not_regenerate(self, tmp_path, monkeypatch):
        hub = HubClient()
        hub._credentials = None

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=_register_ok_response())
        hub._get_client = AsyncMock(return_value=mock_http)

        # Rediriger la persistance vers un tmp_dir isolé
        import hub_client
        monkeypatch.setattr(hub_client, "CREDENTIALS_FILE", str(tmp_path / ".hub_credentials"))

        ok = await hub._recover_credentials()

        assert ok is True
        # Un seul appel HTTP, vers register (PAS regenerate-secret)
        mock_http.post.assert_called_once()
        called_url = mock_http.post.call_args[0][0] if mock_http.post.call_args[0] else mock_http.post.call_args.kwargs.get("url", "")
        assert called_url.endswith("/api/apps/register"), f"URL appelée: {called_url}"
        assert "regenerate-secret" not in called_url
        # Credentials mis à jour
        assert hub._credentials.client_id == "sa_test123"
        assert hub._credentials.client_secret == "secret_test456"

    @pytest.mark.asyncio
    async def test_recover_failure_returns_false(self, tmp_path, monkeypatch):
        hub = HubClient()
        hub._credentials = None

        mock_http = MagicMock()
        err_response = MagicMock()
        err_response.status_code = 500
        err_response.text = "boom"
        mock_http.post = AsyncMock(return_value=err_response)
        hub._get_client = AsyncMock(return_value=mock_http)

        ok = await hub._recover_credentials()
        assert ok is False
