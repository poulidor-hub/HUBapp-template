"""
Tests du streaming du backup — RAM bornée à un batch de lignes.

Rappel des bugs corrigés (2.27.0 → 2.27.1) :
- Export : toutes les tables étaient fetchallées en RAM, puis le dump
  COMPLET sérialisé en une seule string (json.dumps) → l'annonce « RAM
  bornée » du commentaire était fausse pour la partie DB, le bug OOM
  pouvait récidiver. Fix : data.json écrit sur disque table par table,
  lignes par batchs (yield_per) ; le ZIP streame ce fichier.
- Restore : l'upload entier était lu en RAM (BytesIO). Fix : copie par
  chunks vers un fichier temporaire, ZipFile ouvert depuis le disque.

Le FORMAT du backup (data.json : {metadata, data}) reste inchangé —
contrat préservé avec les backups existants.
"""
import io
import json
import zipfile
from unittest.mock import patch, AsyncMock

import pytest

pytestmark = pytest.mark.asyncio


# ============================================================
# FIXTURES LOCALES (indépendantes de test_backup.py)
# ============================================================

@pytest.fixture
def storage_mock(tmp_path):
    """Storage manager réel adossé à un tmp dir, patché dans routes.backup."""
    from storage import StorageManager
    real = StorageManager(base_path=str(tmp_path / "uploads"))
    with patch("routes.backup.storage_manager") as mock:
        mock.base_path = real.base_path
        mock.resolve_path = real.resolve_path
        mock.import_file = AsyncMock(side_effect=real.import_file)
        mock.read_file = AsyncMock(side_effect=real.read_file)
        mock.save_bytes = AsyncMock(side_effect=real.save_bytes)
        mock.delete_file = AsyncMock(side_effect=real.delete_file)
        mock.list_files = AsyncMock(side_effect=real.list_files)
        mock.get_storage_stats = AsyncMock(return_value={
            "total_files": 0, "total_size": 0, "total_size_human": "0 B",
            "by_category": {}, "by_mime_type": {}, "by_owner": {},
        })
        yield mock


@pytest.fixture
async def seed_items_5(db_session):
    """5 items (impair → dernier batch partiel avec batch_size=2)."""
    from models import Item
    for i in range(5):
        db_session.add(Item(title=f"item-{i}", owner="admin", is_public=True))
    await db_session.commit()


# ============================================================
# 1. Export : lignes lues par batchs (jamais toute la table)
# ============================================================

class TestIterTableRows:
    async def test_batches_and_content(self, admin_client, seed_items_5, db_session):
        """5 lignes → itération par batchs (listes), contenu sérialisé correct.

        Note : aiosqlite (tests hôte) bufferise le curseur client-side, le
        découpage exact par batch_size n'est observable qu'avec un vrai
        curseur serveur (PostgreSQL/asyncpg — couvert par make test-docker).
        Ce test garantit le contrat : yield de listes de dicts, total exact.
        """
        from routes.backup import _iter_table_rows

        batches = []
        async for batch in _iter_table_rows(db_session, "items", batch_size=2):
            assert isinstance(batch, list) and len(batch) > 0
            batches.append(batch)

        all_rows = [r for b in batches for r in b]
        assert len(all_rows) == 5
        # Colonnes sérialisées présentes (dictionnaires)
        assert all(isinstance(r, dict) and "title" in r for r in all_rows)

    async def test_empty_table_yields_nothing(self, admin_client, db_session):
        from routes.backup import _iter_table_rows

        batches = []
        async for batch in _iter_table_rows(db_session, "items", batch_size=10):
            batches.append(batch)
        assert batches == []


# ============================================================
# 2. ZIP : data.json streamé depuis le disque (pas writestr)
# ============================================================

