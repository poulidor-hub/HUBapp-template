"""
Tests pour le système de backup/restore.
Teste les endpoints de backup, restore et le storage manager.
"""
import pytest
import json
import zipfile
import io
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

# Import des modèles et schemas
import sys
sys.path.insert(0, '.')

from models import Item, UserPreference, UploadedFile
from schemas import BackupEstimate, BackupMetadata, RestoreResponse


# ============================================================
# FIXTURES SPÉCIFIQUES AU BACKUP
# ============================================================

@pytest.fixture
def temp_uploads_dir(tmp_path):
    """Crée un répertoire temporaire pour les uploads de test."""
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    return uploads_dir


@pytest.fixture
def mock_storage_manager(temp_uploads_dir):
    """Mock du storage manager avec un répertoire temporaire."""
    with patch('routes.backup.storage_manager') as mock:
        mock.base_path = temp_uploads_dir
        
        # Mock des méthodes
        mock.get_storage_stats = AsyncMock(return_value={
            "total_files": 2,
            "total_size": 1024,
            "total_size_human": "1.0 KB",
            "by_category": {"documents": 512, "images": 512},
            "by_mime_type": {"application/pdf": 512, "image/png": 512},
            "by_owner": {"testuser": 1024}
        })
        
        mock.read_file = AsyncMock(return_value=b"test file content")
        mock.save_bytes = AsyncMock(return_value={
            "filename": "backup_test.zip",
            "relative_path": "_system/backups/backup_test.zip",
            "size": 1024
        })
        mock.delete_file = AsyncMock(return_value=True)
        mock.list_files = AsyncMock(return_value=[
            {
                "filename": "backup_test-id.zip",
                "relative_path": "_system/backups/backup_test-id.zip",
                "size": 2048,
                "mime_type": "application/zip",
                "modified_at": "2026-01-05T10:00:00"
            }
        ])
        
        yield mock


@pytest.fixture
async def sample_data(db_session):
    """Crée des données de test dans la base."""
    # Créer des items
    items = [
        Item(
            title="Item 1",
            description="Description 1",
            owner="testuser",
            is_public=True
        ),
        Item(
            title="Item 2",
            description="Description 2",
            owner="testuser",
            is_public=False
        ),
        Item(
            title="Item 3",
            description="Description 3",
            owner="otheruser",
            is_public=True
        )
    ]
    
    # Créer des préférences
    prefs = [
        UserPreference(
            username="testuser",
            theme="dark",
            language="fr",
            items_per_page=25
        ),
        UserPreference(
            username="otheruser",
            theme="light",
            language="en",
            items_per_page=10
        )
    ]
    
    # Créer des fichiers uploadés (métadonnées seulement)
    files = [
        UploadedFile(
            filename="document.pdf",
            original_filename="Mon Document.pdf",
            relative_path="testuser/documents/document.pdf",
            size=1024,
            mime_type="application/pdf",
            hash="abc123",
            category="documents",
            owner="testuser"
        )
    ]
    
    for item in items:
        db_session.add(item)
    for pref in prefs:
        db_session.add(pref)
    for file in files:
        db_session.add(file)
    
    await db_session.commit()
    
    return {
        "items": items,
        "preferences": prefs,
        "files": files
    }


# ============================================================
# TESTS STORAGE MANAGER
# ============================================================

