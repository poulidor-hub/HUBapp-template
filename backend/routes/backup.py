"""
Routes pour le système de backup/restore de l'application.
Permet de créer des snapshots complets et de les restaurer.

Endpoints:
- GET  /api/admin/backup/estimate   : Estimer taille et durée du backup
- POST /api/admin/backup            : Créer un backup complet
- GET  /api/admin/backup/download   : Télécharger le backup au format ZIP
- POST /api/admin/restore           : Restaurer depuis un fichier uploadé
- POST /api/admin/sync-to-hub       : Pousser le backup vers le Hub
- POST /api/admin/sync-from-hub     : Récupérer et restaurer depuis le Hub
"""
import json
import base64
import zipfile
import io
import uuid
import hashlib
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
import logging

from config import get_settings, APP_VERSION
from database import get_db
from hub_auth import require_role, TokenPayload
from hub_client import hub_client
from models import Item, UserPreference, UploadedFile, TestData
from schemas import (
    BackupEstimate, BackupMetadata, BackupResponse,
    RestoreRequest, RestoreResponse,
    SyncToHubRequest, SyncFromHubRequest,
    MessageResponse
)
from storage import storage_manager

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/admin", tags=["Backup/Restore"])

# Constantes pour l'estimation
BYTES_PER_ITEM_AVG = 500  # Taille moyenne d'un item en JSON
BYTES_PER_PREF_AVG = 300  # Taille moyenne d'une préférence en JSON
BYTES_PER_TESTDATA_AVG = 400  # Taille moyenne d'une donnée de test en JSON
BYTES_PER_SECOND_ESTIMATE = 10 * 1024 * 1024  # 10 MB/s estimation


def _human_readable_size(size: int) -> str:
    """Convertit une taille en bytes en format lisible."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _human_readable_duration(seconds: float) -> str:
    """Convertit des secondes en format lisible."""
    if seconds < 60:
        return f"{seconds:.0f} sec"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes} min {secs} sec"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes} min"


def _compute_checksum(data: bytes) -> str:
    """Calcule le checksum SHA-256 des données."""
    return hashlib.sha256(data).hexdigest()


# ============================================================
# ESTIMATION DU BACKUP
# ============================================================

@router.get("/backup/estimate", response_model=BackupEstimate)
async def estimate_backup(
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Estime la taille et la durée d'un backup complet.
    
    Retourne:
    - Nombre d'enregistrements par type
    - Taille estimée en bytes et format lisible
    - Durée estimée
    - Répartition des fichiers par catégorie et type MIME
    - Avertissement si le backup est volumineux
    """
    # Compter les enregistrements
    items_count = await db.scalar(select(func.count(Item.id)))
    prefs_count = await db.scalar(select(func.count(UserPreference.id)))
    files_count = await db.scalar(select(func.count(UploadedFile.id)))
    test_data_count = await db.scalar(select(func.count(TestData.id)))
    
    # Calculer taille DB estimée
    db_size = (
        (items_count or 0) * BYTES_PER_ITEM_AVG + 
        (prefs_count or 0) * BYTES_PER_PREF_AVG +
        (test_data_count or 0) * BYTES_PER_TESTDATA_AVG
    )
    
    # Taille réelle des fichiers
    files_result = await db.execute(select(func.sum(UploadedFile.size)))
    files_size = files_result.scalar() or 0
    
    # Stats du storage
    storage_stats = await storage_manager.get_storage_stats()
    
    # Taille totale (avec overhead JSON + ZIP ~10%)
    total_size = int((db_size + files_size) * 1.1)
    
    # Durée estimée
    duration = total_size / BYTES_PER_SECOND_ESTIMATE
    
    # Warning si volumineux
    warning = None
    if total_size > 100 * 1024 * 1024:  # > 100 MB
        warning = "Backup volumineux détecté. L'opération peut prendre plusieurs minutes."
    if total_size > 1024 * 1024 * 1024:  # > 1 GB
        warning = "⚠️ Backup très volumineux (> 1 GB). Considérez un backup incrémental."
    
    return BackupEstimate(
        total_items=items_count or 0,
        total_preferences=prefs_count or 0,
        total_files=files_count or 0,
        total_test_data=test_data_count or 0,
        database_size_bytes=db_size,
        files_size_bytes=files_size,
        total_size_bytes=total_size,
        total_size_human=_human_readable_size(total_size),
        estimated_duration_seconds=duration,
        estimated_duration_human=_human_readable_duration(duration),
        files_by_category=storage_stats.get("by_category", {}),
        files_by_mime_type=storage_stats.get("by_mime_type", {}),
        warning=warning
    )


