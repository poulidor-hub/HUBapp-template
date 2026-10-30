"""
Jeu de tests minimal d'une app fine (REFERENCE-APP-FINE.md §7) — miroir canari.

1. health expose socle_version ;      2. écriture visible en 2-sessions
(commits explicites) ;                3. POST /api/items 201 + visible ;
4. cloisonnement owner ;              5. garde longueur 422 ;
6. 404 propre ;                       7. DELETE puis 404.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from hub_socle import __version__
from hub_socle.database import Base, get_db


# ============================================================
# 2-sessions : SQLite FICHIER tmp (jamais :memory: — StaticPool partagerait
# une connexion et masquerait la course de visibilité des commits).
# ============================================================

@pytest.fixture
async def file_engine(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/canary.db",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_on_file_db(app, file_engine):
    """App dont get_db est branché sur le moteur fichier (session A du test 2)."""
    maker = async_sessionmaker(file_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def file_client(app_on_file_db, file_engine, mock_hub_client, mock_hub_auth):
    """Client authentifié (user) sur l'app branchée en DB fichier."""
    from hub_socle.auth import TokenPayload
    from hub_socle.config import get_settings
    mock_hub_auth.decode_token.return_value = TokenPayload(
        sub="alice", apps={get_settings().APP_SLUG: "user"},
        token_type="user", exp=9999999999, iat=1000000000, jti="t",
    )
    transport = ASGITransport(app=app_on_file_db)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer t"},
    ) as ac:
        yield ac, file_engine


# ============================================================
# 7 tests minimaux
# ============================================================

class TestCanary:
    async def test_1_health_exposes_socle_version(self, app, client, mock_hub_client, mock_hub_auth):
        """socle_version est posé par le lifespan → on exécute le VRAI
        lifespan ASGI (§4) en mode dégradé (Hub mocké, hosts hors-ligne)."""
        async with app.router.lifespan_context(app):
            resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["socle_version"] == __version__

    async def test_2_create_item_visible_by_independent_session(self, file_client):
        """Écriture (session A via l'app) immédiatement visible par une
        session B indépendante — preuve du commit explicite du handler."""
        file_ac, file_engine = file_client
        resp = await file_ac.post(
            "/api/items",
            json={"title": "visible-en-2-sessions", "description": "canari"},
        )
        assert resp.status_code == 201

        maker = async_sessionmaker(file_engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session_b:
            from sqlalchemy import text
            rows = (await session_b.execute(
                text("SELECT title FROM items WHERE title = 'visible-en-2-sessions'")
            )).fetchall()
        assert rows, "l'écriture n'est pas visible par une session indépendante"

    async def test_3_create_item_via_api_201(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/items", json={"title": "canari-201"}
        )
        assert resp.status_code == 201
        listing = (await authenticated_client.get("/api/items")).json()
        assert any(i["title"] == "canari-201" for i in listing["items"])

    async def test_4_list_items_filtered_by_owner(self, authenticated_client):
        await authenticated_client.post("/api/items", json={"title": "a-alice"})
        listing = (await authenticated_client.get("/api/items")).json()
        owners = {i["owner"] for i in listing["items"]}
        assert owners == {"testuser"}, f"cloisonnement owner rompu : {owners}"

    async def test_5_create_item_name_too_long_422(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/items", json={"title": "x" * 256}
        )
        assert resp.status_code == 422

    async def test_6_get_unknown_item_404(self, authenticated_client):
        resp = await authenticated_client.get("/api/items/999999")
        assert resp.status_code == 404
        assert "non trouvé" in resp.json()["detail"].lower()

    async def test_7_delete_item_then_404(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/items", json={"title": "à-supprimer"}
        )
        item_id = resp.json()["id"]
        assert (await authenticated_client.delete(f"/api/items/{item_id}")).status_code == 200
        assert (await authenticated_client.get(f"/api/items/{item_id}")).status_code == 404
