"""
Routes pour le système de backup/restore de l'application.
Permet de créer des snapshots complets et de les restaurer.

SYSTÈME GÉNÉRIQUE : Découvre et sauvegarde automatiquement TOUTES les tables
de la base de données, sans configuration manuelle.

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
import re
import zipfile
import io
import shutil
import uuid
import hashlib
import asyncio
import os
import tempfile
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, List
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, inspect
import logging

from config import get_settings, APP_VERSION
from database import get_db
from hub_auth import require_role, TokenPayload
from hub_client import hub_client
from schemas import (
    BackupMetadata,
    SyncToHubRequest, SyncFromHubRequest,
    MessageResponse
)
from storage import storage_manager

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/admin", tags=["Backup/Restore"])

# Constantes pour l'estimation
BYTES_PER_ROW_AVG = 400  # Taille moyenne d'une ligne en JSON
BYTES_PER_SECOND_ESTIMATE = 10 * 1024 * 1024  # 10 MB/s estimation

# Regex de validation pour les identifiants SQL (tables, colonnes)
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

# Tables système à exclure du backup (internes PostgreSQL/SQLAlchemy)
EXCLUDED_TABLES = {
    "alembic_version",  # Migrations Alembic
    "spatial_ref_sys",  # PostGIS
}


# Fonctions utilitaires importées depuis utils.py
from utils import human_readable_size as _human_readable_size
from utils import human_readable_duration as _human_readable_duration


def _compute_checksum(data: bytes) -> str:
    """Calcule le checksum SHA-256 des données."""
    return hashlib.sha256(data).hexdigest()


def _compute_checksum_file(path: str | Path) -> str:
    """Calcule le checksum SHA-256 d'un fichier, en streaming (RAM bornée)."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_backup_zip_sync(
    zip_path: str | Path,
    data_json_path: str | Path,
    file_relative_paths: List[str],
    resolve_source: Any,
) -> int:
    """
    Écrit le ZIP de backup directement sur disque, en streaming.

    RAM bornée : data.json est copié depuis le disque vers l'archive par
    chunks (1 Mo), les fichiers uploadés sont copiés par le compresseur —
    jamais chargés intégralement en mémoire. Conçu pour être exécuté dans
    un thread (asyncio.to_thread) afin de ne pas bloquer la boucle.

    Args:
        zip_path: Chemin du ZIP à écrire
        data_json_path: Chemin du data.json déjà écrit sur disque (streaming)
        file_relative_paths: Chemins relatifs des fichiers à inclure
        resolve_source: Callable relative_path -> Path|None (storageManager.resolve_path)

    Returns:
        Nombre de fichiers ajoutés au ZIP
    """
    files_added = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # JSON principal : copié depuis le disque par chunks
        with open(data_json_path, "rb") as src, zf.open("data.json", "w") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)

        # Fichiers binaires : streamés depuis le disque vers l'archive
        for relative_path in file_relative_paths:
            source = resolve_source(relative_path)
            if source is None:
                logger.warning(f"⚠️ Impossible de lire {relative_path}")
                continue
            zf.write(str(source), arcname=f"files/{relative_path}")
            files_added += 1
    return files_added


def _serialize_value(value: Any) -> Any:
    """
    Sérialise une valeur pour JSON.
    Gère les types non-JSON natifs (datetime, date, Decimal, bytes, etc.)
    """
    if value is None:
        return None
    elif isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    elif isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    elif isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    elif isinstance(value, bytes):
        return {"__type__": "bytes", "value": base64.b64encode(value).decode('ascii')}
    elif isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    else:
        return value


def _deserialize_value(value: Any) -> Any:
    """
    Désérialise une valeur depuis JSON.
    Reconstruit les types non-JSON natifs.
    """
    if value is None:
        return None
    elif isinstance(value, dict):
        if "__type__" in value:
            type_name = value["__type__"]
            raw_value = value["value"]
            if type_name == "datetime":
                return datetime.fromisoformat(raw_value)
            elif type_name == "date":
                return date.fromisoformat(raw_value)
            elif type_name == "decimal":
                return Decimal(raw_value)
            elif type_name == "bytes":
                try:
                    return base64.b64decode(raw_value)
                except Exception:
                    logger.warning(f"⚠️ Données base64 corrompues, valeur brute conservée")
                    return raw_value
        return {k: _deserialize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_deserialize_value(v) for v in value]
    else:
        return value


async def _get_all_tables(db: AsyncSession) -> List[str]:
    """
    Découvre dynamiquement toutes les tables de la base de données.
    Exclut les tables système.
    """
    def _sync(session):
        inspector = inspect(session.bind)
        tables = inspector.get_table_names()
        return [t for t in tables if t not in EXCLUDED_TABLES and _SAFE_IDENTIFIER_RE.match(t)]

    return await db.run_sync(_sync)


async def _get_table_row_count(db: AsyncSession, table_name: str) -> int:
    """Compte le nombre de lignes dans une table."""
    result = await db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
    return result.scalar() or 0


