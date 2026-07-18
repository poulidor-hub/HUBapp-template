"""
Transactional Outbox — garantie de livraison des appels M2M.

Principe :
1. Un appel M2M échoue après tous les retries → écrit dans la table outbox
2. Un worker asynchrone tourne en arrière-plan, lit les messages pending/failed
3. Tente la livraison avec backoff exponentiel (30s * 2^n, max ~17h)
4. Marque delivered ou failed (dead letter) après max_retries tentatives
5. Auth provider callback permet de régénérer les tokens M2M à la livraison

Aucune nouvelle infrastructure : utilise PostgreSQL et HTTP (httpx).
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Awaitable

from sqlalchemy import select, or_, and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database import async_session_maker as _default_session_maker
from models import OutboxMessage

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5
BATCH_SIZE = 50
BASE_BACKOFF = 30
DELIVERED_RETENTION_DAYS = 7
FAILED_RETENTION_DAYS = 30


class OutboxService:

    def __init__(self, session_maker: Optional[async_sessionmaker] = None):
        self._session_maker = session_maker or _default_session_maker
        self._worker_task: Optional[asyncio.Task] = None
        self._auth_provider: Optional[Callable[[str], Awaitable[dict]]] = None

    def set_auth_provider(self, provider: Callable[[str], Awaitable[dict]]):
        self._auth_provider = provider

    async def enqueue(
        self,
        target_url: str,
        method: str = "POST",
        headers: Optional[dict] = None,
        payload: Optional[dict] = None,
        target_slug: Optional[str] = None,
        auth_context: Optional[dict] = None,
        max_retries: int = 10,
    ) -> int:
        async with self._session_maker() as session:
            now = datetime.now(timezone.utc)
            msg = OutboxMessage(
                target_url=target_url,
                target_slug=target_slug or "unknown",
                method=method.upper(),
                headers=headers or {},
                payload=payload,
                auth_context=auth_context,
                max_retries=max_retries,
                next_retry_at=now,
            )
            session.add(msg)
            await session.commit()
            logger.info(
                f"📦 Message outbox #{msg.id} enqueued -> "
                f"{target_slug or target_url} ({method})"
            )
            return msg.id

    async def _fetch_pending(self, session: AsyncSession) -> list[OutboxMessage]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(OutboxMessage)
            .where(
                or_(
                    and_(
                        OutboxMessage.status == "pending",
                        OutboxMessage.next_retry_at <= now,
                    ),
                    and_(
                        OutboxMessage.status == "failed",
                        OutboxMessage.next_retry_at <= now,
                        OutboxMessage.retry_count < OutboxMessage.max_retries,
                    ),
                )
            )
            .order_by(OutboxMessage.created_at.asc())
            .limit(BATCH_SIZE)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _deliver(self, msg: OutboxMessage) -> bool:
        import httpx

        try:
            headers = dict(msg.headers or {})

            if msg.auth_context and msg.auth_context.get("type") == "m2m" and self._auth_provider:
                slug = msg.auth_context.get("slug") or msg.target_slug
                auth_headers = await self._auth_provider(slug)
                headers.update(auth_headers)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=msg.method,
                    url=msg.target_url,
                    headers=headers or None,
                    json=msg.payload,
                )

                if 200 <= response.status_code < 300:
                    logger.info(
                        f"✅ Outbox #{msg.id} delivered to "
                        f"{msg.target_slug} (HTTP {response.status_code})"
                    )
                    return True

                logger.warning(
                    f"⚠️ Outbox #{msg.id} HTTP {response.status_code} -> {msg.target_slug}"
                )
                msg.last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                return False

        except httpx.RequestError as e:
            logger.warning(
                f"⚠️ Outbox #{msg.id} network error -> {msg.target_slug}: {e}"
            )
            msg.last_error = f"{type(e).__name__}: {e}"
            return False

    async def _process_batch(self):
        async with self._session_maker() as session:
            messages = await self._fetch_pending(session)
            if not messages:
                return

            now = datetime.now(timezone.utc)

            for msg in messages:
                msg.status = "in_progress"
                await session.flush()

                delivered = await self._deliver(msg)

                if delivered:
                    msg.status = "delivered"
                    msg.delivered_at = now
                    msg.next_retry_at = None
                else:
                    msg.retry_count += 1
                    if msg.retry_count >= msg.max_retries:
                        msg.status = "failed"
                        msg.next_retry_at = None
                        logger.error(
                            f"❌ Outbox #{msg.id} to {msg.target_slug} "
                            f"dead letter after {msg.max_retries} attempts: "
                            f"{msg.last_error}"
                        )
                    else:
                        msg.status = "failed"
                        backoff = BASE_BACKOFF * (2 ** (msg.retry_count - 1))
                        msg.next_retry_at = now + timedelta(seconds=backoff)
                        logger.info(
                            f"🔄 Outbox #{msg.id} to {msg.target_slug} "
                            f"retry in {backoff}s "
                            f"(attempt {msg.retry_count}/{msg.max_retries})"
                        )

            await session.commit()

    async def _worker_loop(self):
        logger.info("🚀 Outbox worker started")
        while True:
            try:
                await asyncio.sleep(POLL_INTERVAL)
                await self._process_batch()
            except asyncio.CancelledError:
                logger.info("🛑 Outbox worker stopped")
                break
            except Exception as e:
                logger.error(f"❌ Outbox worker error: {e}", exc_info=True)
                await asyncio.sleep(POLL_INTERVAL)

    def start_worker(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop_worker(self):
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def retry_failed_message(self, msg_id: int) -> bool:
        async with self._session_maker() as session:
            msg = await session.get(OutboxMessage, msg_id)
            if not msg:
                return False
            if msg.status != "failed":
                return False
            msg.status = "pending"
            msg.next_retry_at = datetime.now(timezone.utc)
            msg.retry_count = 0
            msg.last_error = None
            await session.commit()
            logger.info(f"🔄 Outbox #{msg_id} re-queued for retry")
            return True

    async def get_stats(self) -> dict:
        async with self._session_maker() as session:
            total = await session.scalar(
                select(func.count()).select_from(OutboxMessage)
            )
            result = await session.execute(
                select(OutboxMessage.status, func.count().label("c"))
                .group_by(OutboxMessage.status)
            )
            counts = {row.status: row.c for row in result.fetchall()}

            last = await session.scalar(
                select(OutboxMessage.created_at)
                .order_by(OutboxMessage.created_at.desc())
                .limit(1)
            )

            return {
                "total": total or 0,
                "pending": counts.get("pending", 0),
                "in_progress": counts.get("in_progress", 0),
                "delivered": counts.get("delivered", 0),
                "failed": counts.get("failed", 0),
                "last_message_at": last.isoformat() if last else None,
            }

    async def cleanup_old_messages(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._session_maker() as session:
            deleted = await session.execute(
                delete(OutboxMessage).where(
                    or_(
                        and_(
                            OutboxMessage.status == "delivered",
                            OutboxMessage.delivered_at < now - timedelta(days=DELIVERED_RETENTION_DAYS),
                        ),
                        and_(
                            OutboxMessage.status == "failed",
                            OutboxMessage.created_at < now - timedelta(days=FAILED_RETENTION_DAYS),
                        ),
                    )
                )
            )
            await session.commit()
            count = deleted.rowcount or 0
            return count
            if deleted.rowcount:
                logger.info(f"🧹 Purged {deleted.rowcount} old outbox messages")


outbox_service = OutboxService()
