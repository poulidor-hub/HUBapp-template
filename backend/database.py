"""
Configuration de la base de données PostgreSQL avec SQLAlchemy async.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from typing import AsyncGenerator
from pathlib import Path
import logging

from config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class pour tous les modèles SQLAlchemy."""
    pass


# Engine async
engine = create_async_engine(
    get_settings().database_url,
    echo=get_settings().DEBUG,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # Recycler les connexions toutes les 30 min
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dépendance FastAPI pour obtenir une session de base de données.
    
    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Initialise la base de données (crée les tables si elles n'existent pas)."""
    try:
        async with engine.begin() as conn:
            # checkfirst=True évite les erreurs si les tables existent déjà
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    except Exception as e:
        # Ignorer les erreurs de tables/types existants (race condition avec HTTPS/HTTP)
        error_msg = str(e).lower()
        if "already exists" in error_msg or "duplicate key" in error_msg:
            pass  # Table ou type déjà créé par l'autre instance
        else:
            raise


async def close_db():
    """Ferme les connexions à la base de données."""
    await engine.dispose()


def _strip_sql_comments(sql_block: str) -> str:
    """Retire les lignes de commentaires SQL (--) d'un bloc et renvoie le SQL nettoyé."""
    lines = [line for line in sql_block.splitlines() if not line.strip().startswith('--')]
    return '\n'.join(lines).strip()


async def apply_migrations():
    """
    Applique automatiquement les migrations SQL depuis le dossier migrations/.
    Utilise une table schema_migrations pour suivre les migrations appliquées.
    Les fichiers doivent suivre le format NNN_description.sql (ex: 001_add_column.sql).
    """
    migrations_dir = Path("/app/migrations")
    if not migrations_dir.exists():
        # Mode local (hors Docker)
        migrations_dir = Path(__file__).parent / "migrations"

    if not migrations_dir.exists():
        logger.info("ℹ️ Pas de dossier migrations/ — aucune migration à appliquer")
        return

    # Lister et trier les fichiers de migration
    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        return

    async with engine.begin() as conn:
        # Créer la table de suivi si elle n'existe pas
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(10) PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Récupérer les migrations déjà appliquées
        result = await conn.execute(text("SELECT version FROM schema_migrations"))
        applied = {row[0] for row in result.fetchall()}

        # Appliquer les nouvelles migrations dans l'ordre
        for mf in migration_files:
            version = mf.name.split('_')[0]
            if version in applied:
                continue

            logger.info(f"📦 Application de la migration {mf.name}...")
            sql = mf.read_text()
            for statement in sql.split(';'):
                statement = _strip_sql_comments(statement)
                if statement:
                    try:
                        await conn.execute(text(statement))
                    except Exception as e:
                        logger.warning(f"Migration {mf.name} statement ignoré: {e}")

            await conn.execute(text(
                "INSERT INTO schema_migrations (version, filename) VALUES (:v, :f)"
            ), {"v": version, "f": mf.name})
            logger.info(f"✅ Migration {mf.name} appliquée")