async def _get_table_columns(db: AsyncSession, table_name: str) -> List[Dict[str, str]]:
    """Récupère les informations sur les colonnes d'une table."""
    def _sync(session):
        inspector = inspect(session.bind)
        columns = inspector.get_columns(table_name)
        return [
            {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "default": col.get("default"),
            }
            for col in columns
        ]

    return await db.run_sync(_sync)


async def _get_primary_key_columns(db: AsyncSession, table_name: str) -> List[str]:
    """Récupère les colonnes de la clé primaire d'une table."""
    def _sync(session):
        inspector = inspect(session.bind)
        pk_constraint = inspector.get_pk_constraint(table_name)
        return pk_constraint.get("constrained_columns", []) or []

    return await db.run_sync(_sync)


async def _export_table_data(db: AsyncSession, table_name: str) -> List[Dict[str, Any]]:
    """
    Exporte toutes les données d'une table sous forme de liste de dictionnaires.
    Sérialise automatiquement les types complexes.

    ⚠️ Charge TOUTE la table en RAM — réserver aux usages ponctuels.
    Le backup principal utilise _iter_table_rows (streaming par batchs).
    """
    data = []
    async for batch in _iter_table_rows(db, table_name, batch_size=1000):
        data.extend(batch)
    return data


EXPORT_BATCH_SIZE = 1000


async def _iter_table_rows(db: AsyncSession, table_name: str, batch_size: int = EXPORT_BATCH_SIZE):
    """
    Itère les lignes d'une table PAR BATCHS (streaming côté driver).

    RAM bornée à `batch_size` lignes : yield_per active le streaming du
    curseur (serveur sur asyncpg, client par lots sur aiosqlite) — jamais
    `fetchall()` de la table entière.

    Yields:
        list[dict] : un batch de lignes sérialisées (_serialize_value)
    """
    columns_info = await _get_table_columns(db, table_name)
    column_names = [c["name"] for c in columns_info]

    # stream() + yield_per : curseur serveur (asyncpg) / lots client
    # (aiosqlite) — la table n'est jamais fetchallée en RAM
    result = await db.stream(
        text(f'SELECT * FROM "{table_name}"'),
        execution_options={"yield_per": batch_size},
    )
    async for partition in result.partitions():
        batch = []
        for row in partition:
            row_dict = {}
            for i, col_name in enumerate(column_names):
                row_dict[col_name] = _serialize_value(row[i])
            batch.append(row_dict)
        yield batch


async def _write_data_json_stream(
    db: AsyncSession,
    path: str | Path,
    tables: List[str],
    metadata: Dict[str, Any],
) -> Dict[str, int]:
    """
    Écrit data.json SUR DISQUE table par table, lignes par batchs.

    Le dump complet n'est JAMAIS matérialisé en RAM (le json.dumps global
    de l'ancienne implémentation doublait la mémoire : dict + string).
    Le format produit reste un JSON standard {metadata, data} — contrat
    inchangé avec les backups existants (consommateurs : json.loads).

    Returns:
        table_stats : {table: nb de lignes}
    """
    # Stats par table : COUNT(*) avant l'export (metadata écrite en premier)
    table_stats: Dict[str, int] = {}
    for t in tables:
        table_stats[t] = await _get_table_row_count(db, t)

    metadata_complete = {**metadata, "table_stats": table_stats}

    with open(path, "w", encoding="utf-8") as f:
        f.write('{\n  "metadata": ')
        f.write(json.dumps(metadata_complete, indent=2, ensure_ascii=False))
        f.write(',\n  "data": {\n')

        first_table = True
        for t in tables:
            prefix = "" if first_table else ",\n"
            first_table = False
            f.write(f'{prefix}    {json.dumps(t)}: [')
            first_row = True
            async for batch in _iter_table_rows(db, t):
                for row in batch:
                    separator = "" if first_row else ","
                    first_row = False
                    f.write(separator + "\n      " + json.dumps(row, ensure_ascii=False))
            f.write("\n    ]")

        f.write("\n  }\n}")

    return table_stats


async def _get_fk_dependencies(db: AsyncSession) -> dict:
    """Dépendances FK entre tables du schéma public : {table: {tables référencées}}.
    Auto-références exclues (isolées par savepoints à l'import)."""
    result = await db.execute(text("""
        SELECT tc.table_name, ccu.table_name AS referenced_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
    """))
    deps: dict = {}
    for table_name, referenced in result.fetchall():
        if referenced != table_name:
            deps.setdefault(table_name, set()).add(referenced)
    return deps


async def _get_fk_dependencies_sqlite(db: AsyncSession) -> dict:
    """Équivalent SQLite (pas d'information_schema) via PRAGMA foreign_key_list."""
    deps: dict = {}
    for t in await _get_all_tables(db):
        rows = await db.execute(text(f'PRAGMA foreign_key_list("{t}")'))
        for row in rows.fetchall():
            referenced = row[2]  # colonne 'table' du résultat PRAGMA
            if referenced and referenced != t:
                deps.setdefault(t, set()).add(referenced)
    return deps


