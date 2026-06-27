"""Tests pour le système de transactional outbox."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import text

from models import OutboxMessage

pytestmark = pytest.mark.asyncio


async def test_outbox_table_exists(db_session):
    """Vérifie que la table outbox existe (créée par SQLAlchemy create_all)."""
    result = await db_session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='outbox'"
    ))
    assert result.scalar() == "outbox"


async def test_create_outbox_message(db_session):
    """Test la création d'un message outbox."""
    msg = OutboxMessage(
        target_url="http://service:8000/api/data",
        target_slug="mon-service",
        method="POST",
        payload={"key": "value"},
        auth_context={"type": "m2m", "slug": "mon-service"},
    )
    db_session.add(msg)
    await db_session.commit()

    saved = await db_session.get(OutboxMessage, msg.id)
    assert saved is not None
    assert saved.target_slug == "mon-service"
    assert saved.payload == {"key": "value"}
    assert saved.auth_context == {"type": "m2m", "slug": "mon-service"}
    assert saved.status == "pending"
    assert saved.retry_count == 0
    assert saved.max_retries == 10
    assert saved.created_at is not None
    assert saved.next_retry_at is not None


async def test_outbox_default_values(db_session):
    """Test les valeurs par défaut d'un message outbox."""
    msg = OutboxMessage(
        target_url="http://service/api",
        target_slug="test",
    )
    db_session.add(msg)
    await db_session.commit()

    assert msg.method == "POST"
    assert msg.headers == {}
    assert msg.status == "pending"
    assert msg.retry_count == 0
    assert msg.max_retries == 10


async def test_outbox_status_transitions(db_session):
    """Test les transitions de statut."""
    msg = OutboxMessage(
        target_url="http://service:8000/api/data",
        target_slug="test",
        method="GET",
    )
    db_session.add(msg)
    await db_session.commit()

    msg.status = "in_progress"
    await db_session.commit()
    assert msg.status == "in_progress"

    msg.status = "delivered"
    msg.delivered_at = datetime.now(timezone.utc)
    await db_session.commit()
    assert msg.status == "delivered"
    assert msg.delivered_at is not None


async def test_outbox_nullable_fields(db_session):
    """Test que les champs optionnels peuvent être null."""
    msg = OutboxMessage(
        target_url="http://service/api",
        method="POST",
    )
    db_session.add(msg)
    await db_session.commit()

    saved = await db_session.get(OutboxMessage, msg.id)
    assert saved.target_slug is None
    assert saved.payload is None
    assert saved.auth_context is None
    assert saved.last_error is None
    assert saved.delivered_at is None


@pytest.fixture
async def outbox_svc(async_engine):
    """OutboxService with test database session."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from outbox import OutboxService
    maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    return OutboxService(session_maker=maker)


async def test_enqueue_message(outbox_svc, db_session):
    """Test l'enqueue d'un message via OutboxService."""
    msg_id = await outbox_svc.enqueue(
        target_url="http://target:8000/api/data",
        target_slug="target-app",
        method="POST",
        payload={"hello": "world"},
        auth_context={"type": "m2m", "slug": "target-app"},
        max_retries=3,
    )
    assert isinstance(msg_id, int)
    assert msg_id > 0

    saved = await db_session.get(OutboxMessage, msg_id)
    assert saved is not None
    assert saved.target_slug == "target-app"
    assert saved.payload == {"hello": "world"}
    assert saved.auth_context == {"type": "m2m", "slug": "target-app"}
    assert saved.max_retries == 3
    assert saved.status == "pending"
    assert saved.next_retry_at is not None


async def test_enqueue_default_max_retries(outbox_svc, db_session):
    """Test que max_retries vaut 10 par défaut."""
    msg_id = await outbox_svc.enqueue(
        target_url="http://target/api",
        target_slug="test",
        method="GET",
    )
    saved = await db_session.get(OutboxMessage, msg_id)
    assert saved.max_retries == 10


async def test_get_stats_empty(outbox_svc):
    """Test les stats quand l'outbox est vide."""
    stats = await outbox_svc.get_stats()
    assert stats["total"] == 0
    assert stats["pending"] == 0
    assert stats["delivered"] == 0
    assert stats["failed"] == 0


async def test_get_stats_with_messages(outbox_svc, db_session):
    """Test les stats avec des messages."""
    await outbox_svc.enqueue(target_url="http://a/api", target_slug="a", method="POST", payload={"x": 1})
    await outbox_svc.enqueue(target_url="http://b/api", target_slug="b", method="POST", payload={"x": 2})

    stats = await outbox_svc.get_stats()
    assert stats["total"] == 2
    assert stats["pending"] == 2


