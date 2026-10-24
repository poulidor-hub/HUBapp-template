"""
Tests de l'introspection du catalogue M2M (déduction d'auth + résolution $ref + endpoint).
"""
import logging
import textwrap

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


class TestBuildAppCatalogSharedDecl:
    """Annotation shared+ia des endpoints déclarés dans m2m_share.yaml.

    build_app_catalog(base_dir=...) consomme load_share_decl (m2m_share) et
    pose `shared: True` + un bloc `ia` (description, example, klass_effective,
    name éventuel) sur les endpoints matchés en (path, method) exact. Le défaut
    est fermé : sans YAML, aucun endpoint n'est annoté. Garde anti-fuite : un
    path matchant (?i)password|secret|credential|token n'est JAMAIS partagé.
    """

    def _make_app(self):
        """Mini-app métier : 2 GET partageables, un POST, un DELETE, un path sensible."""
        app = FastAPI()

        @app.get("/api/assets")
        async def list_assets(user: TokenPayload = Depends(get_current_user)):
            return []

        @app.get("/api/assets/available")
        async def available_assets(user: TokenPayload = Depends(get_current_user)):
            return []

        @app.post("/api/assets")
        async def create_asset(user: TokenPayload = Depends(get_current_user)):
            return {}

        @app.delete("/api/assets/{asset_id}")
        async def delete_asset(asset_id: int, user: TokenPayload = Depends(get_current_user)):
            return {}

        @app.get("/api/assets/{asset_id}/password")
        async def get_password(asset_id: int, user: TokenPayload = Depends(get_current_user)):
            return {}

        return app

    def _write_share(self, tmp_path, entries_yaml):
        """Écrit un m2m_share.yaml valide ({share: [...]}) dans tmp_path."""
        body = textwrap.indent(textwrap.dedent(entries_yaml), "  ")
        (tmp_path / "m2m_share.yaml").write_text(f"share:\n{body}", encoding="utf-8")

    def _build(self, app, base_dir=None):
        return build_app_catalog(app, slug="t", base_dir=base_dir)

    def _by_key(self, catalog):
        return {(e["path"], e["method"]): e for e in catalog["endpoints"]}

    def test_declared_endpoints_annotated_others_untouched(self, tmp_path):
        """2 GET déclarés → shared+ia sur ces 2, absents des autres."""
        app = self._make_app()
        self._write_share(tmp_path, """\
            - path: /api/assets
              method: GET
              ia:
                description: "Liste des assets"
                example: "GET /api/assets"
                name: "Lister les assets"
                klass: "read"
            - path: /api/assets/available
              method: GET
              ia:
                description: "Assets disponibles"
                example: "GET /api/assets/available"
            """)
        catalog = self._build(app, base_dir=tmp_path)
        by_key = self._by_key(catalog)

        shared = by_key[("/api/assets", "GET")]
        assert shared["shared"] is True
        assert shared["ia"]["description"] == "Liste des assets"
        assert shared["ia"]["example"] == "GET /api/assets"
        assert shared["ia"]["name"] == "Lister les assets"
        assert shared["ia"]["klass_effective"] == "read"

        available = by_key[("/api/assets/available", "GET")]
        assert available["shared"] is True
        assert available["ia"]["description"] == "Assets disponibles"
        assert available["ia"]["klass_effective"] == "read"
        assert "name" not in available["ia"]  # name éventuel : absent si non déclaré

        # Les endpoints non déclarés ne portent aucun champ de partage.
        for key in [("/api/assets", "POST"), ("/api/assets/{asset_id}", "DELETE"),
                    ("/api/assets/{asset_id}/password", "GET")]:
            assert "shared" not in by_key[key], key
            assert "ia" not in by_key[key], key

    def test_annotation_preserves_endpoint_structure(self, tmp_path):
        """L'annotation ajoute des champs, sans restructurer l'endpoint."""
        app = self._make_app()
        self._write_share(tmp_path, """\
            - path: /api/assets
              method: GET
              ia:
                description: "Liste des assets"
                example: "GET /api/assets"
            """)
        catalog = self._build(app, base_dir=tmp_path)
        endpoint = self._by_key(catalog)[("/api/assets", "GET")]
        assert set(endpoint) == {
            "path", "method", "summary", "description", "auth_level", "tags",
            "path_params", "query_params", "request_body", "responses",
            "shared", "ia",
        }

    def test_auth_level_strictly_unchanged(self, tmp_path):
        """La déclaration ne touche jamais auth_level (avant/après identiques)."""
        app = self._make_app()
        before = {
            k: e["auth_level"]
            for k, e in self._by_key(self._build(app)).items()
        }
        self._write_share(tmp_path, """\
            - path: /api/assets
              method: GET
              ia:
                description: "Liste"
                example: "GET /api/assets"
            - path: /api/assets
              method: POST
              ia:
                description: "Création"
                example: "POST /api/assets"
            - path: /api/assets/{asset_id}
              method: DELETE
              ia:
                description: "Suppression"
                example: "DELETE /api/assets/1"
            """)
        after = {
            k: e["auth_level"]
            for k, e in self._by_key(self._build(app, base_dir=tmp_path)).items()
        }
        assert before == after
        assert set(after.values()) == {"user"}

    def test_klass_declared_valid_wins_over_verb(self, tmp_path):
        """klass déclaré valide (read|write|irreversible) → klass_effective tel quel."""
        app = self._make_app()
        self._write_share(tmp_path, """\
            - path: /api/assets
              method: POST
              ia:
                description: "Import en masse"
                example: "POST /api/assets"
                klass: "read"
            - path: /api/assets/{asset_id}
              method: DELETE
              ia:
                description: "Suppression"
                example: "DELETE /api/assets/1"
                klass: "irreversible"
            """)
        by_key = self._by_key(self._build(app, base_dir=tmp_path))
        assert by_key[("/api/assets", "POST")]["ia"]["klass_effective"] == "read"
        assert by_key[("/api/assets/{asset_id}", "DELETE")]["ia"]["klass_effective"] == "irreversible"

    def test_klass_absent_derived_from_verb(self, tmp_path):
        """klass absent → dérivé du verbe (GET→read, POST→write, DELETE→irreversible)."""
        app = self._make_app()
        self._write_share(tmp_path, """\
            - path: /api/assets
              method: GET
              ia:
                description: "Liste"
                example: "GET /api/assets"
            - path: /api/assets
              method: POST
              ia:
                description: "Création"
                example: "POST /api/assets"
            - path: /api/assets/{asset_id}
              method: DELETE
              ia:
                description: "Suppression"
                example: "DELETE /api/assets/1"
            """)
        by_key = self._by_key(self._build(app, base_dir=tmp_path))
        assert by_key[("/api/assets", "GET")]["ia"]["klass_effective"] == "read"
        assert by_key[("/api/assets", "POST")]["ia"]["klass_effective"] == "write"
        assert by_key[("/api/assets/{asset_id}", "DELETE")]["ia"]["klass_effective"] == "irreversible"

    def test_klass_invalid_falls_back_to_verb_with_warning(self, tmp_path, caplog):
        """klass invalide → dérivé du verbe + warning (jamais autre chose que read|write|irreversible)."""
        app = self._make_app()
        self._write_share(tmp_path, """\
            - path: /api/assets
              method: GET
              ia:
                description: "Liste"
                example: "GET /api/assets"
                klass: "banana"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_catalog"):
            by_key = self._by_key(self._build(app, base_dir=tmp_path))
        assert by_key[("/api/assets", "GET")]["ia"]["klass_effective"] == "read"
        assert any("banana" in r.message for r in caplog.records)

    def test_sensitive_path_never_shared(self, tmp_path, caplog):
        """Garde anti-fuite : path matchant password|secret|credential|token → shared non posé + warning."""
        app = self._make_app()
        self._write_share(tmp_path, """\
            - path: /api/assets/{asset_id}/password
              method: GET
              ia:
                description: "Mot de passe"
                example: "GET /api/assets/1/password"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_catalog"):
            by_key = self._by_key(self._build(app, base_dir=tmp_path))
        endpoint = by_key[("/api/assets/{asset_id}/password", "GET")]
        assert "shared" not in endpoint
        assert "ia" not in endpoint
        assert any("password" in r.message.lower() for r in caplog.records)

    def test_sensitive_path_match_is_case_insensitive(self, tmp_path):
        """Le garde anti-fuite est insensible à la casse (ex. /api/Credentials)."""
        app = FastAPI()

        @app.get("/api/Credentials")
        async def creds():
            return {}

        self._write_share(tmp_path, """\
            - path: /api/Credentials
              method: GET
              ia:
                description: "Credentials"
                example: "GET /api/Credentials"
            """)
        by_key = self._by_key(self._build(app, base_dir=tmp_path))
        assert "shared" not in by_key[("/api/Credentials", "GET")]

    def test_orphan_declaration_ignored_and_logged(self, tmp_path, caplog):
        """Endpoint déclaré absent du catalogue → ignoré + warning listant le path."""
        app = self._make_app()
        self._write_share(tmp_path, """\
            - path: /api/nowhere
              method: GET
              ia:
                description: "Nulle part"
                example: "GET /api/nowhere"
            """)
        with caplog.at_level(logging.WARNING, logger="m2m_catalog"):
            catalog = self._build(app, base_dir=tmp_path)
        assert all("shared" not in e for e in catalog["endpoints"])
        assert any("/api/nowhere" in r.message for r in caplog.records)

    def test_no_yaml_no_annotation(self, tmp_path):
        """Défaut fermé : base_dir sans m2m_share.yaml (ou base_dir omis) → aucun champ de partage."""
        app = self._make_app()
        for catalog in [self._build(app), self._build(app, base_dir=tmp_path)]:
            assert all("shared" not in e for e in catalog["endpoints"])
            assert all("ia" not in e for e in catalog["endpoints"])


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
    async def test_endpoint_wires_base_dir(self, m2m_client: AsyncClient, monkeypatch):
        """L'endpoint passe le base_dir résolu (resolve_base_dir) au hook d'annotation.

        resolve_base_dir gère le layout repo (racine) comme le layout conteneur
        aplati (/app, COPY backend/ .) ; None (aucun YAML) → défaut fermé.
        """
        import routes.m2m as m2m_routes
        from pathlib import Path

        app_root = Path("/fake-app-root")
        monkeypatch.setattr(m2m_routes, "resolve_base_dir", lambda _file: app_root)

        captured = {}

        def fake_load_share_decl(base_dir):
            captured["base_dir"] = base_dir
            return []

        monkeypatch.setattr("m2m_catalog.load_share_decl", fake_load_share_decl)

        response = await m2m_client.get("/api/m2m/catalog")
        assert response.status_code == 200
        assert captured.get("base_dir") == app_root

    @pytest.mark.asyncio
    async def test_user_cannot_access(self, authenticated_client: AsyncClient):
        response = await authenticated_client.get("/api/m2m/catalog")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_anon_cannot_access(self, client: AsyncClient):
        response = await client.get("/api/m2m/catalog")
        assert response.status_code == 401
