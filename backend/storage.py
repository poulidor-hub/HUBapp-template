"""
Gestionnaire de stockage de fichiers pour l'application.
Permet l'upload, le téléchargement et la gestion des fichiers associés aux données.
"""
import os
import aiofiles
import aiofiles.os
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import UploadFile
import logging

from config import get_settings
from utils import human_readable_size

logger = logging.getLogger(__name__)
settings = get_settings()


class StorageManager:
    """
    Gestionnaire de fichiers asynchrone.
    Stocke les fichiers dans un répertoire configurable avec structure organisée.
    """
    
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or settings.UPLOADS_DIR)
        self._ensure_base_path()
    
    def _ensure_base_path(self):
        """Crée le répertoire de base s'il n'existe pas."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Storage initialisé: {self.base_path}")
    
    def _get_file_path(self, owner: str, filename: str, category: str = "general") -> Path:
        """
        Construit le chemin complet du fichier.
        Structure: uploads/{owner}/{category}/{filename}

        Garantie de confinement : le chemin final canonique doit rester dans
        base_path (défense ultime contre les traversées, ex. owner/category
        extraits d'une entrée de ZIP de restore).
        """
        safe_owner = self._sanitize_path(owner)
        safe_category = self._sanitize_path(category)
        safe_filename = self._sanitize_filename(filename)

        if not safe_owner or not safe_category or safe_owner == "." or safe_category == ".":
            raise ValueError(f"Chemin de storage invalide (owner/category vides ou dégénérés): {owner!r}/{category!r}")

        dir_path = (self.base_path / safe_owner / safe_category).resolve()
        if not dir_path.is_relative_to(self.base_path.resolve()):
            raise ValueError(f"Chemin hors du storage refusé: {owner!r}/{category!r}")
        dir_path.mkdir(parents=True, exist_ok=True)

        return dir_path / safe_filename

    def _sanitize_path(self, name: str) -> str:
        """Nettoie un nom de chemin pour éviter les injections.

        Les séquences de points consécutifs sont neutralisées (les segments
        '.'/'..' ne doivent jamais survivre : ils permettraient une traversée
        hors du storage via owner/category).
        """
        filtered = "".join(c for c in name if c.isalnum() or c in "-_.")
        while ".." in filtered:
            filtered = filtered.replace("..", ".")
        return filtered[:100]
    
    def _sanitize_filename(self, filename: str) -> str:
        """Nettoie un nom de fichier."""
        # Garder l'extension
        name, ext = os.path.splitext(filename)
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_.")[:200]
        safe_ext = "".join(c for c in ext if c.isalnum() or c == ".")[:10]
        return f"{safe_name}{safe_ext}"
    
    @staticmethod
    def compute_hash(data: bytes) -> str:
        """Calcule le hash SHA-256 des données."""
        return hashlib.sha256(data).hexdigest()
    
    @staticmethod
    def get_mime_type(filename: str) -> str:
        """Détermine le type MIME d'un fichier."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"
    
    async def save_file(
        self,
        file: UploadFile,
        owner: str,
        category: str = "general",
        custom_filename: Optional[str] = None
    ) -> dict:
        """
        Sauvegarde un fichier uploadé.
        
        Args:
            file: Fichier FastAPI UploadFile
            owner: Propriétaire du fichier (username)
            category: Catégorie/dossier de classement
            custom_filename: Nom personnalisé (optionnel)
        
        Returns:
            dict avec les métadonnées du fichier sauvegardé
        """
        filename = custom_filename or file.filename
        file_path = self._get_file_path(owner, filename, category)
        
        # Lire le contenu
        content = await file.read()
        file_size = len(content)
        file_hash = self.compute_hash(content)
        
        # Sauvegarder
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
        
        # Chemin relatif pour stockage en BDD
        relative_path = str(file_path.relative_to(self.base_path))
        
        logger.info(f"📥 Fichier sauvegardé: {relative_path} ({file_size} bytes)")
        
        return {
            "filename": filename,
            "original_filename": file.filename,
            "relative_path": relative_path,
            "absolute_path": str(file_path),
            "size": file_size,
            "hash": file_hash,
            "mime_type": self.get_mime_type(filename),
            "category": category,
            "owner": owner,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def save_bytes(
        self,
        data: bytes,
        filename: str,
        owner: str,
        category: str = "general"
    ) -> dict:
        """
        Sauvegarde des bytes directement (utile pour restore).
        
        Args:
            data: Données binaires
            filename: Nom du fichier
            owner: Propriétaire
            category: Catégorie
        
        Returns:
            dict avec les métadonnées
        """
        file_path = self._get_file_path(owner, filename, category)
        file_hash = self.compute_hash(data)
        
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data)
        
        relative_path = str(file_path.relative_to(self.base_path))
        
        return {
            "filename": filename,
            "relative_path": relative_path,
            "size": len(data),
            "hash": file_hash,
            "mime_type": self.get_mime_type(filename),
            "category": category,
            "owner": owner
        }
    
    async def read_file(self, relative_path: str) -> Optional[bytes]:
        """
        Lit un fichier depuis son chemin relatif.

        Args:
            relative_path: Chemin relatif depuis UPLOADS_DIR

        Returns:
            Contenu binaire ou None si non trouvé
        """
        file_path = self.resolve_path(relative_path)
        if file_path is None:
            return None

        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    def resolve_path(self, relative_path: str) -> Optional[Path]:
        """
        Résout un chemin relatif en chemin absolu, sans lire le fichier.

        Mêmes vérifications de sécurité que read_file (anti-traversée).
        Permet le streaming fichier → destination sans charger en RAM.

        Args:
            relative_path: Chemin relatif depuis UPLOADS_DIR

        Returns:
            Path absolu, ou None si hors du storage / introuvable
        """
        file_path = (self.base_path / relative_path).resolve()

        # Vérifier que le chemin est bien dans base_path (sécurité)
        try:
            file_path.relative_to(self.base_path.resolve())
        except ValueError:
            logger.error(f"🚨 Tentative d'accès hors du storage: {relative_path}")
            return None

        if not file_path.exists():
            logger.warning(f"⚠️ Fichier non trouvé: {relative_path}")
            return None

        return file_path

    async def import_file(
        self,
        src_path: str | Path,
        filename: str,
        owner: str,
        category: str = "general"
    ) -> dict:
        """
        Importe un fichier existant sur disque vers le storage, par chunks.

        Streaming : la RAM n'est jamais proportionnelle à la taille du fichier
        (copie + hash en blocs de 8 Mo). Conçu pour les gros backups.

        Args:
            src_path: Chemin du fichier source sur disque
            filename: Nom de fichier de destination
            owner: Propriétaire
            category: Catégorie/dossier de classement

        Returns:
            dict avec les métadonnées (comme save_bytes)
        """
        src_path = Path(src_path)
        file_path = self._get_file_path(owner, filename, category)

        file_hash = hashlib.sha256()
        size = 0
        async with aiofiles.open(src_path, "rb") as src, \
                aiofiles.open(file_path, "wb") as dst:
            while chunk := await src.read(1024 * 1024):
                await dst.write(chunk)
                file_hash.update(chunk)
                size += len(chunk)

        relative_path = str(file_path.relative_to(self.base_path))

        return {
            "filename": filename,
            "relative_path": relative_path,
            "size": size,
            "hash": file_hash.hexdigest(),
            "mime_type": self.get_mime_type(filename),
            "category": category,
            "owner": owner
        }
    
    async def delete_file(self, relative_path: str) -> bool:
        """
        Supprime un fichier.

        Args:
            relative_path: Chemin relatif depuis UPLOADS_DIR

        Returns:
            True si supprimé, False sinon (dont chemins hors du storage)
        """
        # Confinement obligatoire (même règle que resolve_path) : un chemin
        # relatif ne doit jamais sortir de base_path.
        try:
            file_path = (self.base_path / relative_path).resolve()
            file_path.relative_to(self.base_path.resolve())
        except (ValueError, OSError):
            logger.error(f"🚨 Tentative de suppression hors du storage: {relative_path}")
            return False

        if not file_path.exists():
            return False

        try:
            await aiofiles.os.remove(file_path)
            logger.info(f"🗑️ Fichier supprimé: {relative_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur suppression {relative_path}: {e}")
            return False
    
    async def list_files(self, owner: Optional[str] = None, category: Optional[str] = None) -> list[dict]:
        """
        Liste les fichiers du storage.
        
        Args:
            owner: Filtrer par propriétaire
            category: Filtrer par catégorie
        
        Returns:
            Liste des fichiers avec métadonnées basiques
        """
        files = []
        
        if owner:
            search_path = self.base_path / self._sanitize_path(owner)
            if category:
                search_path = search_path / self._sanitize_path(category)
        else:
            search_path = self.base_path
        
        if not search_path.exists():
            return files
        
        for file_path in search_path.rglob("*"):
            if file_path.is_file():
                relative_path = str(file_path.relative_to(self.base_path))
                stat = file_path.stat()
                files.append({
                    "relative_path": relative_path,
                    "filename": file_path.name,
                    "size": stat.st_size,
                    "mime_type": self.get_mime_type(file_path.name),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        return files
    
    async def get_storage_stats(self) -> dict:
        """
        Calcule les statistiques du storage.
        Utile pour estimer la taille d'un backup.
        
        Returns:
            dict avec total_files, total_size, by_category, etc.
        """
        total_files = 0
        total_size = 0
        by_owner = {}
        by_category = {}
        by_mime_type = {}
        
        if not self.base_path.exists():
            return {
                "total_files": 0,
                "total_size": 0,
                "total_size_human": "0 B",
                "by_owner": {},
                "by_category": {},
                "by_mime_type": {}
            }
        
        for file_path in self.base_path.rglob("*"):
            if file_path.is_file():
                total_files += 1
                size = file_path.stat().st_size
                total_size += size
                
                # Extraire owner et category du chemin
                relative = file_path.relative_to(self.base_path)
                parts = relative.parts
                
                if len(parts) >= 1:
                    owner = parts[0]
                    by_owner[owner] = by_owner.get(owner, 0) + size
                
                if len(parts) >= 2:
                    category = parts[1]
                    by_category[category] = by_category.get(category, 0) + size
                
                mime = self.get_mime_type(file_path.name)
                by_mime_type[mime] = by_mime_type.get(mime, 0) + size
        
        return {
            "total_files": total_files,
            "total_size": total_size,
            "total_size_human": human_readable_size(total_size),
            "by_owner": by_owner,
            "by_category": by_category,
            "by_mime_type": by_mime_type
        }


# Instance globale
storage_manager = StorageManager()
