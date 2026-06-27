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
