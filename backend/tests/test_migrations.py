"""
Tests du système de migrations (database.apply_migrations).

Rappel des bugs corrigés (2.26.4 → 2.27.0) :
- Une migration à moitié appliquée (un statement en échec avalé) était
  quand même insérée dans schema_migrations → jamais re-jouée, sans aucune
  trace d'erreur fatale. Fix : marquer "appliquée" UNIQUEMENT si tous les
  statements passent ; sinon log ERROR et nouvelle tentative au prochain
  démarrage (les statements valides sont idempotents).
- Split naïf sur ';' : un point-virgule dans une chaîne SQL ('a;b') cassait
  le statement. Fix : split conscient des chaînes quotées.

Les tests tournent sur SQLite (mécanique : savepoints + tracking) ; les
migrations de production (PG) sont idempotentes (IF NOT EXISTS / ALTER).
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine

import database
from database import Base

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def migration_engine(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    yield engine
    await engine.dispose()


@pytest.fixture
def migrations_dir(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    return d


class TestPartialFailureTracking:
    async def test_failed_migration_not_marked_applied(self, migration_engine, migrations_dir):
        (migrations_dir / "901_test_partial.sql").write_text(
            "CREATE TABLE IF NOT EXISTS zz_ok (id INTEGER PRIMARY KEY);\n"
            "INSERT INTO zz_table_inexistante VALUES (1);\n"
        )
        await database.apply_migrations(migrations_dir=migrations_dir, engine=migration_engine)

        async with migration_engine.connect() as conn:
            applied = {row[0] for row in (await conn.execute(
                text("SELECT version FROM schema_migrations")
            )).fetchall()}
        assert "901" not in applied, "migration en échec partiel marquée appliquée !"

    async def test_partial_statements_still_applied(self, migration_engine, migrations_dir):
        """Le statement valide d'une migration partielle est appliqué (savepoint)."""
        (migrations_dir / "901_test_partial.sql").write_text(
            "CREATE TABLE IF NOT EXISTS zz_ok (id INTEGER PRIMARY KEY);\n"
            "INSERT INTO zz_table_inexistante VALUES (1);\n"
        )
        await database.apply_migrations(migrations_dir=migrations_dir, engine=migration_engine)

        async with migration_engine.connect() as conn:
            tables = {row[0] for row in (await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )).fetchall()}
        assert "zz_ok" in tables

    async def test_failed_migration_retried_on_next_run(self, migration_engine, migrations_dir):
        """Après correction du fichier, la migration est rejouée et marquée."""
        path = migrations_dir / "901_test_partial.sql"
        path.write_text("INSERT INTO zz_table_inexistante VALUES (1);\n")
        await database.apply_migrations(migrations_dir=migrations_dir, engine=migration_engine)

        async with migration_engine.connect() as conn:
            applied = {row[0] for row in (await conn.execute(
                text("SELECT version FROM schema_migrations")
            )).fetchall()}
        assert "901" not in applied

        # L'opérateur corrige la migration → nouveau démarrage
        path.write_text("CREATE TABLE IF NOT EXISTS zz_fixed (id INTEGER PRIMARY KEY);\n")
        await database.apply_migrations(migrations_dir=migrations_dir, engine=migration_engine)

        async with migration_engine.connect() as conn:
            applied = {row[0] for row in (await conn.execute(
                text("SELECT version FROM schema_migrations")
            )).fetchall()}
        assert "901" in applied, "la migration corrigée n'a pas été rejouée"


class TestQuoteAwareSplit:
    async def test_semicolon_inside_string_not_split(self, migration_engine, migrations_dir):
        (migrations_dir / "902_test_quote.sql").write_text(
            "CREATE TABLE IF NOT EXISTS zz_notes (id INTEGER PRIMARY KEY, value TEXT);\n"
            "INSERT INTO zz_notes (value) VALUES ('a;b;c');\n"
        )
        await database.apply_migrations(migrations_dir=migrations_dir, engine=migration_engine)

        async with migration_engine.connect() as conn:
            values = [row[0] for row in (await conn.execute(
                text("SELECT value FROM zz_notes")
            )).fetchall()]
        assert values == ["a;b;c"], "le ';' dans la chaîne a cassé le statement"


class TestHappyPath:
    async def test_successful_migration_marked_applied(self, migration_engine, migrations_dir):
        (migrations_dir / "903_test_ok.sql").write_text(
            "CREATE TABLE IF NOT EXISTS zz_happy (id INTEGER PRIMARY KEY);\n"
        )
        await database.apply_migrations(migrations_dir=migrations_dir, engine=migration_engine)

        async with migration_engine.connect() as conn:
            applied = {row[0] for row in (await conn.execute(
                text("SELECT version FROM schema_migrations")
            )).fetchall()}
            # Re-run : pas de doublon, pas d'erreur
        await database.apply_migrations(migrations_dir=migrations_dir, engine=migration_engine)
        assert "903" in applied