def _topological_table_order(table_names: list, fk_deps: dict) -> list:
    """Ordre d'import respectant les FK (Kahn, tie-break alphabétique).

    Les cycles (non résolubles par l'ordre) sont ajoutés à la fin, isolés
    par les savepoints de la boucle d'import.
    """
    names = set(table_names)
    remaining = {t: {d for d in fk_deps.get(t, set()) if d in names} for t in table_names}
    ordered, done = [], set()
    while remaining:
        ready = sorted(t for t, ds in remaining.items() if ds <= done)
        if not ready:
            ordered.extend(sorted(remaining))
            break
        for t in ready:
            ordered.append(t)
            done.add(t)
            del remaining[t]
    return ordered


async def _import_table_data(
    db: AsyncSession, 
    table_name: str, 
    data: List[Dict[str, Any]],
    clear_existing: bool = False
) -> Dict[str, int]:
    """
    Importe des données dans une table.
    
    Returns:
        Dict avec 'imported', 'updated', 'skipped', 'errors' (+ 'errors_detail')
    """
    stats = {"imported": 0, "updated": 0, "skipped": 0, "errors": 0, "errors_detail": []}
    
    if not data:
        return stats
    
    # Récupérer les colonnes de la clé primaire
    pk_columns = await _get_primary_key_columns(db, table_name)
    
    # Récupérer les colonnes existantes dans la table
    columns_info = await _get_table_columns(db, table_name)
    existing_columns = {c["name"] for c in columns_info}
    
    # Supprimer les données existantes si demandé
    if clear_existing:
        await db.execute(text(f'DELETE FROM "{table_name}"'))
    
    # Savepoint par ligne : une ligne en échec (FK, NOT NULL…) ne
    # pousse plus la transaction dans un état aborté qui ferait
    # échouer toutes les lignes suivantes en cascade.
    for row_idx, row_data in enumerate(data):
        # Désérialiser les valeurs
        deserialized = {k: _deserialize_value(v) for k, v in row_data.items()}

        # Filtrer les colonnes qui existent dans la table
        filtered_data = {k: v for k, v in deserialized.items() if k in existing_columns and _SAFE_IDENTIFIER_RE.match(k)}

        if not filtered_data:
            stats["skipped"] += 1
            continue

        # Construire la requête INSERT avec ON CONFLICT (upsert)
        columns = list(filtered_data.keys())
        placeholders = [f":{col}" for col in columns]

        if pk_columns and not clear_existing:
            # Upsert : INSERT ... ON CONFLICT DO UPDATE
            pk_condition = " AND ".join([f'"{col}" = :{col}' for col in pk_columns])
            update_cols = [c for c in columns if c not in pk_columns]

            if update_cols:
                update_set = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in update_cols])
                query = f"""
                    INSERT INTO "{table_name}" ({", ".join([f'"{c}"' for c in columns])})
                    VALUES ({", ".join(placeholders)})
                    ON CONFLICT ({", ".join([f'"{c}"' for c in pk_columns])})
                    DO UPDATE SET {update_set}
                """
            else:
                # Pas de colonnes à mettre à jour, juste ignorer les conflits
                query = f"""
                    INSERT INTO "{table_name}" ({", ".join([f'"{c}"' for c in columns])})
                    VALUES ({", ".join(placeholders)})
                    ON CONFLICT ({", ".join([f'"{c}"' for c in pk_columns])})
                    DO NOTHING
                """
        else:
            # Simple INSERT
            query = f"""
                INSERT INTO "{table_name}" ({", ".join([f'"{c}"' for c in columns])})
                VALUES ({", ".join(placeholders)})
            """

        row_sp = await db.begin_nested()
        try:
            await db.execute(text(query), filtered_data)
            await row_sp.commit()
            stats["imported"] += 1
        except Exception as e:
            await row_sp.rollback()
            logger.warning(f"⚠️ Erreur import ligne dans {table_name}: {e}")
            row_ref = row_data.get("id", f"#{row_idx}")
            stats["errors_detail"].append(f"ligne {row_ref}: {e}")
            stats["errors"] += 1

    return stats


# ============================================================
# ESTIMATION DU BACKUP
# ============================================================

