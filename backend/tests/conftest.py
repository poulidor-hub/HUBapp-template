# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""
Configuration pytest pour l'app fine HUBapp Template.

Herméticité (REFERENCE-APP-FINE.md §4) :
- l'env est positionné AVANT tout import (settings évalués au 1er import),
  par ÉCRASEMENT (jamais setdefault — un env atelier ne doit pas fuir ici) ;
- le vrai lifespan ASGI est exécuté via app.router.lifespan_context ;
- l'auth est mockée au niveau hub_socle.auth.hub_auth ;
- offline déterministe : HUB/PG pointent 127.0.0.1:1 (défaillance instantanée).
"""
import pytest
import asyncio
import os
import tempfile
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

import sys
sys.path.insert(0, '.')

# Créer un répertoire temporaire pour le storage AVANT tout import (socle lit
# UPLOADS_DIR au 1er import).
_test_uploads_dir = tempfile.mkdtemp(prefix="app_uploads_")
os.environ["UPLOADS_DIR"] = _test_uploads_dir

# Endpoints démo /api/tests/* désactivés (l'app n'en dépend pas ; items,
# core et preferences sont toujours montés par le socle).
os.environ["ENABLE_DEMO_ENDPOINTS"] = "false"

# Slug réel de l'app démo (les mocks de tokens doivent porter CE slug).
os.environ["APP_SLUG"] = "mon-app"

# Offline déterministe (settings cachés au 1er import du socle).
os.environ["HUB_HOST"] = os.environ["HUB_INTERNAL_HOST"] = "127.0.0.1"
os.environ["HUB_API_PORT"] = os.environ["POSTGRES_PORT"] = "1"
os.environ["POSTGRES_HOST"] = "127.0.0.1"

from hub_socle.database import Base, get_db
from hub_socle.config import get_settings


# ============================================================
# FIXTURES DE BASE
# ============================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Crée un event loop pour les tests async."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings():
    """Settings de test."""
    return get_settings()


@pytest.fixture(scope="session")
def app():
    """L'app fine du template (backend/main.py) — le livrable testé."""
    import main
    return main.app


# ============================================================
# DATABASE FIXTURES
# ============================================================

@pytest.fixture
async def async_engine():
    """Engine SQLite en mémoire pour les tests unitaires."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Session de test."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session


# ============================================================
# AUTH FIXTURES (Mock)
# ============================================================

@pytest.fixture
def mock_hub_client():
    """Mock du client Hub."""
    with patch('hub_socle.hub_client.hub_client') as mock:
        mock.register = AsyncMock(return_value=True)
        mock.fetch_jwks = AsyncMock(return_value={"keys": []})
        mock.fetch_public_key = AsyncMock(return_value="-----BEGIN PUBLIC KEY-----\nMOCK\n-----END PUBLIC KEY-----")
        mock.get_m2m_token = AsyncMock(return_value="mock_m2m_token")
        yield mock


@pytest.fixture
def mock_hub_auth():
    """Mock de l'authentification Hub (au niveau socle)."""
    with patch('hub_socle.auth.hub_auth') as mock:
        mock.initialize = AsyncMock()
        mock.decode_token = MagicMock()
        yield mock


def create_mock_token(
    username: str = "testuser",
    app_role: str = "user",
    token_type: str = "user"
):
    """Helper pour créer un TokenPayload mock."""
    from hub_socle.auth import TokenPayload

    return TokenPayload(
        sub=username,
        apps={get_settings().APP_SLUG: app_role} if app_role else {},
        token_type=token_type,
        exp=9999999999,
        iat=1000000000,
        jti="test-token-id"
    )


# ============================================================
# API CLIENT FIXTURES
# ============================================================

@pytest.fixture
async def app_with_db(app, db_session, mock_hub_client, mock_hub_auth):
    """App avec la session DB injectée."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
async def client(app_with_db) -> AsyncGenerator[AsyncClient, None]:
    """Client HTTP non authentifié."""
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authenticated_client(app_with_db, mock_hub_auth) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié utilisateur standard."""
    mock_hub_auth.decode_token.return_value = create_mock_token(
        username="testuser",
        app_role="user"
    )

    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer mock_token"}
    ) as ac:
        yield ac


@pytest.fixture
async def admin_client(app_with_db, mock_hub_auth) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié admin."""
    mock_hub_auth.decode_token.return_value = create_mock_token(
        username="admin",
        app_role="admin"
    )

    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer admin_mock_token"}
    ) as ac:
        yield ac


@pytest.fixture
def mock_m2m_token():
    """Token M2M mock (service account)."""
    from hub_socle.auth import TokenPayload

    return TokenPayload(
        sub="sa_test_service_account",
        apps={get_settings().APP_SLUG: "service"},
        token_type="m2m",
        exp=9999999999,
        iat=1000000000,
        jti="test-m2m-token-id"
    )


@pytest.fixture
async def m2m_client(client, mock_hub_auth, mock_m2m_token) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié M2M (service account)."""
    mock_hub_auth.decode_token.return_value = mock_m2m_token

    client.headers["Authorization"] = "Bearer mock_m2m_token"
    yield client