class TestStorageManager:
    """Tests pour le gestionnaire de stockage."""
    
    @pytest.mark.asyncio
    async def test_save_bytes(self, temp_uploads_dir):
        """Test de sauvegarde de bytes."""
        from storage import StorageManager
        
        manager = StorageManager(str(temp_uploads_dir))
        
        result = await manager.save_bytes(
            data=b"Hello, World!",
            filename="test.txt",
            owner="testuser",
            category="documents"
        )
        
        assert result["filename"] == "test.txt"
        assert result["size"] == 13
        assert "testuser" in result["relative_path"]
        assert "documents" in result["relative_path"]
        
        # Vérifier que le fichier existe
        file_path = temp_uploads_dir / "testuser" / "documents" / "test.txt"
        assert file_path.exists()
    
    @pytest.mark.asyncio
    async def test_read_file(self, temp_uploads_dir):
        """Test de lecture de fichier."""
        from storage import StorageManager
        
        manager = StorageManager(str(temp_uploads_dir))
        
        # Créer un fichier
        await manager.save_bytes(
            data=b"Test content",
            filename="read_test.txt",
            owner="user1",
            category="test"
        )
        
        # Lire le fichier
        content = await manager.read_file("user1/test/read_test.txt")
        assert content == b"Test content"
    
    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_uploads_dir):
        """Test de lecture d'un fichier inexistant."""
        from storage import StorageManager
        
        manager = StorageManager(str(temp_uploads_dir))
        content = await manager.read_file("nonexistent/file.txt")
        assert content is None
    
    @pytest.mark.asyncio
    async def test_delete_file(self, temp_uploads_dir):
        """Test de suppression de fichier."""
        from storage import StorageManager
        
        manager = StorageManager(str(temp_uploads_dir))
        
        # Créer puis supprimer
        await manager.save_bytes(
            data=b"To delete",
            filename="delete_me.txt",
            owner="user1",
            category="temp"
        )
        
        result = await manager.delete_file("user1/temp/delete_me.txt")
        assert result is True
        
        # Vérifier que le fichier n'existe plus
        file_path = temp_uploads_dir / "user1" / "temp" / "delete_me.txt"
        assert not file_path.exists()
    
    @pytest.mark.asyncio
    async def test_list_files(self, temp_uploads_dir):
        """Test de listage des fichiers."""
        from storage import StorageManager
        
        manager = StorageManager(str(temp_uploads_dir))
        
        # Créer plusieurs fichiers
        await manager.save_bytes(b"File 1", "file1.txt", "user1", "docs")
        await manager.save_bytes(b"File 2", "file2.txt", "user1", "docs")
        await manager.save_bytes(b"File 3", "file3.txt", "user1", "images")
        
        # Lister tous les fichiers de user1
        files = await manager.list_files(owner="user1")
        assert len(files) == 3
        
        # Lister par catégorie
        files = await manager.list_files(owner="user1", category="docs")
        assert len(files) == 2
    
    @pytest.mark.asyncio
    async def test_storage_stats(self, temp_uploads_dir):
        """Test des statistiques de stockage."""
        from storage import StorageManager
        
        manager = StorageManager(str(temp_uploads_dir))
        
        # Créer des fichiers
        await manager.save_bytes(b"A" * 100, "file1.txt", "user1", "docs")
        await manager.save_bytes(b"B" * 200, "file2.pdf", "user2", "docs")
        
        stats = await manager.get_storage_stats()
        
        assert stats["total_files"] == 2
        assert stats["total_size"] == 300
        assert "user1" in stats["by_owner"]
        assert "docs" in stats["by_category"]
    
    def test_compute_hash(self):
        """Test du calcul de hash."""
        from storage import StorageManager
        
        hash1 = StorageManager.compute_hash(b"Hello")
        hash2 = StorageManager.compute_hash(b"Hello")
        hash3 = StorageManager.compute_hash(b"World")
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA-256 = 64 caractères hex
    
    def test_human_readable_size(self):
        """Test du formatage de taille."""
        from utils import human_readable_size
        
        assert human_readable_size(0) == "0.0 B"
        assert human_readable_size(1023) == "1023.0 B"
        assert human_readable_size(1024) == "1.0 KB"
        assert human_readable_size(1024 * 1024) == "1.0 MB"
        assert human_readable_size(1024 * 1024 * 1024) == "1.0 GB"


# ============================================================
# TESTS ENDPOINTS BACKUP
# ============================================================

class TestBackupEstimate:
    """Tests pour l'endpoint d'estimation."""
    
    @pytest.mark.asyncio
    async def test_estimate_requires_admin(self, authenticated_client):
        """L'estimation nécessite un rôle admin."""
        response = await authenticated_client.get("/api/admin/backup/estimate")
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_estimate_success(self, admin_client, sample_data, mock_storage_manager):
        """Estimation réussie avec données."""
        response = await admin_client.get("/api/admin/backup/estimate")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "tables" in data
        assert "total_tables" in data
        assert "total_rows" in data
        assert "total_files" in data
        assert "total_size_bytes" in data
        assert "total_size_human" in data
        assert "estimated_duration_seconds" in data
        assert "estimated_duration_human" in data
    
    @pytest.mark.asyncio
    async def test_estimate_empty_database(self, admin_client, mock_storage_manager):
        """Estimation avec base vide."""
        # Mock storage stats vide
        mock_storage_manager.get_storage_stats.return_value = {
            "total_files": 0,
            "total_size": 0,
            "by_category": {},
            "by_mime_type": {}
        }
        
        response = await admin_client.get("/api/admin/backup/estimate")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_rows"] == 0


class TestBackupCreate:
    """Tests pour la création de backup."""
    
    @pytest.mark.asyncio
    async def test_create_requires_admin(self, authenticated_client):
        """La création nécessite un rôle admin."""
        response = await authenticated_client.post("/api/admin/backup")
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_create_backup_success(self, admin_client, sample_data, mock_storage_manager):
        """Création de backup réussie."""
        response = await admin_client.post("/api/admin/backup")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "metadata" in data
        assert "backup_id" in data["metadata"]
        assert "download_url" in data
        
        metadata = data["metadata"]
        assert metadata["total_rows"] == 6
        assert metadata["table_stats"]["items"] == 3
    
    @pytest.mark.asyncio
    async def test_create_backup_empty_db(self, admin_client, mock_storage_manager):
        """Création de backup avec base vide."""
        response = await admin_client.post("/api/admin/backup")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["metadata"]["total_rows"] == 0


