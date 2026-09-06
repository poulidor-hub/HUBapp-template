"""Tests de l'ordre topologique et de l'isolation par SAVEPOINT du restore générique.

Bug réel (exemple-app, 06/09/2026) : le backup liste ses tables par ordre
alphabétique ; `groupements` référençait `groupement_voicemails` via une FK
non-deferrable → ForeignKeyViolationError sur la première table, transaction
empoisonnée pour toutes les suivantes, « 12 tables, 0 importés » renvoyé en 200.
"""
import io
import json
import zipfile

import pytest

from routes.backup import _topological_table_order


class TestTopologicalTableOrder:
    """Tri topologique des tables selon les dépendances FK."""

    def test_respects_fk_dependencies(self):
        deps = {
            "groupements": {"groupement_voicemails"},
            "groupement_voicemails": set(),
            "phone_users": set(),
        }
        order = _topological_table_order(list(deps), deps)
        assert order.index("groupement_voicemails") < order.index("groupements")
        assert set(order) == set(deps.keys())

    def test_chain_ordering(self):
        deps = {"c": {"b"}, "b": {"a"}, "a": set()}
        order = _topological_table_order(["c", "b", "a"], deps)
        assert order == ["a", "b", "c"]

    def test_self_reference_ignored(self):
        """Une auto-référence (parent_id) ne doit pas bloquer le tri."""
        deps = {"t": {"t"}}
        assert _topological_table_order(["t"], deps) == ["t"]

    def test_cycle_fallback_keeps_all_tables(self):
        """Cycle non résoluble : les tables restent toutes dans l'ordre final
        (les savepoints isoleront les échecs éventuels)."""
        deps = {"a": {"b"}, "b": {"a"}, "c": set()}
        order = _topological_table_order(["a", "b", "c"], deps)
        assert sorted(order) == ["a", "b", "c"]
        assert order[0] == "c"  # sans dépendance → d'abord


class TestRestoreSavepointIsolation:
    """Une table en échec ne doit plus empêcher l'import des autres."""

    @pytest.fixture
    def mixed_backup_zip(self):
        """Backup : `items` avec une ligne violant NOT NULL (title absent) +
        `user_preferences` valide. Sur l'ancien code, l'échec de `items`
        empoisonnait la transaction → user_preferences n'était pas importé."""
        backup_data = {
            "metadata": {
                "backup_id": "test-savepoint",
                "app_slug": "mon-app",
                "app_version": "1.0.0",
                "created_at": "2026-09-06T10:00:00",
                "created_by": "admin",
            },
            "data": {
                # Ordre alphabétique : items (cassé) AVANT user_preferences
                "items": [
                    {
                        "id": 100,
                        # title absent → NOT NULL violation à l'INSERT
                        "description": "Ligne cassée volontairement",
                        "owner": "restoreuser",
                        "is_public": True,
                        "created_at": "2026-09-06T10:00:00",
                        "updated_at": "2026-09-06T10:00:00",
                    }
                ],
                "user_preferences": [
                    {
                        "id": 200,
                        "username": "restoreuser",
                        "theme": "dark",
                        "language": "fr",
                        "items_per_page": 50,
                        "email_notifications": True,
                        "created_at": "2026-09-06T10:00:00",
                        "updated_at": "2026-09-06T10:00:00",
                    }
                ],
                "uploaded_files": [],
            },
        }
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.json", json.dumps(backup_data, indent=2))
        zip_buffer.seek(0)
        return zip_buffer

    @pytest.mark.asyncio
    async def test_broken_table_does_not_block_others(self, admin_client, mixed_backup_zip):
        response = await admin_client.post(
            "/api/admin/restore",
            files={"file": ("backup.zip", mixed_backup_zip.read(), "application/zip")},
            data={"clear_existing": "false"},
        )
        assert response.status_code == 200
        data = response.json()

        # La table cassée est signalée, mais PAS fatale
        assert data["tables_restored"]["items"].get("errors", 0) >= 1

        # 🎯 LA table saine est importée malgré l'échec de l'autre
        assert data["tables_restored"]["user_preferences"]["imported"] == 1
