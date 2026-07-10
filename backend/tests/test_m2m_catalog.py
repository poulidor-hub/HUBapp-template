"""
Tests de l'introspection du catalogue M2M (déduction d'auth + résolution $ref + endpoint).
"""
import pytest
from fastapi import FastAPI, Depends, APIRouter
from httpx import AsyncClient

from hub_auth import (
    require_role, require_service_account, get_current_user, TokenPayload,
)
from m2m_catalog import deduce_auth_level, resolve_refs, build_app_catalog


class TestDeduceAuthLevel:
    """deduce_auth_level lit le niveau d'auth d'une route via ses dépendances."""

    def _make_app_with_routes(self):
        """Construit une mini-app FastAPI avec des routes de chaque niveau d'auth."""
        app = FastAPI()

        @app.get("/public")
        async def public_route():
            return {}

        @app.get("/user-only")
        async def user_route(user: TokenPayload = Depends(get_current_user)):
            return {}

        @app.get("/admin-only")
        async def admin_route(user: TokenPayload = Depends(require_role("admin"))):
            return {}

        @app.get("/m2m-sync")
        async def service_route(sa: TokenPayload = Depends(require_service_account())):
            return {}

        return app

    def test_public_route(self):
        app = self._make_app_with_routes()
        route = self._find_route(app, "/public", "GET")
        assert deduce_auth_level(route) == "public"

    def test_user_route(self):
        app = self._make_app_with_routes()
        route = self._find_route(app, "/user-only", "GET")
        assert deduce_auth_level(route) == "user"

    def test_admin_route(self):
        app = self._make_app_with_routes()
        route = self._find_route(app, "/admin-only", "GET")
        assert deduce_auth_level(route) == "admin"

    def test_service_route_takes_priority(self):
        app = self._make_app_with_routes()
        route = self._find_route(app, "/m2m-sync", "GET")
        assert deduce_auth_level(route) == "service"

    def _find_route(self, app, path, method):
        for r in app.routes:
            methods = {m.lower() for m in getattr(r, "methods", set())}
            if getattr(r, "path", None) == path and method.lower() in methods:
                return r
        raise AssertionError(f"Route {method} {path} introuvable")


class TestResolveRefs:
    """resolve_refs inline les $ref et détecte les cycles."""

    def test_resolves_simple_ref(self):
        spec = {
            "paths": {
                "/items": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Item"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Item": {"type": "object", "properties": {"id": {"type": "integer"}}}
                }
            },
        }
        resolved = resolve_refs(spec)
        schema = resolved["paths"]["/items"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        # Le $ref est inliné
        assert schema["type"] == "object"
        assert "id" in schema["properties"]
        assert "$ref" not in schema

    def test_detects_circular_ref(self):
        spec = {
            "paths": {
                "/tree": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Node"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Node": {
                        "type": "object",
                        "properties": {
                            "children": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Node"},
                            }
                        },
                    }
                }
            },
        }
        resolved = resolve_refs(spec)
        node = resolved["paths"]["/tree"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        # Le premier niveau est inliné
        assert node["type"] == "object"
        # La référence circulaire (Node dans Node) est marquée, pas bouclée
        children_items = node["properties"]["children"]["items"]
        assert children_items.get("$ref_circular") == "Node"


class TestBuildAppCatalog:
    """build_app_catalog assemble le catalogue d'une app à partir de ses routes."""

    def test_catalog_structure_and_exclusions(self):
        from fastapi import FastAPI
        from hub_auth import require_role, require_service_account, get_current_user, TokenPayload

        app = FastAPI()

        @app.get("/api/items")
        async def list_items(user: TokenPayload = Depends(get_current_user)):
            """Liste des items."""
            return []

        @app.post("/api/m2m/sync")
        async def sync(sa: TokenPayload = Depends(require_service_account())):
            return {}

        catalog = build_app_catalog(app, slug="test-app", name="Test", version="1.0.0")

        assert catalog["slug"] == "test-app"
        assert catalog["name"] == "Test"
        assert catalog["version"] == "1.0.0"
        assert catalog["introspection_source"] == "m2m-catalog"
        # 2 endpoints métier (les routes techniques /docs, /openapi.json exclues)
        paths = {(e["path"], e["method"]) for e in catalog["endpoints"]}
        assert ("/api/items", "GET") in paths
        assert ("/api/m2m/sync", "POST") in paths
        # Les routes techniques sont exclues
        assert all("/docs" != e["path"] for e in catalog["endpoints"])
        assert all("/openapi.json" != e["path"] for e in catalog["endpoints"])

    def test_auth_levels_assigned(self):
        from fastapi import FastAPI
        from hub_auth import require_role, require_service_account, get_current_user, TokenPayload

        app = FastAPI()

        @app.get("/api/public-ish")
        async def p():
            return {}

        @app.get("/api/secure")
        async def s(user: TokenPayload = Depends(get_current_user)):
            return {}

        @app.get("/api/svc")
        async def sv(sa: TokenPayload = Depends(require_service_account())):
            return {}

        catalog = build_app_catalog(app, slug="x")
        by_path = {e["path"]: e["auth_level"] for e in catalog["endpoints"]}
        assert by_path["/api/public-ish"] == "public"
        assert by_path["/api/secure"] == "user"
        assert by_path["/api/svc"] == "service"


class TestAppCatalogEndpoint:
    """L'endpoint GET /api/m2m/catalog retourne le catalogue et est service-only."""

    @pytest.mark.asyncio
    async def test_service_account_can_access(self, m2m_client: AsyncClient):
        response = await m2m_client.get("/api/m2m/catalog")
        assert response.status_code == 200
        data = response.json()
        assert "endpoints" in data
        assert "introspection_source" in data

    @pytest.mark.asyncio
    async def test_user_cannot_access(self, authenticated_client: AsyncClient):
        response = await authenticated_client.get("/api/m2m/catalog")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_anon_cannot_access(self, client: AsyncClient):
        response = await client.get("/api/m2m/catalog")
        assert response.status_code == 401
