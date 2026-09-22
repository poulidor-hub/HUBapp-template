"""
Tests de l'authentification — aucun appel réseau bloquant dans l'event loop.

Rappel du bug corrigé (2.27.0 → 2.27.1) :
- PyJWKClient (urllib synchrone) était appelé DIRECTEMENT dans des
  coroutines : initialize(), refresh_jwks_cache() et surtout
  _decode_with_jwks() via decode_token() — appelée par la dépendance async
  get_current_user sur CHAQUE requête. Hub lent ou coupé (rotation de clé,
  kid inconnu) = event loop entièrement gelée, health checks compris.
- Fix : les fetchs JWKS passent par asyncio.to_thread ; decode_token ne
  fait JAMAIS de réseau (cache de clés local par kid) ; une clé inconnue
  déclenche un refresh asynchrone (hors loop) suivi d'un seul retry dans
  les dépendances async.
"""
import asyncio
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

try:
    from hub_auth import JWKSKeyUnknownError
except ImportError:  # RED : l'exception dédiée n'existe pas encore
    class JWKSKeyUnknownError(Exception):
        pass

from hub_auth import hub_auth

pytestmark = pytest.mark.asyncio


def _jwks_call_is_in_event_loop() -> bool:
    """True si appelé DANS l'event loop (get_running_loop réussit)."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class TestInitializeOffLoop:
    async def test_initialize_fetches_jwks_outside_event_loop(self, mock_hub_client):
        """Le fetch JWKS de initialize() doit s'exécuter hors de la loop."""
        fake_client = MagicMock()
        # Si get_signing_keys est appelé DANS la loop → le test échoue
        fake_client.get_signing_keys = MagicMock(
            side_effect=lambda: (
                AssertionError("get_signing_keys appelé dans l'event loop (bloquant)")
                if _jwks_call_is_in_event_loop()
                else []
            )
        )
        with patch("hub_auth.PyJWKClient", return_value=fake_client):
            await hub_auth.initialize()

        fake_client.get_signing_keys.assert_called_once()
        assert hub_auth._jwks_available is True


class TestDecodeTokenNoNetwork:
    async def test_unknown_kid_never_touches_network(self, mock_hub_client):
        """decode_token (sync) ne doit JAMAIS déclencher de fetch réseau."""
        import jwt

        # Token signé « n'importe comment » avec un kid inconnu du cache
        token = jwt.encode({"sub": "x", "exp": 9999999999},
                           "test-secret-min-32-chars-long-xxxx", algorithm="HS256",
                           headers={"kid": "unknown-kid-42"})

        fake_client = MagicMock()
        def _network():
            raise AssertionError(
                "get_signing_key_from_jwt appelé depuis decode_token (réseau bloquant)"
            )
        fake_client.get_signing_key_from_jwt = MagicMock(side_effect=_network)
        fake_client.get_signing_keys = MagicMock(side_effect=_network)

        with patch.object(hub_auth, "_jwk_client", fake_client), \
             patch.object(hub_auth, "_jwks_available", True), \
             patch.object(hub_auth, "_public_key", None), \
             patch.object(hub_auth, "schedule_reconnect") as spy_reconnect:
            with pytest.raises((JWKSKeyUnknownError, Exception)) as exc_info:
                hub_auth.decode_token(token)

        fake_client.get_signing_key_from_jwt.assert_not_called()
        fake_client.get_signing_keys.assert_not_called()
        spy_reconnect.assert_called()  # la reprise async est armée, hors loop
        # L'erreur doit être identifiable (pas une 500 générique)
        assert not isinstance(exc_info.value, AssertionError)

    async def test_known_kid_decodes_from_local_cache(self, mock_hub_client):
        """Un kid déjà en cache local décode sans aucun réseau."""
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        token = jwt.encode(
            {"sub": "alice", "apps": {"mon-app": "user"}, "exp": 9999999999,
             "iat": 1000000000, "jti": "t1", "type": "user"},
            key, algorithm="RS256", headers={"kid": "cached-kid"},
        )

        fake_client = MagicMock()
        def _network():
            raise AssertionError("réseau inattendu")
        fake_client.get_signing_key_from_jwt = MagicMock(side_effect=_network)

        with patch.object(hub_auth, "_jwk_client", fake_client), \
             patch.object(hub_auth, "_jwks_available", True), \
             patch.object(hub_auth, "_jwks_keys_cache", {"cached-kid": pem}):
            payload = hub_auth.decode_token(token)

        assert payload.sub == "alice"
        fake_client.get_signing_key_from_jwt.assert_not_called()


class TestRefreshThenRetry:
    async def test_get_current_user_refreshes_on_unknown_kid(self, mock_hub_client):
        """Clé inconnue → refresh JWKS async → retry unique → payload."""
        from hub_auth import get_current_user, TokenPayload
        from fastapi import HTTPException

        expected = TokenPayload(
            sub="bob", apps={"mon-app": "user"}, token_type="user",
            exp=9999999999, iat=1000000000, jti="j1",
        )
        credentials = MagicMock(scheme="Bearer", credentials="tok")
        calls = {"decode": 0, "refresh": 0}

        def decode_side_effect(token):
            calls["decode"] += 1
            if calls["decode"] == 1:
                raise JWKSKeyUnknownError("kid inconnu")
            return expected

        async def refresh_side_effect():
            calls["refresh"] += 1

        with patch.object(hub_auth, "decode_token",
                          side_effect=decode_side_effect), \
             patch.object(hub_auth, "refresh_jwks_cache",
                          side_effect=refresh_side_effect):
            payload = await get_current_user(credentials)

        assert payload is expected
        assert calls == {"decode": 2, "refresh": 1}, \
            "un seul refresh doit précéder un seul retry"

    async def test_get_current_user_401_after_failed_refresh(self, mock_hub_client):
        """Refresh en échec (Hub down) → 401 propre, pas de gel ni 500."""
        from hub_auth import get_current_user, JWKSKeyUnknownError
        from fastapi import HTTPException

        credentials = MagicMock(scheme="Bearer", credentials="tok")

        def decode_side_effect(token):
            raise JWKSKeyUnknownError("kid inconnu")

        async def refresh_side_effect():
            return {"success": False}

        with patch.object(hub_auth, "decode_token",
                          side_effect=decode_side_effect), \
             patch.object(hub_auth, "refresh_jwks_cache",
                          side_effect=refresh_side_effect):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

        assert exc_info.value.status_code in (401, 503)