# ============================================================
# CRÉATION DU BACKUP
# ============================================================

@router.post("/backup", response_model=BackupResponse)
async def create_backup(
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Crée un backup complet de l'application.
    
    Le backup inclut:
    - Tous les items (avec leurs métadonnées)
    - Toutes les préférences utilisateur
    - Tous les fichiers uploadés (encodés en base64 dans le ZIP)
    - Métadonnées du backup (version, date, checksums)
    
    Le backup est stocké temporairement et peut être téléchargé via /backup/download.
    """
    backup_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()
    
    logger.info(f"📦 Création du backup {backup_id} par {user.sub}")
    
    try:
        # 1. Récupérer tous les items
        items_result = await db.execute(select(Item))
        items = items_result.scalars().all()
        items_data = [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "owner": item.owner,
                "is_public": item.is_public,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None
            }
            for item in items
        ]
        
        # 2. Récupérer toutes les préférences
        prefs_result = await db.execute(select(UserPreference))
        prefs = prefs_result.scalars().all()
        prefs_data = [
            {
                "id": pref.id,
                "username": pref.username,
                "theme": pref.theme,
                "language": pref.language,
                "items_per_page": pref.items_per_page,
                "email_notifications": pref.email_notifications,
                "created_at": pref.created_at.isoformat() if pref.created_at else None,
                "updated_at": pref.updated_at.isoformat() if pref.updated_at else None
            }
            for pref in prefs
        ]
        
        # 3. Récupérer tous les fichiers uploadés (métadonnées)
        files_result = await db.execute(select(UploadedFile))
        uploaded_files = files_result.scalars().all()
        files_data = [f.to_backup_dict() for f in uploaded_files]
        
        # 4. Récupérer toutes les données de test
        test_data_result = await db.execute(select(TestData))
        test_data_entries = test_data_result.scalars().all()
        test_data_list = [td.to_backup_dict() for td in test_data_entries]
        
        # 5. Construire le JSON principal
        backup_data = {
            "metadata": {
                "backup_id": backup_id,
                "app_slug": settings.APP_SLUG,
                "app_version": APP_VERSION,
                "created_at": created_at,
                "created_by": user.sub,
                "format_version": "1.1"  # Version mise à jour pour test_data
            },
            "data": {
                "items": items_data,
                "user_preferences": prefs_data,
                "uploaded_files": files_data,
                "test_data": test_data_list
            }
        }
        
        # 5. Créer le fichier ZIP en mémoire
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Ajouter le JSON principal
            data_json = json.dumps(backup_data, indent=2, ensure_ascii=False)
            zf.writestr("data.json", data_json)
            
            # Ajouter les fichiers binaires
            files_added = 0
            for file_meta in uploaded_files:
                try:
                    content = await storage_manager.read_file(file_meta.relative_path)
                    if content:
                        zf.writestr(f"files/{file_meta.relative_path}", content)
                        files_added += 1
                except Exception as e:
                    logger.warning(f"⚠️ Impossible de lire {file_meta.relative_path}: {e}")
        
        zip_buffer.seek(0)
        zip_data = zip_buffer.getvalue()
        total_size = len(zip_data)
        checksum = _compute_checksum(zip_data)
        
        # 6. Stocker le backup temporairement (dans le storage)
        backup_filename = f"backup_{backup_id}.zip"
        await storage_manager.save_bytes(
            data=zip_data,
            filename=backup_filename,
            owner="_system",
            category="backups"
        )
        
        logger.info(f"✅ Backup {backup_id} créé: {len(items_data)} items, {len(prefs_data)} prefs, {len(test_data_list)} test_data, {files_added} fichiers ({_human_readable_size(total_size)})")
        
        metadata = BackupMetadata(
            backup_id=backup_id,
            app_slug=settings.APP_SLUG,
            app_version=APP_VERSION,
            created_at=created_at,
            created_by=user.sub,
            total_items=len(items_data),
            total_preferences=len(prefs_data),
            total_files=files_added,
            total_test_data=len(test_data_list),
            total_size_bytes=total_size,
            total_size_human=_human_readable_size(total_size),
            includes_files=True,
            checksum=checksum
        )
        
        return BackupResponse(
            success=True,
            message=f"Backup créé avec succès",
            metadata=metadata,
            download_url=f"/api/admin/backup/download?backup_id={backup_id}"
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur création backup: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création du backup: {str(e)}")


# ============================================================
# TÉLÉCHARGEMENT DU BACKUP
# ============================================================

@router.get("/backup/download")
async def download_backup(
    backup_id: str,
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Télécharge un backup au format ZIP.
    
    Le ZIP contient:
    - data.json : Toutes les données structurées
    - files/ : Dossier avec tous les fichiers uploadés
    """
    backup_filename = f"backup_{backup_id}.zip"
    backup_path = f"_system/backups/{backup_filename}"
    
    content = await storage_manager.read_file(backup_path)
    if not content:
        raise HTTPException(status_code=404, detail="Backup non trouvé")
    
    logger.info(f"📥 Téléchargement backup {backup_id} par {user.sub}")
    
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{settings.APP_SLUG}_backup_{backup_id}.zip"',
            "Content-Length": str(len(content))
        }
    )


