"""
Routes de découverte de données pour le HUB (M2M).
Permet au HUB d'importer les valeurs d'une table/colonne sans endpoint dédié.

Endpoints:
- GET /api/hub/data/tables            : Liste les tables disponibles
- GET /api/hub/data/columns?table=X   : Liste les colonnes d'une table
- GET /api/hub/data/values?table=X&column=Y : Valeurs distinctes d'une colonne
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, inspect
from database import get_db
from hub_auth import require_role

router = APIRouter(prefix="/api/hub/data", tags=["Hub Data Discovery"])

EXCLUDED_TABLES = {"alembic_version", "spatial_ref_sys"}
MAX_VALUES = 500


def _safe_ident(name: str) -> bool:
    """Vérifie qu'un identifiant SQL est sûr (lettres, chiffres, underscores)."""
    return bool(name) and name.replace("_", "").replace("-", "").isalnum() and len(name) <= 128


@router.get("/tables")
async def list_tables(
    _=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db),
):
    """Liste les noms des tables disponibles dans la base de données."""

    def _sync(sync_conn):
        inspector = inspect(sync_conn)
        return [
            t for t in inspector.get_table_names()
            if t not in EXCLUDED_TABLES
        ]

    conn = await session.connection()
    tables = await conn.run_sync(_sync)
    return {"tables": sorted(tables)}


@router.get("/columns")
async def list_columns(
    table: str = Query(..., description="Nom de la table"),
    _=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db),
):
    """Liste les colonnes d'une table."""
    if not _safe_ident(table):
        raise HTTPException(400, f"Nom de table invalide: {table}")

    def _sync(sync_conn):
        inspector = inspect(sync_conn)
        cols = inspector.get_columns(table)
        return [c["name"] for c in cols if c["name"] not in ("id", "created_at", "updated_at")]

    conn = await session.connection()
    try:
        columns = await conn.run_sync(_sync)
    except Exception:
        raise HTTPException(404, f"Table '{table}' introuvable")
    return {"table": table, "columns": sorted(columns)}


@router.get("/values")
async def list_values(
    table: str = Query(..., description="Nom de la table"),
    column: str = Query(..., description="Nom de la colonne"),
    _=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db),
):
    """Retourne les valeurs distinctes d'une colonne (max 500)."""
    if not _safe_ident(table) or not _safe_ident(column):
        raise HTTPException(400, "Nom de table ou colonne invalide")

    # Valider que la table et la colonne existent
    def _validate(sync_conn):
        inspector = inspect(sync_conn)
        if table not in inspector.get_table_names():
            raise LookupError(f"Table '{table}' introuvable")
        cols = {c["name"] for c in inspector.get_columns(table)}
        if column not in cols:
            raise LookupError(f"Colonne '{column}' introuvable dans la table '{table}'")

    conn = await session.connection()
    try:
        await conn.run_sync(_validate)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except Exception:
        raise HTTPException(404, "Impossible de valider table/colonne")

    # Requête sécurisée via text() avec paramètres bind
    query = text(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL ORDER BY "{column}" LIMIT :limit')
    result = await session.execute(query, {"limit": MAX_VALUES})
    values = [str(row[0]) for row in result.fetchall() if row[0] is not None]

    return {"table": table, "column": column, "values": values, "count": len(values)}