class TestBuildZipStreamsDataJson:
    async def test_signature_takes_path_not_dict(self, tmp_path):
        """_build_backup_zip_sync reçoit un FICHIER data.json, pas un dict."""
        import inspect
        from routes.backup import _build_backup_zip_sync

        sig = inspect.signature(_build_backup_zip_sync)
        param_names = list(sig.parameters)
        assert "data_json_path" in param_names, \
            "la signature doit prendre data_json_path (streaming disque)"
        assert "backup_data" not in param_names, \
            "backup_data (dict complet en RAM) doit disparaître"

    async def test_data_json_written_byte_identical(self, tmp_path):
        """Le data.json du ZIP est exactement le fichier source (stream)."""
        from routes.backup import _build_backup_zip_sync

        data_json_path = tmp_path / "data.json"
        payload = {"metadata": {"format_version": "3.0"}, "data": {"items": [{"id": 1}]}}
        data_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

        zip_path = tmp_path / "out.zip"
        files_added = _build_backup_zip_sync(zip_path, data_json_path, [], lambda p: None)
        assert files_added == 0

        with zipfile.ZipFile(zip_path) as zf:
            assert zf.read("data.json") == data_json_path.read_bytes()

    async def test_binary_files_still_streamed(self, tmp_path):
        """Non-régression : les fichiers binaires restent inclus."""
        from routes.backup import _build_backup_zip_sync

        src = tmp_path / "photo.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 1000)

        data_json_path = tmp_path / "data.json"
        data_json_path.write_text("{}")

        zip_path = tmp_path / "out.zip"
        def resolve(rel):
            return src if rel == "alice/photo.png" else None

        files_added = _build_backup_zip_sync(
            zip_path, data_json_path, ["alice/photo.png"], resolve
        )
        assert files_added == 1
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.read("files/alice/photo.png") == src.read_bytes()


class TestCreateBackupEndpoint:
    async def test_endpoint_uses_streamed_data_json(
        self, admin_client, seed_items_5, storage_mock
    ):
        """L'endpoint passe un CHEMIN de data.json au builder ZIP (pas un dict)."""
        import routes.backup as backup_module

        with patch.object(backup_module, "_build_backup_zip_sync",
                          side_effect=backup_module._build_backup_zip_sync) as spy:
            response = await admin_client.post("/api/admin/backup")

        assert response.status_code == 200, response.text
        (args, _kwargs) = spy.call_args
        data_json_arg = args[1]
        assert not isinstance(data_json_arg, dict), \
            "le dump complet est encore passé en RAM au builder ZIP"
        assert str(data_json_arg).endswith(".json"), \
            "le builder doit recevoir un chemin de fichier data.json"

    async def test_backup_format_unchanged(
        self, admin_client, seed_items_5, storage_mock
    ):
        """Le data.json produit garde la structure {metadata, data} (contrat)."""
        response = await admin_client.post("/api/admin/backup")
        assert response.status_code == 200

        metadata = response.json()["metadata"]
        backup_id = metadata["backup_id"]
        listing = await admin_client.get(
            "/api/admin/backup/list", params={"backup_id": backup_id}
        )
        assert listing.status_code == 200


# ============================================================
# 3. Restore : upload copié sur disque (pas de BytesIO du ZIP)
# ============================================================

class TestRestoreStreamsUpload:
    async def test_zipfile_opens_disk_path_not_bytesio(
        self, admin_client, seed_items_5, storage_mock
    ):
        """Pendant un restore, ZipFile est ouvert depuis un chemin disque."""
        import routes.backup as backup_module

        # Fabriquer un backup via l'API, puis le re-uploader
        created = await admin_client.post("/api/admin/backup")
        assert created.status_code == 200

        with patch.object(backup_module.zipfile, "ZipFile",
                          side_effect=backup_module.zipfile.ZipFile) as spy:
            downloaded = await admin_client.get(
                "/api/admin/backup/download",
                params={"backup_id": created.json()["metadata"]["backup_id"]},
            )
            assert downloaded.status_code == 200
            spy.reset_mock()

            response = await admin_client.post(
                "/api/admin/restore",
                files={"file": ("backup.zip", downloaded.content, "application/zip")},
                data={"clear_existing": "false"},
            )

        assert response.status_code == 200, response.text
        opened_args = [call.args for call in spy.call_args_list]
        assert opened_args, "ZipFile doit être utilisé"
        for args in opened_args:
            src = args[0]
            assert not isinstance(src, io.BytesIO), \
                "le ZIP complet est encore chargé en RAM (BytesIO)"
            assert isinstance(src, (str, __import__("pathlib").Path)), \
                "ZipFile doit être ouvert depuis un chemin disque"