@router.get("/backup/estimate")
async def estimate_backup(
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Estime la taille et la durée d'un backup complet.
    
    Découvre AUTOMATIQUEMENT toutes les tables de la base de données
    et compte les enregistrements de chaque table.
    
    Retourne:
    - Liste de toutes les tables avec leur nombre d'enregistrements
    - Taille estimée en bytes et format lisible
    - Durée estimée
    - Répartition des fichiers par catégorie et type MIME
    - Avertissement si le backup est volumineux
    """
    # Découvrir toutes les tables
    tables = await _get_all_tables(db)
    
    # Compter les enregistrements par table
    tables_stats = {}
    total_rows = 0
    for table_name in tables:
        count = await _get_table_row_count(db, table_name)
        tables_stats[table_name] = count
        total_rows += count
    
    # Calculer taille DB estimée
    db_size = total_rows * BYTES_PER_ROW_AVG
    
    # Taille réelle des fichiers uploadés (si la table existe)
    files_size = 0
    files_count = 0
    if "uploaded_files" in tables:
        try:
            result = await db.execute(text("SELECT COALESCE(SUM(size), 0), COUNT(*) FROM uploaded_files"))
            row = result.fetchone()
            files_size = row[0] or 0
            files_count = row[1] or 0
        except:
            pass
    
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
    
    return {
        "tables": tables_stats,
        "total_tables": len(tables),
        "total_rows": total_rows,
        "total_files": files_count,
        "database_size_bytes": db_size,
        "files_size_bytes": files_size,
        "total_size_bytes": total_size,
        "total_size_human": _human_readable_size(total_size),
        "estimated_duration_seconds": duration,
        "estimated_duration_human": _human_readable_duration(duration),
        "files_by_category": storage_stats.get("by_category", {}),
        "files_by_mime_type": storage_stats.get("by_mime_type", {}),
        "warning": warning
    }


# ============================================================
# CRÉATION DU BACKUP
# ============================================================

@router.post("/backup")
async def create_backup(
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Crée un backup complet de l'application.
    
    ⚡ SYSTÈME GÉNÉRIQUE ⚡
    
    Découvre AUTOMATIQUEMENT toutes les tables de la base de données
    et exporte toutes les données sans configuration préalable.
    
    Le backup inclut:
    - Toutes les tables de la base de données (découvertes automatiquement)
    - Tous les fichiers uploadés (encodés dans le ZIP)
    - Métadonnées du backup (version, date, checksums)
    
    Le backup est stocké temporairement et peut être téléchargé via /backup/download.
    """
    backup_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
    logger.info(f"📦 Création du backup générique {backup_id} par {user.sub}")
    
    try:
        # 1. Découvrir toutes les tables de la base de données
        tables = await _get_all_tables(db)
        logger.info(f"📊 Tables découvertes: {tables}")

        # 2. data.json écrit sur DISQUE table par table, lignes par batchs
        #    (RAM bornée : ni fetchall des tables, ni dump complet en string)
        backup_filename = f"backup_{backup_id}.zip"
        metadata = {
            "backup_id": backup_id,
            "app_slug": settings.APP_SLUG,
            "app_version": APP_VERSION,
            "created_at": created_at,
            "created_by": user.sub,
            "format_version": "3.0",  # Version 3.0 = format générique
            "tables": list(tables),
        }

        json_fd, tmp_json_path = tempfile.mkstemp(
            prefix=f"backup_{backup_id}_", suffix=".json",
            dir=str(storage_manager.base_path)
        )
        os.close(json_fd)
        tmp_fd, tmp_zip_path = tempfile.mkstemp(
            prefix=f"backup_{backup_id}_", suffix=".zip",
            dir=str(storage_manager.base_path)
        )
        os.close(tmp_fd)

        try:
            table_stats = await _write_data_json_stream(db, tmp_json_path, tables, metadata)

            # 3. Chemins des fichiers uploadés à inclure (liste légère)
            file_relative_paths = []
            if "uploaded_files" in tables:
                result = await db.execute(text("SELECT relative_path FROM uploaded_files"))
                file_relative_paths = [r[0] for r in result.fetchall() if r[0]]

            # 4. Créer le fichier ZIP sur disque (streaming — RAM bornée au
            #    plus gros chunk : data.json copié depuis le disque, binaires
            #    compressés en flux ; incident OOM 512M)
            files_added = await asyncio.to_thread(
                _build_backup_zip_sync,
                tmp_zip_path,
                tmp_json_path,
                file_relative_paths,
                storage_manager.resolve_path,
            )

            total_size = os.path.getsize(tmp_zip_path)
            checksum = _compute_checksum_file(tmp_zip_path)

            # 5. Stocker le backup (copie par chunks — pas de chargement RAM)
            await storage_manager.import_file(
                src_path=tmp_zip_path,
                filename=backup_filename,
                owner="_system",
                category="backups"
            )
        finally:
            for tmp_path in (tmp_zip_path, tmp_json_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    logger.warning(f"⚠️ Fichier temporaire non supprimé: {tmp_path}")
        
        # Log détaillé
        total_rows = sum(table_stats.values())
        non_empty_tables = [t for t, c in table_stats.items() if c > 0]
        logger.info(f"✅ Backup générique {backup_id} créé: {len(tables)} tables, "
                    f"{total_rows} enregistrements total, {files_added} fichiers ({_human_readable_size(total_size)})")
        logger.info(f"   Tables avec données: {non_empty_tables}")
        
        return {
            "success": True,
            "message": f"Backup créé avec succès",
            "metadata": {
                "backup_id": backup_id,
                "app_slug": settings.APP_SLUG,
                "app_version": APP_VERSION,
                "created_at": created_at,
                "created_by": user.sub,
                "format_version": "3.0",
                "total_tables": len(tables),
                "total_rows": total_rows,
                "total_files": files_added,
                "total_size_bytes": total_size,
                "total_size_human": _human_readable_size(total_size),
                "includes_files": files_added > 0,
                "checksum": checksum,
                "table_stats": table_stats
            },
            "download_url": f"/api/admin/backup/download?backup_id={backup_id}"
        }
        
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

    zip_abs_path = storage_manager.resolve_path(backup_path)
    if zip_abs_path is None:
        raise HTTPException(status_code=404, detail="Backup non trouvé")

    logger.info(f"📥 Téléchargement backup {backup_id} par {user.sub}")

    # Streaming depuis le disque : la RAM ne charge jamais le ZIP entier
    return FileResponse(
        path=str(zip_abs_path),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{settings.APP_SLUG}_backup_{backup_id}.zip"',
        }
    )


# ============================================================
# RESTAURATION DEPUIS UN FICHIER
# ============================================================

@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    clear_existing: str = Form("false"),
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Restaure l'application depuis un fichier de backup uploadé.
    
    ⚡ SYSTÈME GÉNÉRIQUE ⚡
    
    Restaure AUTOMATIQUEMENT toutes les tables contenues dans le backup,
    sans nécessiter de configuration préalable.
    
    Paramètres:
    - file: Fichier ZIP de backup
    - clear_existing: Supprimer toutes les données existantes avant restauration
    
    ⚠️ ATTENTION: clear_existing=true supprime TOUTES les données existantes!
    """
    clear_existing_bool = clear_existing.lower() in ("true", "1", "yes", "on")
    
    errors = []
    warnings = []
    tables_restored = {}
    files_restored = 0
    
    logger.info(f"🔄 Restauration générique démarrée par {user.sub} (clear_existing={clear_existing_bool})")
    
    tmp_zip_path = None
    try:
        # 1. Streamer l'upload vers un fichier temporaire (RAM bornée au
        #    chunk — l'ancienne implémentation chargeait tout le ZIP en RAM)
        tmp_fd, tmp_zip_path = tempfile.mkstemp(
            prefix="restore_", suffix=".zip", dir=str(storage_manager.base_path)
        )
        with os.fdopen(tmp_fd, "wb") as f:
            while chunk := await file.read(8 * 1024 * 1024):
                f.write(chunk)

        with zipfile.ZipFile(tmp_zip_path, "r") as zf:
            # 2. Lire le JSON principal
            if "data.json" not in zf.namelist():
                raise HTTPException(status_code=400, detail="Fichier de backup invalide: data.json manquant")
            
            data_json = zf.read("data.json").decode("utf-8")
            backup_data = json.loads(data_json)
            
            metadata = backup_data.get("metadata", {})
            data = backup_data.get("data", {})
            format_version = metadata.get("format_version", "1.0")
            
            logger.info(f"📂 Backup {metadata.get('backup_id', 'inconnu')} - "
                       f"App: {metadata.get('app_slug')}, Version: {metadata.get('app_version')}, "
                       f"Format: {format_version}")
            
            # 3. Vérifier la compatibilité
            if metadata.get("app_slug") != settings.APP_SLUG:
                warnings.append(f"Le backup provient d'une application différente ({metadata.get('app_slug')})")
            
            # 4. Découvrir les tables dans le backup
            backup_tables = list(data.keys())
            logger.info(f"📊 Tables dans le backup: {backup_tables}")
            
            # 5. Découvrir les tables existantes dans la base
            existing_tables = await _get_all_tables(db)
            logger.info(f"📊 Tables existantes dans la base: {existing_tables}")
            
            # 6. Clear existing si demandé
            if clear_existing_bool:
                logger.warning("🗑️ Suppression des données existantes...")
                # Désactiver les contraintes FK temporairement (PostgreSQL uniquement)
                if db.get_bind().dialect.name != "sqlite":
                    await db.execute(text("SET CONSTRAINTS ALL DEFERRED"))
                
                for table_name in existing_tables:
                    if table_name in backup_tables:
                        try:
                            await db.execute(text(f'DELETE FROM "{table_name}"'))
                            logger.debug(f"  🗑️ Table {table_name} vidée")
                        except Exception as e:
                            warnings.append(f"Impossible de vider {table_name}: {str(e)}")
                
                # PAS de commit ici — on garde tout dans la même transaction
                # pour pouvoir rollback si l'import échoue
                await db.flush()
            
            # 7. Restaurer chaque table — ordre topologique (dépendances FK)
            # + SAVEPOINT par table : une table en échec n'empoisonne plus la
            # transaction des autres (bug exemple-app 06/09/2026 : FK violée
            # sur la 1ère table alphabétique → « 12 tables, 0 importés »).
            restore_tables = [t for t in data.keys() if t in existing_tables]
            for t in data.keys():
                if t not in existing_tables:
                    warnings.append(f"Table '{t}' du backup n'existe pas dans la base actuelle")

            if db.get_bind().dialect.name == "sqlite":
                fk_deps = await _get_fk_dependencies_sqlite(db)
            else:
                fk_deps = await _get_fk_dependencies(db)
            ordered_tables = _topological_table_order(restore_tables, fk_deps)
            logger.info(f"📊 Ordre d'import topologique: {ordered_tables}")

            # Cycles de FK non déferrables (ex. groupements ↔ voicemails) :
            # l'ordre seul ne suffit pas → désactiver les triggers FK pendant
            # l'import (rôle superuser requis ; sinon repli sur l'ordre seul).
            replication_disabled = False
            if db.get_bind().dialect.name == "postgresql":
                try:
                    await db.execute(text("SET session_replication_role = replica"))
                    replication_disabled = True
                except Exception as e:
                    logger.warning(f"⚠️ session_replication_role=replica refusé: {e}")

            try:
                for i, table_name in enumerate(ordered_tables):
                    table_data = data[table_name]

                    if not table_data:
                        tables_restored[table_name] = {"imported": 0, "updated": 0, "skipped": 0}
                        continue

                    savepoint = await db.begin_nested()
                    try:
                        result = await _import_table_data(db, table_name, table_data, clear_existing_bool)
                        await savepoint.commit()
                        tables_restored[table_name] = result

                        total = result["imported"] + result["updated"]
                        if total > 0:
                            logger.info(f"  ✓ {table_name}: {result['imported']} importés, "
                                       f"{result['updated']} mis à jour, {result['skipped']} ignorés")

                        # Agréger les erreurs nested (lignes rejetées) dans le
                        # top-level errors : elles ne doivent pas rester
                        # silenciées dans tables_restored (bug banc AN-7 :
                        # outbox errors:2 invisible dans la réponse).
                        row_errors = result.get("errors", 0)
                        if row_errors:
                            summary = (f"Table {table_name}: {row_errors} ligne(s) en échec "
                                       f"(le reste est restauré)")
                            errors.append(summary)
                            logger.warning(f"⚠️ Restore: {summary}")
                            for detail in result.get("errors_detail", []):
                                entry = f"Table {table_name} — {detail}"
                                errors.append(entry)
                                logger.warning(f"⚠️ Restore: {entry}")
                    except Exception as e:
                        await savepoint.rollback()
                        errors.append(f"Table {table_name}: {str(e)}")
                        tables_restored[table_name] = {"imported": 0, "updated": 0, "skipped": 0, "error": str(e)}

            finally:
                if replication_disabled:
                    try:
                        await db.execute(text("SET session_replication_role = DEFAULT"))
                    except Exception:
                        logger.warning(
                            "⚠️ session_replication_role non réinitialisé "
                            "(transaction abortée) — la connexion poolée sera recyclée."
                        )

            # Ré-synchroniser les séquences : l'import insère des ids
            # explicites sans avancer les sequences → le prochain INSERT
            # de l'app sinon échoue en duplicate key. CHAQUE table est isolée
            # par un savepoint (tables sans colonne 'id', ex. schema_migrations,
            # ne doivent pas aborter la transaction).
            if db.get_bind().dialect.name == "postgresql":
                for table_name in ordered_tables:
                    resync = await db.begin_nested()
                    try:
                        col = await db.execute(text(
                            "SELECT 1 FROM information_schema.columns "
                            "WHERE table_schema = 'public' AND table_name = :t AND column_name = 'id'"
                        ), {"t": table_name})
                        if col.scalar() is None:
                            await resync.rollback()
                            continue
                        seq_res = await db.execute(text(
                            f"SELECT pg_get_serial_sequence('\"{table_name}\"', 'id')"
                        ))
                        seq_name = seq_res.scalar()
                        if not seq_name:
                            await resync.rollback()
                            continue
                        await db.execute(text(
                            f"SELECT setval('{seq_name}', "
                            f"COALESCE((SELECT MAX(id) FROM \"{table_name}\"), 1))"
                        ))
                        await resync.commit()
                    except Exception:
                        await resync.rollback()
            
            # 8. Restaurer les fichiers binaires
            file_entries = [f for f in zf.namelist() if f.startswith("files/") and not f.endswith("/")]
            for file_path in file_entries:
                try:
                    relative_path = file_path[6:]  # Remove "files/" prefix
                    file_content = zf.read(file_path)
                    
                    # Extraire owner/category du chemin
                    parts = relative_path.split("/")
                    if len(parts) >= 2:
                        owner = parts[0]
                        category = parts[1]
                        filename = "/".join(parts[2:]) if len(parts) > 2 else parts[-1]
                    else:
                        owner = "_restored"
                        category = "general"
                        filename = relative_path
                    
                    await storage_manager.save_bytes(
                        data=file_content,
                        filename=filename,
                        owner=owner,
                        category=category
                    )
                    files_restored += 1
                except Exception as e:
                    errors.append(f"Fichier {file_path}: {str(e)}")
            
            await db.commit()
        
        # Calculer les totaux
        total_imported = sum(t.get("imported", 0) for t in tables_restored.values())
        total_updated = sum(t.get("updated", 0) for t in tables_restored.values())
        total_skipped = sum(t.get("skipped", 0) for t in tables_restored.values())
        
        logger.info(f"✅ Restauration terminée: {len(tables_restored)} tables, "
                   f"{total_imported} importés, {total_updated} mis à jour, {files_restored} fichiers")
        
        return {
            "success": len(errors) == 0,
            "message": "Restauration terminée" + (" avec des erreurs" if errors else " avec succès"),
            "format_version": format_version,
            "tables_restored": tables_restored,
            "total_tables": len(tables_restored),
            "total_imported": total_imported,
            "total_updated": total_updated,
            "total_skipped": total_skipped,
            "files_restored": files_restored,
            "errors": errors,
            "warnings": warnings,
            # Compatibilité avec l'ancien format
            "items_restored": tables_restored.get("items", {}).get("imported", 0),
            "preferences_restored": tables_restored.get("user_preferences", {}).get("imported", 0),
            "items_skipped": tables_restored.get("items", {}).get("skipped", 0),
            "files_skipped": 0
        }
        
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Le fichier uploadé n'est pas un ZIP valide")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Le fichier data.json est corrompu")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur restauration: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la restauration: {str(e)}")
    finally:
        if tmp_zip_path:
            try:
                os.remove(tmp_zip_path)
            except OSError:
                logger.warning(f"⚠️ Fichier temporaire non supprimé: {tmp_zip_path}")


# ============================================================
# SYNCHRONISATION AVEC LE HUB
# ============================================================

@router.post("/sync-to-hub")
async def sync_to_hub(
    request: SyncToHubRequest = None,
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Pousse le backup complet vers le Hub central.
    
    ⚡ SYSTÈME GÉNÉRIQUE ⚡
    
    Le Hub se charge de:
    - Stocker le backup avec toutes les tables découvertes
    - Gérer les versions
    - Permettre la restauration depuis n'importe quelle instance
    
    ⚠️ Nécessite que l'application soit enregistrée auprès du Hub avec IS_SHARED=true
    """
    if not hub_client.is_registered:
        raise HTTPException(
            status_code=503,
            detail="Application non enregistrée auprès du Hub. Vérifiez la connexion."
        )
    
    logger.info(f"☁️ Synchronisation générique vers le Hub initiée par {user.sub}")
    
    try:
        # 1. Créer un backup générique
        backup_response = await create_backup(db=db, user=user)
        
        if not backup_response.get("success"):
            raise HTTPException(status_code=500, detail="Échec de la création du backup")
        
        metadata = backup_response.get("metadata", {})
        backup_id = metadata.get("backup_id")
        
        # 2. Lire le fichier backup
        backup_path = f"_system/backups/backup_{backup_id}.zip"
        backup_content = await storage_manager.read_file(backup_path)
        
        if not backup_content:
            raise HTTPException(status_code=500, detail="Backup créé mais fichier introuvable")
        
        # 3. Envoyer au Hub via M2M en multipart/form-data
        # Le Hub attend un fichier ZIP + des champs de métadonnées
        result = await hub_client.call_hub_endpoint(
            endpoint=f"/api/apps/{settings.APP_SLUG}/backup",
            method="POST",
            files={
                "file": (f"backup_{backup_id}.zip", backup_content, "application/zip")
            },
            data={
                "backup_id": backup_id,
                "app_version": metadata.get("app_version", APP_VERSION),
                "format_version": metadata.get("format_version", "3.0"),
                "total_tables": str(metadata.get("total_tables", 0)),
                "total_rows": str(metadata.get("total_rows", 0)),
                "total_files": str(metadata.get("total_files", 0)),
                "checksum": metadata.get("checksum", ""),
                "description": request.description if request else ""
            },
            timeout=120.0
        )
        
        if result and result.get("success", True) and not result.get("error"):
            logger.info(f"✅ Backup générique {backup_id} synchronisé avec le Hub "
                       f"({metadata.get('total_tables', 0)} tables, {metadata.get('total_rows', 0)} enregistrements)")
            return {
                "success": True,
                "message": "Backup synchronisé avec le Hub",
                "detail": f"Backup ID: {backup_id}, Tables: {metadata.get('total_tables', 0)}, "
                         f"Enregistrements: {metadata.get('total_rows', 0)}, "
                         f"Taille: {metadata.get('total_size_human', '?')}",
                "backup_id": backup_id,
                "metadata": metadata
            }
        else:
            error_msg = result.get("error", "Erreur inconnue") if result else "Pas de réponse du Hub"
            raise HTTPException(status_code=502, detail=f"Erreur Hub: {error_msg}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur sync vers Hub: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur de synchronisation: {str(e)}")


@router.post("/sync-from-hub")
async def sync_from_hub(
    request: SyncFromHubRequest = None,
    db: AsyncSession = Depends(get_db),
    user: TokenPayload = Depends(require_role("admin"))
):
    """
    Demande au Hub de restaurer le dernier backup vers cette application.
    
    ⚡ SYSTÈME GÉNÉRIQUE ⚡
    
    Le Hub :
    1. Récupère le backup demandé (ou le dernier)
    2. Envoie le fichier ZIP à cette application via POST /api/admin/restore
    3. L'application restaure toutes les tables automatiquement
    
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
    
    logger.info(f"☁️ Demande de restauration générique depuis le Hub par {user.sub} (backup_id={backup_id})")
    
    try:
        # 1. Si pas de backup_id, récupérer les infos du dernier backup
        if not backup_id:
            latest_endpoint = f"/api/apps/{settings.APP_SLUG}/backup/latest"
            latest_result = await hub_client.call_hub_endpoint(
                endpoint=latest_endpoint,
                method="GET"
            )
            
            if not latest_result:
                raise HTTPException(
                    status_code=404, 
                    detail="Aucun backup trouvé sur le Hub pour cette application"
                )
            
            # Le Hub retourne les métadonnées du backup
            backup_id = latest_result.get("backup_id")
            if not backup_id:
                raise HTTPException(
                    status_code=502,
                    detail="Le Hub n'a pas retourné d'identifiant de backup"
                )
            
            logger.info(f"📋 Dernier backup trouvé: {backup_id}")
        
        # 2. Demander au Hub de déclencher la restauration vers cette app
        # Le Hub va appeler POST /api/admin/restore sur cette application
        restore_endpoint = f"/api/apps/{settings.APP_SLUG}/backup/{backup_id}/restore"
        
        result = await hub_client.call_hub_endpoint(
            endpoint=restore_endpoint,
            method="POST",
            data={
                "clear_existing": clear_existing
            },
            timeout=300.0  # Timeout plus long pour la restauration
        )
        
        if not result:
            raise HTTPException(
                status_code=502,
                detail="Pas de réponse du Hub lors de la restauration"
            )
        
        if result.get("error") or result.get("success") is False:
            error_msg = result.get("error", result.get("message", "Erreur inconnue"))
            raise HTTPException(status_code=502, detail=f"Erreur Hub: {error_msg}")
        
        # 3. Retourner le résultat de la restauration (format générique)
        logger.info(f"✅ Restauration générique depuis le Hub terminée: "
                   f"{result.get('total_tables', 0)} tables, {result.get('total_imported', 0)} importés")
        
        return {
            "success": result.get("success", True),
            "message": result.get("message", "Restauration terminée depuis le Hub"),
            "format_version": result.get("format_version", "3.0"),
            "tables_restored": result.get("tables_restored", {}),
            "total_tables": result.get("total_tables", 0),
            "total_imported": result.get("total_imported", 0),
            "total_updated": result.get("total_updated", 0),
            "total_skipped": result.get("total_skipped", 0),
            "files_restored": result.get("files_restored", 0),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
            # Compatibilité avec l'ancien format
            "items_restored": result.get("items_restored", 0),
            "preferences_restored": result.get("preferences_restored", 0),
            "items_skipped": result.get("items_skipped", 0),
            "files_skipped": result.get("files_skipped", 0)
        }
        
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
    Liste les backups stockés localement, triés par created_at (desc).

    Les métadonnées (created_by, checksum, includes_files, …) sont relues
    dans le data.json de chaque ZIP pour rester cohérentes avec celles
    retournées par la création du backup (fix AN-4, banc 2026-09-10).

    Note: Les backups sont normalement envoyés au Hub et supprimés localement.
    Cette liste montre les backups en attente ou conservés temporairement.
    """
    backups = []
    files = await storage_manager.list_files(owner="_system", category="backups")

    for file in files:
        if file["filename"].startswith("backup_") and file["filename"].endswith(".zip"):
            backup_id = file["filename"].replace("backup_", "").replace(".zip", "")

            # Métadonnées par défaut (= comportement dégradé si ZIP illisible)
            created_at = file.get("modified_at", "")
            created_by = "unknown"
            includes_files = False
            total_files = 0
            table_stats: Dict[str, int] = {}
            checksum = ""

            content = await storage_manager.read_file(file["relative_path"])
            if content:
                checksum = _compute_checksum(content)
                try:
                    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                        names = zf.namelist()
                        file_entries = [
                            n for n in names if n.startswith("files/") and not n.endswith("/")
                        ]
                        includes_files = len(file_entries) > 0
                        total_files = len(file_entries)
                        if "data.json" in names:
                            metadata = json.loads(
                                zf.read("data.json").decode("utf-8")
                            ).get("metadata", {})
                            created_by = metadata.get("created_by", created_by)
                            created_at = metadata.get("created_at") or created_at
                            table_stats = metadata.get("table_stats", {}) or {}
                except Exception as e:
                    logger.warning(f"⚠️ Métadonnées illisibles pour {file['filename']}: {e}")

            backups.append(BackupMetadata(
                backup_id=backup_id,
                app_slug=settings.APP_SLUG,
                app_version=APP_VERSION,
                created_at=created_at,
                created_by=created_by,
                total_items=table_stats.get("items", 0),
                total_preferences=table_stats.get("user_preferences", 0),
                total_files=total_files,
                total_size_bytes=file["size"],
                total_size_human=_human_readable_size(file["size"]),
                includes_files=includes_files,
                checksum=checksum
            ))

    # Plus récent d'abord (ISO 8601 : l'ordre lexicographique = l'ordre chronologique)
    backups.sort(key=lambda b: b.created_at or "", reverse=True)

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
