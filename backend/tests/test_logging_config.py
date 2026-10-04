"""
Tests logging horodaté à l'heure du Hub (template) :
- HubClock : offset hub/local (point médian), fallback heure locale UTC
- HubTimeFormatter : format ISO 8601 UTC (…Z) sourcé de HubClock
- setup_logging : root + uvicorn reconfigurés, idempotent
- hub_client.sync_hub_time : applique l'offset via /api/system/time (epoch_ms),
  conserve le fallback en cas d'échec
"""
import logging
import time
from datetime import datetime, timezone

import pytest

from logging_config import HubClock, HubTimeFormatter, setup_logging


@pytest.fixture(autouse=True)
def _fresh_clock():
    """Clock isolé par test + restauration de la config logging globale."""
    HubClock.reset()
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    uvicorn_names = ("uvicorn", "uvicorn.error", "uvicorn.access")
    saved_uvicorn = {n: logging.getLogger(n).handlers[:] for n in uvicorn_names}
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    for n, handlers in saved_uvicorn.items():
        logging.getLogger(n).handlers[:] = handlers
    HubClock.reset()


class TestHubClock:
    def test_fallback_horloge_locale(self):
        """Pas de synchro → offset nul, now_utc = heure locale UTC."""
        clock = HubClock()
        before = datetime.now(timezone.utc)
        now = clock.now_utc()
        after = datetime.now(timezone.utc)
        assert not clock.synced
        assert clock.offset_seconds == 0.0
        assert before <= now <= after

    def test_apply_epoch_ms_point_median(self):
        """offset = epoch_hub − epoch_local (latence absorbée par le point médian)."""
        clock = HubClock()
        local = time.time()
        hub_ms = int((local + 120.5) * 1000)  # Hub « en avance » de 2 min 05
        offset = clock.apply_epoch_ms(hub_ms, local - 0.05, local + 0.05)
        assert clock.synced
        assert 120.0 <= offset <= 121.0
        drift = (clock.now_utc() - datetime.now(timezone.utc)).total_seconds()
        assert 120.0 <= drift <= 121.0

    def test_singleton_partage(self):
        assert HubClock.shared() is HubClock.shared()

    def test_reset(self):
        HubClock.shared()
        HubClock.reset()
        assert HubClock._shared is None


class TestHubTimeFormatter:
    @staticmethod
    def _record() -> logging.LogRecord:
        return logging.LogRecord("app.x", logging.INFO, "f.py", 1, "msg", None, None)

    def test_format_iso8601_utc(self):
        line = HubTimeFormatter("%(asctime)s | %(message)s").format(self._record())
        ts, msg = line.split(" | ", 1)
        assert msg == "msg"
        parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        assert parsed.tzinfo is None  # suffixe Z, valeur UTC

    def test_format_suit_l_offset_hub(self):
        """L'horodatage du log reflète l'heure du Hub (offset appliqué)."""
        HubClock.shared().apply_epoch_ms(
            int((time.time() + 3600) * 1000), time.time() - 0.01, time.time() + 0.01
        )
        line = HubTimeFormatter("%(asctime)s").format(self._record())
        ts = datetime.strptime(line, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        drift = abs((ts - datetime.now(timezone.utc)).total_seconds() - 3600)
        assert drift < 5


class TestSetupLogging:
    def test_root_configure_idempotent(self):
        setup_logging("WARNING")
        setup_logging("WARNING")
        root = logging.getLogger()
        hub_handlers = [h for h in root.handlers if isinstance(h.formatter, HubTimeFormatter)]
        assert len(hub_handlers) == 1
        assert root.level == logging.WARNING

    def test_level_par_defaut_info_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        setup_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_level_invalide_retombe_sur_info(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "CERTAINEMENT_PAS_UN_NIVEAU")
        setup_logging()
        assert logging.getLogger().level == logging.INFO

    def test_loggers_uvicorn_reconfigures(self):
        setup_logging()
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(name)
            assert any(isinstance(h.formatter, HubTimeFormatter) for h in lg.handlers)
            assert lg.propagate is False


class TestSyncHubTime:
    async def test_sync_applique_offset(self, monkeypatch):
        """epoch_ms du Hub → offset appliqué au HubClock partagé."""
        from hub_client import hub_client
        from logging_config import HubClock

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"epoch_ms": int((time.time() + 60) * 1000)}

        class FakeClient:
            async def get(self, url, timeout=None):
                assert url.endswith("/api/system/time")
                return FakeResponse()

        async def fake_get_client():
            return FakeClient()

        monkeypatch.setattr(hub_client, "_get_client", fake_get_client)
        assert await hub_client.sync_hub_time() is True
        assert HubClock.shared().synced
        assert 59 <= HubClock.shared().offset_seconds <= 61

    async def test_sync_echec_reste_fallback(self, monkeypatch):
        """Hub injoignable → False, offset inchangé (heure locale conservée)."""
        from hub_client import hub_client
        from logging_config import HubClock

        class FakeClient:
            async def get(self, url, timeout=None):
                raise ConnectionError("hub down")

        async def fake_get_client():
            return FakeClient()

        monkeypatch.setattr(hub_client, "_get_client", fake_get_client)
        assert await hub_client.sync_hub_time() is False
        assert not HubClock.shared().synced
        assert HubClock.shared().offset_seconds == 0.0

    async def test_sync_sans_epoch_ms_rejete(self, monkeypatch):
        """Réponse 200 sans epoch_ms (hub ancien) → False, pas d'offset."""
        from hub_client import hub_client
        from logging_config import HubClock

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"utc_now": "2026-10-04T12:00:00+00:00"}

        class FakeClient:
            async def get(self, url, timeout=None):
                return FakeResponse()

        async def fake_get_client():
            return FakeClient()

        monkeypatch.setattr(hub_client, "_get_client", fake_get_client)
        assert await hub_client.sync_hub_time() is False
        assert not HubClock.shared().synced
