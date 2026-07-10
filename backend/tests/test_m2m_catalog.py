"""
Tests de l'introspection du catalogue M2M (déduction d'auth + résolution $ref + endpoint).
"""
import pytest
from fastapi import FastAPI, Depends, APIRouter
from httpx import AsyncClient

from hub_auth import (
    require_role, require_service_account, get_current_user, TokenPayload,
)
from m2m_catalog import deduce_auth_level, resolve_refs


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
