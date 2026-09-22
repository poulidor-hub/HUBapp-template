"""
Tests des endpoints de découverte de données Hub (/api/hub/data/*).

Rappel du bug corrigé (2.26.4 → 2.27.0) : ces routes appelaient
`async with get_db() as session:` sur un async generator (jamais un context
manager) → TypeError systématique → 500 sur les 3 endpoints, sans test de
couverture. Le contrat correct est l'injection FastAPI `Depends(get_db)`,
cohérente avec le reste du template (items.py, backup.py…) et surchargée par
la fixture de test app_with_db.
"""
import pytest

pytestmark = pytest.mark.asyncio


class TestHubDataTables:
    """GET /api/hub/data/tables."""

    async def test_list_tables_returns_200_with_items(self, admin_client):
        resp = await admin_client.get("/api/hub/data/tables")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "tables" in data
        assert isinstance(data["tables"], list)
        # La table métier du template doit être visible
        assert "items" in data["tables"]

    async def test_list_tables_excludes_internal_tables(self, admin_client):
        resp = await admin_client.get("/api/hub/data/tables")
        assert resp.status_code == 200
        tables = resp.json()["tables"]
        for excluded in ("alembic_version", "spatial_ref_sys"):
            assert excluded not in tables

    async def test_list_tables_requires_admin(self, authenticated_client):
        resp = await authenticated_client.get("/api/hub/data/tables")
        assert resp.status_code in (401, 403)


class TestHubDataColumns:
    """GET /api/hub/data/columns?table=X."""

    async def test_list_columns_returns_200(self, admin_client):
        resp = await admin_client.get("/api/hub/data/columns", params={"table": "items"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["table"] == "items"
        assert "title" in data["columns"]
        # Colonnes techniques exclues
        assert "id" not in data["columns"]
        assert "created_at" not in data["columns"]

    async def test_list_columns_rejects_unsafe_identifier(self, admin_client):
        resp = await admin_client.get("/api/hub/data/columns", params={"table": "items; DROP TABLE x"})
        assert resp.status_code == 400

    async def test_list_columns_unknown_table_404(self, admin_client):
        resp = await admin_client.get("/api/hub/data/columns", params={"table": "nope_table"})
        assert resp.status_code == 404


class TestHubDataValues:
    """GET /api/hub/data/values?table=X&column=Y."""

    async def test_list_values_returns_200(self, admin_client, db_session):
        # Seed minimal : un item public
        from models import Item
        db_session.add(Item(title="valeur A", owner="admin", is_public=True))
        db_session.add(Item(title="valeur B", owner="admin", is_public=True))
        await db_session.commit()

        resp = await admin_client.get(
            "/api/hub/data/values", params={"table": "items", "column": "title"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["table"] == "items"
        assert data["column"] == "title"
        assert set(data["values"]) == {"valeur A", "valeur B"}
        assert data["count"] == 2

    async def test_list_values_rejects_unsafe_column(self, admin_client):
        resp = await admin_client.get(
            "/api/hub/data/values", params={"table": "items", "column": "title; DELETE FROM items"}
        )
        assert resp.status_code == 400

    async def test_list_values_unknown_column_404(self, admin_client):
        resp = await admin_client.get(
            "/api/hub/data/values", params={"table": "items", "column": "nope_col"}
        )
        assert resp.status_code == 404
