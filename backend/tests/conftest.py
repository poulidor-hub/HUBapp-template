"""
Configuration pytest pour les tests.
"""
import pytest
import asyncio
import os
import tempfile
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Import de l'application
import sys
sys.path.insert(0, '.')

# Créer un répertoire temporaire pour le storage AVANT tout import de main/storage
_test_uploads_dir = tempfile.mkdtemp(prefix="test_uploads_")
os.environ["UPLOADS_DIR"] = _test_uploads_dir

# Activer les endpoints démo (/api/tests/*) couverts par test_services.py.
# À positionner AVANT l'import de config/main (settings évalués au 1er import).
os.environ["ENABLE_DEMO_ENDPOINTS"] = "true"

from database import Base, get_db
from config import get_settings

# IMPORTANT : importer models AVANT tout create_all. Sans cet import,
# Base.metadata est vide au moment où la fixture async_engine crée les
# tables → aucune table créée → le premier test DB-écrivain de chaque
# worker échoue ("no such table") selon l'ordre d'exécution.
import models  # noqa: F401

# Slug réel de l'app (settings, surchargeable par env) — les mocks de tokens
# doivent porter CE slug, sinon hub_auth ne résout aucun rôle quand l'app
# instanciée a un slug ≠ "mon-app" (38 tests cassent en conteneur).
APP_SLUG = get_settings().APP_SLUG


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
    """Crée un engine SQLite sur fichier temporaire pour les tests.

    ⚠️ Fichier temporaire (pas :memory:) : avec SQLAlchemy 2.1, les sessions
    concurrentes sur une base :memory: (StaticPool = connexion unique partagée)
    produisent des IDs dupliqués (course sur lastrowid) — ex.
    test_concurrent_enqueue échouait en conteneur (assert 3 == 10) alors qu'il
    passait sur l'hôte (2.0.48). Un fichier temporaire par test donne une base
    unique partagée par toutes les connexions, rowids fiables.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="hubtest_")
    os.close(fd)
    try:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
        )

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        await engine.dispose()
    finally:
        os.unlink(db_path)


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
async def outbox_svc(async_engine):
    """OutboxService branché sur la base de test."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from outbox import OutboxService
    maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    return OutboxService(session_maker=maker)


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
    token_type: str = "user"
):
    """Helper pour créer un TokenPayload mock."""
    from hub_auth import TokenPayload
    
    return TokenPayload(
        sub=username,
        apps={APP_SLUG: app_role} if app_role else {},
        token_type=token_type,
        exp=9999999999,
        iat=1000000000,
        jti="test-token-id"
    )


# ============================================================
# API CLIENT FIXTURE
# ============================================================

@pytest.fixture
async def app_with_db(db_session, mock_hub_client, mock_hub_auth):
    """App avec la session DB injectée."""
    from main import app
    
    # Override de la dépendance DB
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield app
    
    app.dependency_overrides.clear()


@pytest.fixture
async def client(app_with_db) -> AsyncGenerator[AsyncClient, None]:
    """Client HTTP pour tester l'API (non authentifié)."""
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authenticated_client(app_with_db, mock_hub_auth) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié avec un utilisateur standard."""
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
    """Client authentifié avec un admin."""
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
async def viewer_client(app_with_db, mock_hub_auth) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié avec un viewer."""
    mock_hub_auth.decode_token.return_value = create_mock_token(
        username="viewer",
        app_role="viewer"
    )
    
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(
        transport=transport, 
        base_url="http://test",
        headers={"Authorization": "Bearer viewer_mock_token"}
    ) as ac:
        yield ac


# ============================================================
# M2M (Machine-to-Machine) FIXTURES
# ============================================================

@pytest.fixture
def mock_m2m_token():
    """Crée un token M2M mock pour les tests inter-services."""
    from hub_auth import TokenPayload
    
    return TokenPayload(
        sub="sa_test_service_account",
        apps={APP_SLUG: "service"},  # Rôle "service" pour les service accounts
        token_type="m2m",
        exp=9999999999,
        iat=1000000000,
        jti="test-m2m-token-id"
    )


@pytest.fixture
async def m2m_client(client, mock_hub_auth, mock_m2m_token) -> AsyncGenerator[AsyncClient, None]:
    """Client authentifié avec un token M2M (service account)."""
    mock_hub_auth.decode_token.return_value = mock_m2m_token
    
    client.headers["Authorization"] = "Bearer mock_m2m_token"
    yield client


@pytest.fixture
def mock_hub_client_with_m2m(mock_hub_client):
    """Mock du client Hub avec support M2M complet."""
    from unittest.mock import AsyncMock, PropertyMock
    from dataclasses import dataclass
    
    @dataclass
    class MockCredentials:
        client_id: str = "sa_test_client_id"
        client_secret: str = "test_secret"
        access_token: str = "mock_m2m_access_token"
    
    mock_hub_client.credentials = MockCredentials()
    mock_hub_client.is_registered = PropertyMock(return_value=True)
    mock_hub_client.get_m2m_token = AsyncMock(return_value="mock_m2m_token")
    mock_hub_client.discover_services = AsyncMock(return_value=[
        {
            "slug": "test-service",
            "name": "Test Service",
            "api_url": "https://localhost:9000",
            "is_shared": True
        }
    ])
    
    return mock_hub_client
