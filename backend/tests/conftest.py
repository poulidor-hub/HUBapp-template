"""
Configuration pytest pour les tests.
"""
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Import de l'application
import sys
sys.path.insert(0, '.')

from database import Base, get_db
from config import get_settings


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


# ============================================================
# DATABASE FIXTURES
# ============================================================

@pytest.fixture
async def async_engine():
    """Crée un engine SQLite en mémoire pour les tests."""
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
    """Crée une session de test."""
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
    with patch('hub_client.hub_client') as mock:
        mock.register = AsyncMock(return_value=True)
        mock.fetch_jwks = AsyncMock(return_value={"keys": []})
        mock.fetch_public_key = AsyncMock(return_value="-----BEGIN PUBLIC KEY-----\nMOCK\n-----END PUBLIC KEY-----")
        mock.get_m2m_token = AsyncMock(return_value="mock_m2m_token")
        yield mock


@pytest.fixture
def mock_hub_auth():
    """Mock de l'authentification Hub."""
    with patch('hub_auth.hub_auth') as mock:
        mock.initialize = AsyncMock()
        mock.decode_token = MagicMock()
        yield mock


def create_mock_token(
    username: str = "testuser",
    app_role: str = "user",
    global_roles: list = None,
    token_type: str = "user"
):
    """Helper pour créer un TokenPayload mock."""
    from hub_auth import TokenPayload
    
    return TokenPayload(
        sub=username,
        roles=global_roles or [],
        apps={"mon-app": app_role} if app_role else {},
        token_type=token_type,
        exp=9999999999,
        iat=1000000000,
        jti="test-token-id"
    )


# ============================================================
# API CLIENT FIXTURE
# ============================================================

@pytest.fixture
async def client(db_session, mock_hub_client, mock_hub_auth) -> AsyncGenerator[AsyncClient, None]:
    """Client HTTP pour tester l'API."""
    from main import app
    
    # Override de la dépendance DB
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(client, mock_hub_auth) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié avec un utilisateur standard."""
    mock_hub_auth.decode_token.return_value = create_mock_token(
        username="testuser",
        app_role="user"
    )
    
    # Ajouter le header Authorization
    client.headers["Authorization"] = "Bearer mock_token"
    yield client


@pytest.fixture
async def admin_client(client, mock_hub_auth) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié avec un admin."""
    mock_hub_auth.decode_token.return_value = create_mock_token(
        username="admin",
        app_role="admin",
        global_roles=["admin"]
    )
    
    client.headers["Authorization"] = "Bearer admin_mock_token"
    yield client


@pytest.fixture
async def viewer_client(client, mock_hub_auth) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié avec un viewer."""
    mock_hub_auth.decode_token.return_value = create_mock_token(
        username="viewer",
        app_role="viewer"
    )
    
    client.headers["Authorization"] = "Bearer viewer_mock_token"
    yield client
