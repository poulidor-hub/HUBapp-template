"""
Stats/cohérence backup sur les tables de démonstration (AN-4/AN-7).

Dépend des modèles démo `items`/`test_data` — retiré de l'app scaffoldée
par INITIALISE --clean (cf. _clean_demo_tests). Reste dans le TEMPLATE
comme référence copiable.
"""
import io
import json
import zipfile
from unittest.mock import AsyncMock, patch

import pytest

import routes.backup as backup_module


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
