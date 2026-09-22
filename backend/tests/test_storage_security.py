"""
Tests de sécurité du StorageManager — confinement des chemins.

Rappel des bugs corrigés (2.26.4 → 2.27.0) :
- _sanitize_path conservait les points → un owner/category ".." issu d'un
  ZIP de restore traversait hors d'UPLOADS_DIR (écriture avec mkdir).
- delete_file ne vérifiait AUCUN confinement (contrairement à resolve_path)
  → DELETE /api/admin/backup/../../x supprimait hors du storage.
"""
import pytest

from storage import StorageManager


@pytest.fixture
def storage(tmp_path):
    """StorageManager branché sur un répertoire temporaire, avec un fichier
    légitime et un fichier « hors storage » dans le dossier parent."""
    base = tmp_path / "uploads"
    base.mkdir()
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("ne doit pas être supprimé")

    sm = StorageManager(base_path=str(base))

    # Fichier légitime
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        sm.save_bytes(b"legit", "file.txt", owner="alice", category="docs")
    )
    return sm, base, outside


class TestSanitizePath:
    """Neutralisation des traversées dans _sanitize_path."""

    def test_dotdot_is_neutralized(self, storage):
        sm, _, _ = storage
        assert sm._sanitize_path("..") != ".."

    def test_embedded_dotdot_is_neutralized(self, storage):
        sm, _, _ = storage
        result = sm._sanitize_path("al..ice")
        assert ".." not in result

    def test_normal_names_unchanged(self, storage):
        sm, _, _ = storage
        assert sm._sanitize_path("alice") == "alice"
        assert sm._sanitize_path("v1.2-beta") == "v1.2-beta"


class TestSaveConfinement:
    """Écriture : impossible de sortir du storage via owner/category."""

    async def test_save_bytes_dotdot_owner_rejected(self, storage):
        sm, base, outside = storage
        with pytest.raises(ValueError):
            await sm.save_bytes(b"evil", "evil.txt", owner="..", category="general")
        # Rien n'a été écrit hors du storage
        assert not (base.parent / "evil.txt").exists()

    async def test_save_bytes_dotdot_category_rejected(self, storage):
        sm, base, outside = storage
        with pytest.raises(ValueError):
            await sm.save_bytes(b"evil", "evil.txt", owner="alice", category="..")
        assert not (base.parent / "evil.txt").exists()

    async def test_save_bytes_dotdot_filename_via_zip_rejected(self, storage):
        """Cas restore ZIP : owner extrait d'une entrée 'files/../../x'."""
        sm, base, outside = storage
        with pytest.raises(ValueError):
            await sm.save_bytes(b"evil", "evil.txt", owner="../..", category="general")
        assert not (base.parent / "evil.txt").exists()


class TestDeleteConfinement:
    """Suppression : delete_file respecte le confinement comme resolve_path."""

    async def test_delete_outside_storage_refused(self, storage):
        sm, base, outside = storage
        result = await sm.delete_file("../outside_secret.txt")
        assert result is False
        assert outside.exists(), "le fichier hors storage a été supprimé !"

    async def test_delete_deep_traversal_refused(self, storage):
        sm, base, outside = storage
        result = await sm.delete_file("alice/docs/../../../../../outside_secret.txt")
        assert result is False
        assert outside.exists()

    async def test_delete_legit_file_still_works(self, storage):
        sm, base, outside = storage
        result = await sm.delete_file("alice/docs/file.txt")
        assert result is True
        assert not (base / "alice" / "docs" / "file.txt").exists()
        assert outside.exists()

    async def test_delete_missing_file_returns_false(self, storage):
        sm, base, outside = storage
        assert await sm.delete_file("nobody/nowhere.txt") is False