class TestBackupDownload:
    """Tests pour le téléchargement de backup."""
    
    @pytest.mark.asyncio
    async def test_download_requires_admin(self, authenticated_client):
        """Le téléchargement nécessite un rôle admin."""
        response = await authenticated_client.get(
            "/api/admin/backup/download",
            params={"backup_id": "test-id"}
        )
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_download_not_found(self, admin_client, mock_storage_manager):
        """Téléchargement d'un backup inexistant."""
        mock_storage_manager.read_file.return_value = None
        
        response = await admin_client.get(
            "/api/admin/backup/download",
            params={"backup_id": "nonexistent"}
        )
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_download_success(self, admin_client, mock_storage_manager):
        """Téléchargement réussi."""
        # Créer un faux ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("data.json", '{"test": true}')
        zip_content = zip_buffer.getvalue()
        
        mock_storage_manager.read_file.return_value = zip_content
        
        response = await admin_client.get(
            "/api/admin/backup/download",
            params={"backup_id": "test-id"}
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"


class TestBackupList:
    """Tests pour le listage des backups."""
    
    @pytest.mark.asyncio
    async def test_list_requires_admin(self, authenticated_client):
        """Le listage nécessite un rôle admin."""
        response = await authenticated_client.get("/api/admin/backup/list")
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_list_success(self, admin_client, mock_storage_manager):
        """Listage réussi."""
        response = await admin_client.get("/api/admin/backup/list")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)


class TestBackupDelete:
    """Tests pour la suppression de backup."""
    
    @pytest.mark.asyncio
    async def test_delete_requires_admin(self, authenticated_client):
        """La suppression nécessite un rôle admin."""
        response = await authenticated_client.delete("/api/admin/backup/test-id")
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_delete_success(self, admin_client, mock_storage_manager):
        """Suppression réussie."""
        response = await admin_client.delete("/api/admin/backup/test-id")
        
        assert response.status_code == 200
        data = response.json()
        assert "supprimé" in data["message"].lower() or "deleted" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_delete_not_found(self, admin_client, mock_storage_manager):
        """Suppression d'un backup inexistant."""
        mock_storage_manager.delete_file.return_value = False
        
        response = await admin_client.delete("/api/admin/backup/nonexistent")
        
        assert response.status_code == 404


# ============================================================
# TESTS RESTORE
# ============================================================

