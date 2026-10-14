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

# Alias de l'engine global (permet à apply_migrations(engine=...) d'avoir un
# paramètre nommé naturellement sans masquer la globale).
_default_engine = engine


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
    """Retire les commentaires SQL (--) d'un bloc : lignes entières ET fins de
    ligne, en ignorant les occurrences de '--' placées dans une chaîne quotée
    ('...' avec échappement '' en SQL).

    Doit être appelé AVANT _split_sql_statements : une apostrophe dans un
    commentaire (« d'ingestion ») ouvre sinon une chaîne fantôme dans le
    splitter, qui avale tous les ';' suivants et fusionne la migration entière
    en un statement → échec systématique, migration jamais appliquée
    (bug 2.30.2 : fresh-install bloquée, ex. exports 003/006).
    """
    cleaned_lines: list[str] = []
    for line in sql_block.splitlines():
        out: list[str] = []
        in_string = False
        i = 0
        while i < len(line):
            ch = line[i]
            if in_string:
                out.append(ch)
                if ch == "'":
                    if i + 1 < len(line) and line[i + 1] == "'":
                        out.append("'")  # '' échappé → un seul quote
                        i += 1
                    else:
                        in_string = False
            elif ch == "'":
                in_string = True
                out.append(ch)
            elif ch == '-' and line[i + 1:i + 2] == '-':
                break  # commentaire → on coupe jusqu'à la fin de ligne
            else:
                out.append(ch)
            i += 1
        cleaned_lines.append(''.join(out).rstrip())
    return '\n'.join(cleaned_lines).strip()


def _split_sql_statements(sql: str) -> list[str]:
    """Split un script SQL sur ';' en ignorant les points-virgules placés
    dans des chaînes quotées ('...' avec échappement '' en SQL).

    Un split naïf sur ';' casse les statements contenant une valeur du type
    VALUES ('a;b') — le statement tronqué échoue et la donnée est perdue.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_string = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_string:
            buf.append(ch)
            if ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":
                    buf.append("'")  # '' échappé → un seul quote
                    i += 1
                else:
                    in_string = False
        elif ch == "'":
            in_string = True
            buf.append(ch)
        elif ch == ';':
            statements.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        statements.append("".join(buf))
    return statements


async def apply_migrations(
    migrations_dir: Path = None,
    engine=None,
):
    """
    Applique automatiquement les migrations SQL depuis le dossier migrations/.
    Utilise une table schema_migrations pour suivre les migrations appliquées.
    Les fichiers doivent suivre le format NNN_description.sql (ex: 001_add_column.sql).

    Chaque statement est isolé via SAVEPOINT pour éviter qu'un échec
    (ex: colonne déjà existante) n'avorte toute la transaction PostgreSQL.

    Fiabilité : une migration n'est marquée « appliquée » que si TOUS ses
    statements passent. En cas d'échec partiel, elle n'est PAS enregistrée
    (log ERROR) et sera re-jouée au prochain démarrage — les migrations
    doivent donc être idempotentes (IF NOT EXISTS, ALTER tolérant, etc.).

    Args:
        migrations_dir: dossier des migrations (défaut : /app/migrations ou
            ./migrations en mode local) — injectable pour les tests.
        engine: engine SQLAlchemy async cible (défaut : engine global).
    """
    if migrations_dir is None:
        migrations_dir = Path("/app/migrations")
        if not migrations_dir.exists():
            # Mode local (hors Docker)
            migrations_dir = Path(__file__).parent / "migrations"

    migrations_dir = Path(migrations_dir)
    if not migrations_dir.exists():
        logger.info("ℹ️ Pas de dossier migrations/ — aucune migration à appliquer")
        return

    target_engine = engine or _default_engine

    async with target_engine.begin() as conn:
        # Créer la table de suivi si elle n'existe pas
        # (CURRENT_TIMESTAMP : accepté par PostgreSQL ET SQLite)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(10) PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Récupérer les migrations déjà appliquées
        result = await conn.execute(text("SELECT version FROM schema_migrations"))
        applied = {row[0] for row in result.fetchall()}

        # Appliquer les nouvelles migrations dans l'ordre
        for mf in sorted(migrations_dir.glob("*.sql")):
            version = mf.name.split('_')[0]
            if version in applied:
                continue

            logger.info(f"📦 Application de la migration {mf.name}...")
            sql = mf.read_text()
            failed_statements = 0
            # Strip des commentaires AVANT le split : une apostrophe dans un
            # commentaire (« d'ingestion ») ouvre sinon une chaîne fantôme dans
            # le splitter → tous les ';' avalés → un seul statement fusionné →
            # migration jamais appliquée (bug 2.30.2, ex. exports 003/006).
            for statement in _split_sql_statements(_strip_sql_comments(sql)):
                statement = statement.strip()
                if statement:
                    try:
                        await conn.execute(text("SAVEPOINT migration_stmt"))
                        await conn.execute(text(statement))
                        await conn.execute(text("RELEASE SAVEPOINT migration_stmt"))
                    except Exception as e:
                        await conn.execute(text("ROLLBACK TO SAVEPOINT migration_stmt"))
                        failed_statements += 1
                        logger.warning(f"Migration {mf.name} statement en échec: {e}")

            if failed_statements:
                # NE PAS marquer appliquée : elle sera re-jouée au prochain
                # démarrage (les statements déjà passés doivent être idempotents).
                logger.error(
                    f"❌ Migration {mf.name} partiellement appliquée "
                    f"({failed_statements} statement(s) en échec) — NON marquée "
                    f"appliquée, nouvelle tentative au prochain démarrage"
                )
                continue

            await conn.execute(text(
                "INSERT INTO schema_migrations (version, filename) VALUES (:v, :f)"
            ), {"v": version, "f": mf.name})
            logger.info(f"✅ Migration {mf.name} appliquée")
