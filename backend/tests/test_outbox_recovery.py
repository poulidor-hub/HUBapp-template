"""
Tests de fiabilité de l'outbox — crash recovery et verrouillage.

Rappel des bugs corrigés (2.26.4 → 2.27.0) :
- Un message passé in_progress puis interrompu par un crash/restart n'était
  JAMAIS repris (_fetch_pending ne sélectionnait que pending/failed) → perte
  silencieuse. Fix : next_retry_at sert d'horodatage de claim — un
  in_progress dont le claim est expiré (next_retry_at <= now) est repris.
- Pas de FOR UPDATE SKIP LOCKED : deux workers pouvaient prendre le même
  message. Fix : with_for_update(skip_locked=True) (ignoré par SQLite en
  tests, appliqué par PostgreSQL en prod).
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from models import OutboxMessage

pytestmark = pytest.mark.asyncio


def _aware(dt):
    """Normalise un datetime SQLite (naive) en aware UTC pour comparaison."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _mark(msg_id, session, *, status, next_retry_at):
    """Repositionne un message (simulation d'état crashé)."""
    m = await session.get(OutboxMessage, msg_id)
    m.status = status
    m.next_retry_at = next_retry_at
    await session.commit()


class TestCrashRecovery:
    """Un in_progress interrompu doit être repris, pas perdu."""

    async def test_in_progress_stale_is_reclaimed_and_delivered(self, outbox_svc, db_session, monkeypatch):
        msg_id = await outbox_svc.enqueue(
            target_url="http://target/api", target_slug="t", method="POST", payload={"x": 1}
        )
        # Crash simulé : status in_progress, claim expiré (comme après un kill -9)
        now = datetime.now(timezone.utc)
        await _mark(msg_id, db_session, status="in_progress", next_retry_at=now - timedelta(seconds=1))

        deliver = AsyncMock(return_value=True)
        monkeypatch.setattr(outbox_svc, "_deliver", deliver)

        await outbox_svc._process_batch()

        deliver.assert_awaited_once()
        saved = await db_session.get(OutboxMessage, msg_id)
        assert saved.status == "delivered", "le message crashé a été perdu !"

    async def test_in_progress_fresh_claim_not_stolen(self, outbox_svc, db_session, monkeypatch):
        """Un claim récent (next_retry_at futur) n'est pas volé par un autre worker."""
        msg_id = await outbox_svc.enqueue(
            target_url="http://target/api", target_slug="t", method="POST", payload={"x": 1}
        )
        now = datetime.now(timezone.utc)
        await _mark(msg_id, db_session, status="in_progress", next_retry_at=now + timedelta(minutes=5))

        deliver = AsyncMock(return_value=True)
        monkeypatch.setattr(outbox_svc, "_deliver", deliver)

        await outbox_svc._process_batch()

        deliver.assert_not_awaited()
        saved = await db_session.get(OutboxMessage, msg_id)
        assert saved.status == "in_progress", "un claim légitime a été volé !"


class TestClaimTimestamp:
    """Le claim in_progress doit rafraîchir next_retry_at (heartbeat)."""

    async def test_claim_sets_future_next_retry_at(self, outbox_svc, db_session, monkeypatch):
        msg_id = await outbox_svc.enqueue(
            target_url="http://target/api", target_slug="t", method="POST", payload={"x": 1}
        )
        captured = {}

        async def slow_deliver(msg):
            captured["next_retry_at"] = msg.next_retry_at
            captured["status"] = msg.status
            return True

        monkeypatch.setattr(outbox_svc, "_deliver", slow_deliver)
        await outbox_svc._process_batch()

        assert captured["status"] == "in_progress"
        # Le claim doit repousser next_retry_at dans le futur (au-delà de now)
        assert captured["next_retry_at"] is not None
        assert _aware(captured["next_retry_at"]) > datetime.now(timezone.utc), \
            "le claim n'a pas rafraîchi next_retry_at → un crash pendant la livraison perd le message"


class TestMultiWorkerLocking:
    """Verrouillage des lignes traitées (PostgreSQL : FOR UPDATE SKIP LOCKED)."""

    async def test_fetch_pending_compiles_with_skip_locked(self, outbox_svc):
        """Le SELECT de fetch doit porter FOR UPDATE SKIP LOCKED (dialecte PG)."""
        from sqlalchemy.dialects import postgresql

        stmt = outbox_svc._fetch_pending_stmt(datetime.now(timezone.utc))
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE SKIP LOCKED" in compiled, \
            "sans SKIP LOCKED, deux workers traitent le même message"


class TestPurgeLogging:
    async def test_cleanup_returns_count(self, outbox_svc, db_session):
        msg_id = await outbox_svc.enqueue(
            target_url="http://target/api", target_slug="t", method="POST", payload={"x": 1}
        )
        m = await db_session.get(OutboxMessage, msg_id)
        m.status = "delivered"
        m.delivered_at = datetime.now(timezone.utc) - timedelta(days=30)
        await db_session.commit()

        count = await outbox_svc.cleanup_old_messages()
        assert count == 1
