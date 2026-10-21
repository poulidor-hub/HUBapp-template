"""
Alignement du template sur HUBsocle 2.23.2 (vague de fixes banc 2026-09-10).

Portage des fixes HUBsocle v2.21.1→v2.23.2 applicables au template
(architecture backend monolithique) :

- **AN-3** : register() court-circuité (credentials en cache) doit pousser
  l'état is_shared courant au Hub (`PUT /api/apps/me/shared`) — cf.
  HUBsocle `_sync_state_to_hub`/`_push_shared_state_to_hub`.
- **Deadlock flock** : ré-entrance register (cascade 403 → register) doit
  court-circuiter le lock fichier (flag `_register_in_progress`).
- **AN-4** : `/api/backup/list` trié `created_at` desc + métadonnées relues
  du data.json (created_by/checksum/includes_files cohérents).
- **AN-5** : `/api/health/detailed` reflète la découverte LIVE ; fallback
  sur `app.state.discovered_services_count` si l'appel live échoue.
- **AN-7** : restore — les erreurs nested par table sont agrégées dans le
  top-level `errors` (plus de `errors: []` silencié).
"""
import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import hub_client as hub_client_module
import main as main_module
import routes.backup as backup_module
from hub_client import HubClient, HubCredentials


# ============================================================
# AN-3 + deadlock : register / sync is_shared
# ============================================================

def _write_cached_credentials(monkeypatch, tmp_path, client_id="sa_cached", secret="secret_cached"):
    """Prépare un fichier de credentials avec la version COURANTE
    → register() prend le chemin « cache » (sync simple). Un fichier dont la
    version diffère (ou legacy 2 lignes) déclenche désormais un register complet."""
    monkeypatch.setattr(
        hub_client_module, "CREDENTIALS_FILE", str(tmp_path / ".hub_credentials")
    )
    with open(hub_client_module.CREDENTIALS_FILE, "w") as f:
        f.write(f"{client_id}\n{secret}\n{hub_client_module.APP_VERSION}")


def _mock_http(ok_request: bool = True):
    """HTTP mock : POST /api/auth/token → 200 token ; request() → 200 (ou exception)."""
    http = MagicMock()
    token_resp = MagicMock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "m2m_tok"}
    http.post = AsyncMock(return_value=token_resp)
    if ok_request:
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {}
        ok_resp.text = ""
        http.request = AsyncMock(return_value=ok_resp)
    else:
        http.request = AsyncMock(side_effect=RuntimeError("hub down"))
    return http


class TestRegisterCachedPushesSharedState:
    async def test_register_with_cached_credentials_pushes_is_shared(self, monkeypatch, tmp_path):
        _write_cached_credentials(monkeypatch, tmp_path)
        hub = HubClient()
        http = _mock_http()
        hub._get_client = AsyncMock(return_value=http)

        ok = await hub.register()

        assert ok is True
        shared_calls = [
            c for c in http.request.await_args_list
            if c.args and str(c.args[1]).endswith("/api/apps/me/shared")
        ]
        assert shared_calls, (
            "register() avec credentials en cache doit pousser l'état is_shared "
            "au Hub (PUT /api/apps/me/shared) — sinon IS_SHARED du .env ne propage jamais"
        )
        call = shared_calls[0]
        assert call.args[0] == "PUT"
        assert call.kwargs["params"] == {"is_shared": hub.settings.IS_SHARED}

    async def test_register_cached_survives_hub_ko(self, monkeypatch, tmp_path):
        """Best-effort : un échec de la poussée is_shared ne fait pas échouer le register."""
        _write_cached_credentials(monkeypatch, tmp_path)
        hub = HubClient()
        http = _mock_http(ok_request=False)
        hub._get_client = AsyncMock(return_value=http)

        ok = await hub.register()
        assert ok is True


class TestRegisterReentrance:
    async def test_reentrant_register_skips_lock_and_uses_cache(self, monkeypatch, tmp_path):
        """Cascade 403 → register pendant un register en cours : pas de lock
        (deadlock flock), le chemin cache court-circuite."""
        _write_cached_credentials(monkeypatch, tmp_path)
        hub = HubClient()
        http = _mock_http()
        hub._get_client = AsyncMock(return_value=http)
        hub._register_in_progress = True

        ok = await hub.register()

        assert ok is True
        assert not http.post.await_args_list or all(
            "/register" not in str(c.args[1]) for c in http.post.await_args_list if c.args
        ), "le chemin ré-entrant ne doit pas re-poster /register"

    async def test_register_in_progress_flag_exists(self):
        hub = HubClient()
        assert hasattr(hub, "_register_in_progress")
        assert hub._register_in_progress is False


# ============================================================
# AN-5 : health/detailed discovery LIVE + fallback
# ============================================================

def _svc(slug: str):
    return MagicMock(slug=slug, status="online", is_healthy=True)


@pytest.fixture
def registered_main_hub(monkeypatch):
    """Rend le hub_client singleton du main « enregistré » (is_registered → True),
    entièrement isolé du réseau (token M2M mocké)."""
    hc = main_module.hub_client
    monkeypatch.setattr(
        hc, "_credentials", HubCredentials(client_id="sa_x", client_secret="s")
    )
    monkeypatch.setattr(hc, "get_m2m_token", AsyncMock(return_value="m2m_mock_tok"))
    return hc


@pytest.fixture
def outbox_stats_mock(monkeypatch):
    """health/detailed lit outbox_service.get_stats() sur la DB globale —
    isolé ici (hors périmètre du test)."""
    mock = AsyncMock(return_value={"total": 0, "pending": 0, "delivered": 0, "failed": 0})
    monkeypatch.setattr(main_module.outbox_service, "get_stats", mock)
    return mock


class TestHealthDetailedLiveDiscovery:
    async def test_discovered_count_reflects_live_value(
        self, client, registered_main_hub, monkeypatch, outbox_stats_mock
    ):
        monkeypatch.setattr(main_module.settings, "IS_SHARED", True)
        monkeypatch.setattr(
            registered_main_hub,
            "list_discovered_services",
            AsyncMock(return_value=[_svc("a"), _svc("b"), _svc("c")]),
        )

        response = await client.get("/api/health/detailed")

        assert response.status_code == 200
        body = response.json()
        assert body["services"]["discovered_count"] == 3, (
            "health/detailed doit refléter la découverte LIVE (AN-5)"
        )

    async def test_fallback_to_startup_state_when_live_fails(
        self, client, registered_main_hub, monkeypatch, outbox_stats_mock, app_with_db
    ):
        monkeypatch.setattr(main_module.settings, "IS_SHARED", True)
        monkeypatch.setattr(
            registered_main_hub,
            "list_discovered_services",
            AsyncMock(side_effect=RuntimeError("hub down")),
        )
        app_with_db.state.discovered_services_count = 7

        response = await client.get("/api/health/detailed")

        assert response.status_code == 200
        body = response.json()
        assert body["services"]["discovered_count"] == 7, (
            "fallback sur app.state.discovered_services_count attendu (AN-5)"
        )


# ============================================================