# ============================================================
# RESTAURATION DEPUIS UN FICHIER
# ============================================================

@router.post("/restore", response_model=RestoreResponse)
async def restore_backup(
    file: UploadFile = File(...),
    clear_existing: str = Form("false"),
    restore_items: str = Form("true"),
    restore_preferences: str = Form("true"),
    restore_files: str = Form("true"),
    restore_test_data: str = Form("true"),
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Restaure l'application depuis un fichier de backup uploadé.
    
    Paramètres:
    - file: Fichier ZIP de backup
    - clear_existing: Supprimer toutes les données existantes avant restauration
    - restore_items: Restaurer les items
    - restore_preferences: Restaurer les préférences utilisateur
    - restore_files: Restaurer les fichiers uploadés
    
    ⚠️ ATTENTION: clear_existing=true supprime TOUTES les données existantes!
    """
    # Convertir les strings en booléens
    clear_existing_bool = clear_existing.lower() in ("true", "1", "yes", "on")
    restore_items_bool = restore_items.lower() in ("true", "1", "yes", "on")
    restore_preferences_bool = restore_preferences.lower() in ("true", "1", "yes", "on")
    restore_files_bool = restore_files.lower() in ("true", "1", "yes", "on")
    restore_test_data_bool = restore_test_data.lower() in ("true", "1", "yes", "on")
    
    errors = []
    warnings = []
    items_restored = 0
    prefs_restored = 0
    files_restored = 0
    test_data_restored = 0
    items_skipped = 0
    files_skipped = 0
    test_data_skipped = 0
    
    logger.info(f"🔄 Restauration démarrée par {user.sub} (clear_existing={clear_existing_bool})")
    
    try:
        # 1. Lire le fichier ZIP
        content = await file.read()
        zip_buffer = io.BytesIO(content)
        
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            # 2. Lire le JSON principal
            if "data.json" not in zf.namelist():
                raise HTTPException(status_code=400, detail="Fichier de backup invalide: data.json manquant")
            
            data_json = zf.read("data.json").decode("utf-8")
            backup_data = json.loads(data_json)
            
            metadata = backup_data.get("metadata", {})
            data = backup_data.get("data", {})
            
            logger.info(f"📂 Backup {metadata.get('backup_id', 'inconnu')} - App: {metadata.get('app_slug')}, Version: {metadata.get('app_version')}")
            
            # 3. Vérifier la compatibilité
            if metadata.get("app_slug") != settings.APP_SLUG:
                warnings.append(f"Le backup provient d'une application différente ({metadata.get('app_slug')})")
            
            # 4. Clear existing si demandé
            if clear_existing_bool:
                logger.warning("🗑️ Suppression des données existantes...")
                if restore_items_bool:
                    await db.execute(delete(Item))
                if restore_preferences_bool:
                    await db.execute(delete(UserPreference))
                if restore_files_bool:
                    await db.execute(delete(UploadedFile))
                if restore_test_data_bool:
                    await db.execute(delete(TestData))
                await db.commit()
            
            # 5. Restaurer les items
            if restore_items_bool:
                for item_data in data.get("items", []):
                    try:
                        # Vérifier si existe déjà
                        existing = await db.execute(
                            select(Item).where(Item.id == item_data.get("id"))
                        )
                        if existing.scalar() and not clear_existing_bool:
                            items_skipped += 1
                            continue
                        
                        item = Item(
                            title=item_data["title"],
                            description=item_data.get("description"),
                            owner=item_data["owner"],
                            is_public=item_data.get("is_public", False),
                            created_at=datetime.fromisoformat(item_data["created_at"]) if item_data.get("created_at") else None,
                            updated_at=datetime.fromisoformat(item_data["updated_at"]) if item_data.get("updated_at") else None
                        )
                        db.add(item)
                        items_restored += 1
                    except Exception as e:
                        errors.append(f"Item {item_data.get('id')}: {str(e)}")
            
            # 6. Restaurer les préférences
            if restore_preferences_bool:
                for pref_data in data.get("user_preferences", []):
                    try:
                        existing = await db.execute(
                            select(UserPreference).where(UserPreference.username == pref_data.get("username"))
                        )
                        if existing.scalar() and not clear_existing_bool:
                            continue
                        
                        pref = UserPreference(
                            username=pref_data["username"],
                            theme=pref_data.get("theme", "system"),
                            language=pref_data.get("language", "fr"),
                            items_per_page=pref_data.get("items_per_page", 20),
                            email_notifications=pref_data.get("email_notifications", True),
                            created_at=datetime.fromisoformat(pref_data["created_at"]) if pref_data.get("created_at") else None,
                            updated_at=datetime.fromisoformat(pref_data["updated_at"]) if pref_data.get("updated_at") else None
                        )
                        db.add(pref)
                        prefs_restored += 1
                    except Exception as e:
                        errors.append(f"Preference {pref_data.get('username')}: {str(e)}")
            
            # 7. Restaurer les fichiers
            if restore_files_bool:
                for file_data in data.get("uploaded_files", []):
                    try:
                        relative_path = file_data.get("relative_path")
                        zip_path = f"files/{relative_path}"
                        
                        # Vérifier si le fichier existe dans le ZIP
                        if zip_path not in zf.namelist():
                            warnings.append(f"Fichier manquant dans le backup: {relative_path}")
                            files_skipped += 1
                            continue
                        
                        # Lire et sauvegarder le fichier
                        file_content = zf.read(zip_path)
                        
                        # Reconstruire le chemin
                        parts = relative_path.split("/")
                        if len(parts) >= 2:
                            owner = parts[0]
                            category = parts[1]
                            filename = "/".join(parts[2:]) if len(parts) > 2 else parts[-1]
                        else:
                            owner = file_data.get("owner", "_restored")
                            category = file_data.get("category", "general")
                            filename = file_data.get("filename", relative_path)
                        
                        await storage_manager.save_bytes(
                            data=file_content,
                            filename=filename,
                            owner=owner,
                            category=category
                        )
                        
                        # Enregistrer en BDD
                        uploaded_file = UploadedFile(
                            filename=file_data["filename"],
                            original_filename=file_data.get("original_filename", file_data["filename"]),
                            relative_path=relative_path,
                            size=file_data["size"],
                            mime_type=file_data["mime_type"],
                            hash=file_data["hash"],
                            category=file_data.get("category", "general"),
                            description=file_data.get("description"),
                            owner=file_data["owner"],
                            entity_type=file_data.get("entity_type"),
                            entity_id=file_data.get("entity_id")
                        )
                        db.add(uploaded_file)
                        files_restored += 1
                        
                    except Exception as e:
                        errors.append(f"Fichier {file_data.get('filename')}: {str(e)}")
            
            # 8. Restaurer les données de test
            if restore_test_data_bool:
                for td_data in data.get("test_data", []):
                    try:
                        # Vérifier si existe déjà
                        existing = await db.execute(
                            select(TestData).where(TestData.id == td_data.get("id"))
                        )
                        if existing.scalar() and not clear_existing_bool:
                            test_data_skipped += 1
                            continue
                        
                        test_data_entry = TestData(
                            name=td_data["name"],
                            value=td_data.get("value"),
                            category=td_data.get("category", "general"),
                            last_modified_by=td_data.get("last_modified_by", user.sub),
                            created_at=datetime.fromisoformat(td_data["created_at"]) if td_data.get("created_at") else None,
                            updated_at=datetime.fromisoformat(td_data["updated_at"]) if td_data.get("updated_at") else None
                        )
                        db.add(test_data_entry)
                        test_data_restored += 1
                    except Exception as e:
                        errors.append(f"TestData {td_data.get('id')}: {str(e)}")
            
            await db.commit()
        
        logger.info(f"✅ Restauration terminée: {items_restored} items, {prefs_restored} prefs, {test_data_restored} test_data, {files_restored} fichiers")
        
        return RestoreResponse(
            success=len(errors) == 0,
            message="Restauration terminée" + (" avec des erreurs" if errors else " avec succès"),
            items_restored=items_restored,
            preferences_restored=prefs_restored,
            files_restored=files_restored,
            items_skipped=items_skipped,
            files_skipped=files_skipped,
            errors=errors,
            warnings=warnings
        )
        
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Le fichier uploadé n'est pas un ZIP valide")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Le fichier data.json est corrompu")
    except HTTPException:
        # Re-raise HTTPException sans les transformer
        raise
    except Exception as e:
        logger.error(f"❌ Erreur restauration: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la restauration: {str(e)}")


# ============================================================
# SYNCHRONISATION AVEC LE HUB
# ============================================================

@router.post("/sync-to-hub", response_model=MessageResponse)
async def sync_to_hub(
    request: SyncToHubRequest = None,
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Pousse le backup complet vers le Hub central.
    
    Le Hub se charge de:
    - Stocker le backup
    - Gérer les versions
    - Permettre la restauration depuis n'importe quelle instance
    
    ⚠️ Nécessite que l'application soit enregistrée auprès du Hub avec IS_SHARED=true
    """
    if not hub_client.is_registered:
        raise HTTPException(
            status_code=503,
            detail="Application non enregistrée auprès du Hub. Vérifiez la connexion."
        )
    
    logger.info(f"☁️ Synchronisation vers le Hub initiée par {user.sub}")
    
    try:
        # 1. Créer un backup
        backup_response = await create_backup(db=db, user=user)
        if not backup_response.success:
            raise HTTPException(status_code=500, detail="Échec de la création du backup")
        
        backup_id = backup_response.metadata.backup_id
        
        # 2. Lire le fichier backup
        backup_path = f"_system/backups/backup_{backup_id}.zip"
        backup_content = await storage_manager.read_file(backup_path)
        
        if not backup_content:
            raise HTTPException(status_code=500, detail="Backup créé mais fichier introuvable")
        
        # 3. Encoder en base64 pour envoi
        backup_b64 = base64.b64encode(backup_content).decode("utf-8")
        
        # 4. Envoyer au Hub via M2M
        # Le Hub doit exposer un endpoint /api/apps/{slug}/backup
        result = await hub_client.call_hub_endpoint(
            endpoint=f"/api/apps/{settings.APP_SLUG}/backup",
            method="POST",
            data={
                "backup_id": backup_id,
                "backup_data": backup_b64,
                "metadata": backup_response.metadata.model_dump(),
                "description": request.description if request else None,
                "tags": request.tags if request else []
            }
        )
        
        if result and result.get("success"):
            logger.info(f"✅ Backup {backup_id} synchronisé avec le Hub")
            return MessageResponse(
                message="Backup synchronisé avec le Hub",
                detail=f"Backup ID: {backup_id}, Taille: {backup_response.metadata.total_size_human}"
            )
        else:
            error_msg = result.get("error", "Erreur inconnue") if result else "Pas de réponse du Hub"
            raise HTTPException(status_code=502, detail=f"Erreur Hub: {error_msg}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur sync vers Hub: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur de synchronisation: {str(e)}")


@router.post("/sync-from-hub", response_model=RestoreResponse)
async def sync_from_hub(
    request: SyncFromHubRequest = None,
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Récupère et restaure le dernier backup depuis le Hub central.
    
    Paramètres:
    - backup_id: ID spécifique du backup (optionnel, sinon le plus récent)
    - clear_existing: Supprimer les données existantes avant restauration
    
    ⚠️ Cette opération écrase les données locales avec celles du Hub!
    """
    if not hub_client.is_registered:
        raise HTTPException(
            status_code=503,
            detail="Application non enregistrée auprès du Hub. Vérifiez la connexion."
        )
    
    backup_id = request.backup_id if request else None
    clear_existing = request.clear_existing if request else False
    
    logger.info(f"☁️ Récupération du backup depuis le Hub par {user.sub} (backup_id={backup_id})")
    
    try:
        # 1. Récupérer le backup depuis le Hub
        endpoint = f"/api/apps/{settings.APP_SLUG}/backup"
        if backup_id:
            endpoint += f"/{backup_id}"
        else:
            endpoint += "/latest"
        
        result = await hub_client.call_hub_endpoint(
            endpoint=endpoint,
            method="GET"
        )
        
        if not result or not result.get("success"):
            error_msg = result.get("error", "Backup non trouvé") if result else "Pas de réponse du Hub"
            raise HTTPException(status_code=404, detail=f"Erreur Hub: {error_msg}")
        
        # 2. Décoder le backup
        backup_b64 = result.get("backup_data")
        if not backup_b64:
            raise HTTPException(status_code=502, detail="Données de backup manquantes dans la réponse du Hub")
        
        backup_content = base64.b64decode(backup_b64)
        
        # 3. Créer un fichier temporaire pour la restauration
        temp_file = UploadFile(
            filename="hub_backup.zip",
            file=io.BytesIO(backup_content)
        )
        
        # 4. Utiliser la fonction de restauration existante
        restore_result = await restore_backup(
            file=temp_file,
            clear_existing=clear_existing,
            restore_items=True,
            restore_preferences=True,
            restore_files=True,
            db=db,
            user=user
        )
        
        logger.info(f"✅ Restauration depuis le Hub terminée")
        return restore_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur sync depuis Hub: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur de récupération: {str(e)}")


# ============================================================
# ENDPOINTS UTILITAIRES
# ============================================================

@router.get("/backup/list", response_model=list[BackupMetadata])
async def list_local_backups(
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Liste les backups stockés localement.
    
    Note: Les backups sont normalement envoyés au Hub et supprimés localement.
    Cette liste montre les backups en attente ou conservés temporairement.
    """
    backups = []
    files = await storage_manager.list_files(owner="_system", category="backups")
    
    for file in files:
        if file["filename"].startswith("backup_") and file["filename"].endswith(".zip"):
            backup_id = file["filename"].replace("backup_", "").replace(".zip", "")
            backups.append(BackupMetadata(
                backup_id=backup_id,
                app_slug=settings.APP_SLUG,
                app_version=APP_VERSION,
                created_at=file.get("modified_at", ""),
                created_by="unknown",
                total_items=0,
                total_preferences=0,
                total_files=0,
                total_size_bytes=file["size"],
                total_size_human=_human_readable_size(file["size"]),
                includes_files=True,
                checksum=""
            ))
    
    return backups


@router.delete("/backup/{backup_id}", response_model=MessageResponse)
async def delete_local_backup(
    backup_id: str,
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Supprime un backup local.
    """
    backup_path = f"_system/backups/backup_{backup_id}.zip"
    deleted = await storage_manager.delete_file(backup_path)
    
    if deleted:
        logger.info(f"🗑️ Backup {backup_id} supprimé par {user.sub}")
        return MessageResponse(message="Backup supprimé", detail=f"ID: {backup_id}")
    else:
        raise HTTPException(status_code=404, detail="Backup non trouvé")