async def test_worker_delivers_success(outbox_svc, monkeypatch):
    """Test que le worker livre un message avec succès."""
    msg_id = await outbox_svc.enqueue(
        target_url="http://localhost:9999/api/test",
        target_slug="test",
        method="POST",
        payload={"order": 42},
    )

    calls = []

    async def mock_request(self, method, url, **kwargs):
        calls.append({"method": method, "url": url, "json": kwargs.get("json")})
        class FakeResp:
            status_code = 200
            async def aiter_bytes(self):
                return
            def json(self):
                return {}
        return FakeResp()

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)
    monkeypatch.setattr("outbox.POLL_INTERVAL", 0.1)

    await outbox_svc._process_batch()

    from models import OutboxMessage
    async with outbox_svc._session_maker() as session:
        saved = await session.get(OutboxMessage, msg_id)
    assert saved.status == "delivered"
    assert saved.delivered_at is not None
    assert len(calls) == 1
    assert calls[0]["json"] == {"order": 42}


async def test_worker_retries_on_network_error(outbox_svc, monkeypatch):
    """Test que le worker retry en cas d'erreur réseau (5xx)."""
    msg_id = await outbox_svc.enqueue(
        target_url="http://localhost:9999/api/test",
        target_slug="test",
        method="GET",
        max_retries=2,
    )

    async def mock_500(self, method, url, **kwargs):
        class FakeResp:
            status_code = 503
            text = "Service Unavailable"
            async def aiter_bytes(self):
                return
        return FakeResp()

    monkeypatch.setattr("httpx.AsyncClient.request", mock_500)
    monkeypatch.setattr("outbox.POLL_INTERVAL", 0.1)
    monkeypatch.setattr("outbox.BASE_BACKOFF", 0.1)

    await outbox_svc._process_batch()

    async with outbox_svc._session_maker() as session:
        saved = await session.get(OutboxMessage, msg_id)
    assert saved.status == "failed"
    assert saved.retry_count == 1
    assert saved.last_error is not None


async def test_worker_dead_letter_after_max_retries(outbox_svc, monkeypatch):
    """Test dead letter après max_retries échecs."""
    import httpx
    msg_id = await outbox_svc.enqueue(
        target_url="http://localhost:9999/api/test",
        target_slug="test",
        method="GET",
        max_retries=1,
    )

    async def mock_fail(self, method, url, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("httpx.AsyncClient.request", mock_fail)
    monkeypatch.setattr("outbox.POLL_INTERVAL", 0.1)
    monkeypatch.setattr("outbox.BASE_BACKOFF", 0.1)

    await outbox_svc._process_batch()

    async with outbox_svc._session_maker() as session:
        saved = await session.get(OutboxMessage, msg_id)
    assert saved.status == "failed"
    assert saved.retry_count == 1
    assert "ConnectError" in saved.last_error


async def test_retry_failed_message(outbox_svc, monkeypatch):
    """Test retry manuel d'un message failed."""
    import httpx
    msg_id = await outbox_svc.enqueue(
        target_url="http://localhost:9999/api/test",
        target_slug="test",
        method="GET",
        max_retries=1,
    )

    async def mock_fail(self, method, url, **kwargs):
        raise httpx.ConnectError("Fail")

    monkeypatch.setattr("httpx.AsyncClient.request", mock_fail)
    monkeypatch.setattr("outbox.POLL_INTERVAL", 0.1)
    monkeypatch.setattr("outbox.BASE_BACKOFF", 0.1)

    await outbox_svc._process_batch()

    async with outbox_svc._session_maker() as session:
        saved = await session.get(OutboxMessage, msg_id)
    assert saved.status == "failed"

    result = await outbox_svc.retry_failed_message(msg_id)
    assert result is True

    async with outbox_svc._session_maker() as session:
        saved = await session.get(OutboxMessage, msg_id)
    assert saved.status == "pending"
    assert saved.retry_count == 0


async def test_worker_skips_4xx_errors(outbox_svc, monkeypatch):
    """Test que les 4xx sont considérées comme livrées (pas de retry applicatif)."""
    msg_id = await outbox_svc.enqueue(
        target_url="http://localhost:9999/api/test",
        target_slug="test",
        method="POST",
        payload={"bad": "request"},
    )

    async def mock_400(self, method, url, **kwargs):
        class FakeResp:
            status_code = 400
            text = "Bad Request"
            async def aiter_bytes(self):
                return
        return FakeResp()

    monkeypatch.setattr("httpx.AsyncClient.request", mock_400)
    monkeypatch.setattr("outbox.POLL_INTERVAL", 0.1)

    await outbox_svc._process_batch()

    async with outbox_svc._session_maker() as session:
        saved = await session.get(OutboxMessage, msg_id)
    assert saved.status == "delivered"
