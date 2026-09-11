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
    """Prépare un fichier de credentials → register() prend le chemin « cache »."""
    monkeypatch.setattr(
        hub_client_module, "CREDENTIALS_FILE", str(tmp_path / ".hub_credentials")
    )
    with open(hub_client_module.CREDENTIALS_FILE, "w") as f:
        f.write(f"{client_id}\n{secret}")


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
# AN-4 : backup list triée + métadonnées cohérentes
# ============================================================

def _backup_zip_bytes(backup_id: str, created_at: str, created_by: str = "admin",
                      with_file: bool = False) -> bytes:
    """ZIP de backup au format 3.0 (cf. create_backup)."""
    backup_data = {
        "metadata": {
            "backup_id": backup_id,
            "app_slug": "test-app",
            "app_version": "1.0.0",
            "created_at": created_at,
            "created_by": created_by,
            "format_version": "3.0",
            "tables": ["items"],
            "table_stats": {"items": 1},
        },
        "data": {"items": [{"id": 1, "title": "x", "owner": "u", "is_public": True}]},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(backup_data))
        if with_file:
            zf.writestr("files/_system/general/note.txt", "contenu")
    return buf.getvalue()


@pytest.fixture
def backups_on_disk():
    """Deux backups, ordre disque ANTI-chronologique (le plus ancien en premier)."""
    old_zip = _backup_zip_bytes("aaaaaaaa", "2026-09-09T18:39:00+00:00")
    new_zip = _backup_zip_bytes("bbbbbbbb", "2026-09-11T00:50:00+00:00", with_file=True)
    files = [
        {
            "filename": "backup_aaaaaaaa.zip",
            "relative_path": "_system/backups/backup_aaaaaaaa.zip",
            "size": len(old_zip),
            "mime_type": "application/zip",
            "modified_at": "2026-09-09T18:39:10",
        },
        {
            "filename": "backup_bbbbbbbb.zip",
            "relative_path": "_system/backups/backup_bbbbbbbb.zip",
            "size": len(new_zip),
            "mime_type": "application/zip",
            "modified_at": "2026-09-11T00:50:10",
        },
    ]
    contents = {
        "_system/backups/backup_bbbbbbbb.zip": new_zip,
        "_system/backups/backup_aaaaaaaa.zip": old_zip,
    }

    async def _read(path, *args, **kwargs):
        return contents[path]

    return files, AsyncMock(side_effect=_read)


class TestBackupListSortedAndCoherent:
    async def test_list_sorted_desc_with_metadata(self, admin_client, backups_on_disk):
        files, read_mock = backups_on_disk
        with patch.object(backup_module.storage_manager, "list_files", AsyncMock(return_value=files)), \
             patch.object(backup_module.storage_manager, "read_file", read_mock):
            response = await admin_client.get("/api/admin/backup/list")

        assert response.status_code == 200, response.text
        backups = response.json()
        assert [b["backup_id"] for b in backups] == ["bbbbbbbb", "aaaaaaaa"], (
            "liste triée created_at desc (AN-4)"
        )
        newest = backups[0]
        assert newest["created_at"] == "2026-09-11T00:50:00+00:00", (
            "created_at relu du data.json (métadonnée create), pas du mtime"
        )
        assert newest["created_by"] == "admin", "created_by relu du data.json (AN-4)"
        assert newest["includes_files"] is True, "includes_files relu du ZIP (AN-4)"
        assert newest["checksum"], "checksum calculé du contenu (AN-4)"
        assert newest["total_items"] == 1, "table_stats relues du data.json"


# ============================================================
# AN-7 : restore — erreurs nested surfacées
# ============================================================

def _restore_zip(data: dict) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "data.json",
            json.dumps({
                "metadata": {
                    "backup_id": "restore-err-test",
                    "app_slug": "test-app",
                    "app_version": "1.0.0",
                    "created_at": "2026-09-11T00:00:00+00:00",
                    "created_by": "admin",
                    "format_version": "3.0",
                },
                "data": data,
            }),
        )
    buf.seek(0)
    return buf


class TestRestoreSurfacesNestedErrors:
    async def test_nested_row_errors_surface_in_top_level_errors(self, admin_client):
        """Une ligne rejetée (ex. FK invalide) dans une table → le top-level
        `errors` mentionne la table (plus de `errors: []` silencié, AN-7)."""
        payload = _restore_zip({
            "items": [
                {"id": 1, "title": "ok", "owner": "u", "is_public": True},
                # Ligne sans title (NOT NULL attendu côté modèle) → rejetée
                {"id": 2, "title": None, "owner": "u", "is_public": True},
            ],
        })

        response = await admin_client.post(
            "/api/admin/restore",
            files={"file": ("backup.zip", payload, "application/zip")},
            data={"clear_existing": "false"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        errors = " ".join(body.get("errors", []))
        assert "items" in errors, (
            f"AN-7 : les erreurs nested doivent être surfacées dans errors[] ; "
            f"reçu errors={body.get('errors')}"
        )