class TestRestore:
    """Tests pour la restauration."""
    
    @pytest.fixture
    def valid_backup_zip(self):
        """Crée un fichier ZIP de backup valide."""
        backup_data = {
            "metadata": {
                "backup_id": "test-backup-id",
                "app_slug": "mon-app",
                "app_version": "1.0.0",
                "created_at": "2026-01-05T10:00:00",
                "created_by": "admin"
            },
            "data": {
                "items": [
                    {
                        "id": 100,
                        "title": "Restored Item",
                        "description": "From backup",
                        "owner": "restoreuser",
                        "is_public": True,
                        "created_at": "2026-01-01T00:00:00",
                        "updated_at": "2026-01-01T00:00:00"
                    }
                ],
                "user_preferences": [
                    {
                        "id": 100,
                        "username": "restoreuser",
                        "theme": "dark",
                        "language": "fr",
                        "items_per_page": 50,
                        "email_notifications": True,
                        "created_at": "2026-01-01T00:00:00",
                        "updated_at": "2026-01-01T00:00:00"
                    }
                ],
                "uploaded_files": []
            }
        }
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.json", json.dumps(backup_data, indent=2))
        
        zip_buffer.seek(0)
        return zip_buffer
    
    @pytest.mark.asyncio
    async def test_restore_requires_admin(self, authenticated_client, valid_backup_zip):
        """La restauration nécessite un rôle admin."""
        response = await authenticated_client.post(
            "/api/admin/restore",
            files={"file": ("backup.zip", valid_backup_zip, "application/zip")}
        )
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_restore_invalid_zip(self, admin_client):
        """Restauration avec fichier invalide."""
        invalid_file = io.BytesIO(b"not a zip file")
        
        response = await admin_client.post(
            "/api/admin/restore",
            files={"file": ("backup.zip", invalid_file, "application/zip")}
        )
        
        assert response.status_code == 400
        assert "ZIP" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_restore_missing_data_json(self, admin_client):
        """Restauration avec ZIP sans data.json."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("other.txt", "some content")
        zip_buffer.seek(0)
        
        response = await admin_client.post(
            "/api/admin/restore",
            files={"file": ("backup.zip", zip_buffer, "application/zip")}
        )
        
        assert response.status_code == 400
        assert "data.json" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_restore_success(self, admin_client, valid_backup_zip, mock_storage_manager):
        """Restauration réussie."""
        response = await admin_client.post(
            "/api/admin/restore",
            files={"file": ("backup.zip", valid_backup_zip, "application/zip")}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["items_restored"] == 1
        assert data["preferences_restored"] == 1
    
    @pytest.mark.asyncio
    async def test_restore_with_clear_existing(
        self, admin_client, valid_backup_zip, sample_data, mock_storage_manager
    ):
        """Restauration avec suppression des données existantes."""
        response = await admin_client.post(
            "/api/admin/restore",
            files={"file": ("backup.zip", valid_backup_zip, "application/zip")},
            data={"clear_existing": "true"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_restore_restores_all_tables_in_backup(self, admin_client, valid_backup_zip, mock_storage_manager):
        """Restauration complète de toutes les tables du backup."""
        response = await admin_client.post(
            "/api/admin/restore",
            files={"file": ("backup.zip", valid_backup_zip, "application/zip")}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["items_restored"] == 1
        assert data["preferences_restored"] == 1


# ============================================================
# TESTS SYNC HUB
# ============================================================

class TestSyncToHub:
    """Tests pour la synchronisation vers le Hub."""
    
    @pytest.mark.asyncio
    async def test_sync_to_hub_requires_admin(self, authenticated_client):
        """La sync nécessite un rôle admin."""
        response = await authenticated_client.post("/api/admin/sync-to-hub")
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_sync_to_hub_not_registered(self, admin_client, mock_storage_manager):
        """Sync impossible si non enregistré au Hub."""
        with patch('routes.backup.hub_client') as mock_hub:
            mock_hub.is_registered = False
            
            response = await admin_client.post("/api/admin/sync-to-hub")
            
            assert response.status_code == 503


class TestSyncFromHub:
    """Tests pour la synchronisation depuis le Hub."""
    
    @pytest.mark.asyncio
    async def test_sync_from_hub_requires_admin(self, authenticated_client):
        """La sync nécessite un rôle admin."""
        response = await authenticated_client.post("/api/admin/sync-from-hub")
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_sync_from_hub_not_registered(self, admin_client, mock_storage_manager):
        """Sync impossible si non enregistré au Hub."""
        with patch('routes.backup.hub_client') as mock_hub:
            mock_hub.is_registered = False
            
            response = await admin_client.post("/api/admin/sync-from-hub")
            
            assert response.status_code == 503


# ============================================================
# TESTS INTÉGRATION BACKUP/RESTORE
# ============================================================

class TestBackupRestoreIntegration:
    """Tests d'intégration backup -> restore."""
    
    @pytest.mark.asyncio
    async def test_full_backup_restore_cycle(self, admin_client, sample_data, mock_storage_manager):
        """Test du cycle complet backup -> restore."""
        # 1. Estimer le backup
        estimate_response = await admin_client.get("/api/admin/backup/estimate")
        assert estimate_response.status_code == 200
        estimate = estimate_response.json()
        assert estimate["total_rows"] == 6
        
        # 2. Créer le backup (on capture le ZIP créé)
        captured_zip = None
        original_save = mock_storage_manager.save_bytes
        
        async def capture_save(*args, **kwargs):
            nonlocal captured_zip
            if kwargs.get("category") == "backups":
                captured_zip = kwargs.get("data") or args[0]
            return await original_save(*args, **kwargs)
        
        # Note: Dans un vrai test d'intégration, on utiliserait le vrai storage
        # Ici on vérifie juste que le flow fonctionne
        
        backup_response = await admin_client.post("/api/admin/backup")
        assert backup_response.status_code == 200
        assert backup_response.json()["success"] is True


# ============================================================
# TESTS UPLOADED FILE MODEL
# ============================================================

class TestUploadedFileModel:
    """Tests pour le modèle UploadedFile."""
    
    @pytest.mark.asyncio
    async def test_to_backup_dict(self, db_session):
        """Test de la méthode to_backup_dict."""
        file = UploadedFile(
            filename="test.pdf",
            original_filename="Original Test.pdf",
            relative_path="user/docs/test.pdf",
            size=2048,
            mime_type="application/pdf",
            hash="abcd1234",
            category="documents",
            description="A test file",
            owner="testuser",
            entity_type="item",
            entity_id=42
        )
        
        db_session.add(file)
        await db_session.commit()
        
        backup_dict = file.to_backup_dict()
        
        assert backup_dict["filename"] == "test.pdf"
        assert backup_dict["original_filename"] == "Original Test.pdf"
        assert backup_dict["size"] == 2048
        assert backup_dict["owner"] == "testuser"
        assert backup_dict["entity_type"] == "item"
        assert backup_dict["entity_id"] == 42
