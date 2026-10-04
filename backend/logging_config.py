"""
Configuration de logging centralisée — horodatée à l'heure du Hub.

Convention parc (règle 10, guide-parc-poulidor.md) : UTC strict. L'horodatage
des logs est sourcé de l'horloge du Hub, autorité temps du parc : les apps
maintiennent un offset (heure hub − heure locale) rafraîchi via
GET /api/system/time (champ epoch_ms, endpoint public). Le Hub lui-même est
la référence : son offset reste nul, il utilise ce module uniquement pour
le format commun.

Fallback : tant qu'aucune synchro n'a réussi (ou si le Hub redevient
injoignable, le dernier offset est conservé), l'horloge locale UTC est
utilisée — conforme à la convention.

Format de ligne :
    2026-10-04T12:34:56.789Z | INFO     | app.hub_client | message
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Loggers uvicorn reconfigurés pour porter le même format horodaté
# (uvicorn.configure_logging() tourne AVANT l'import de l'app : notre
# configuration, appliquée à l'import de main.py, a donc le dernier mot).
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class HubClock:
    """Horloge de référence du parc : heure du Hub maintenue par offset.

    offset = epoch_hub − epoch_local, mesuré lors de la synchro (point
    médian request/réponse pour absorber la latence réseau). Tant
    qu'aucune synchro n'a réussi, offset = 0 → heure locale UTC.
    """

    _shared: HubClock | None = None

    def __init__(self) -> None:
        self._offset_seconds: float = 0.0
        self._last_sync_monotonic: float | None = None

    @classmethod
    def shared(cls) -> HubClock:
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @classmethod
    def reset(cls) -> None:
        """Réinitialise le singleton (tests)."""
        cls._shared = None

    @property
    def offset_seconds(self) -> float:
        return self._offset_seconds

    @property
    def synced(self) -> bool:
        """True si au moins une synchro Hub a réussi."""
        return self._last_sync_monotonic is not None

    @property
    def age_seconds(self) -> float | None:
        """Secondes (monotonic) depuis la dernière synchro réussie."""
        if self._last_sync_monotonic is None:
            return None
        return time.monotonic() - self._last_sync_monotonic

    def apply_epoch_ms(self, epoch_ms: int, t_before: float, t_after: float) -> float:
        """Applique un epoch_ms du Hub, mesuré entre t_before et t_after.

        t_before/t_after sont des epochs locaux en secondes (time.time()),
        pris juste avant/après la requête ; le point médian
        ((t_before+t_after)/2) absorbe la latence réseau. Retourne
        l'offset appliqué en secondes.
        """
        hub_epoch_s = epoch_ms / 1000.0
        local_mid = (t_before + t_after) / 2.0
        self._offset_seconds = hub_epoch_s - local_mid
        self._last_sync_monotonic = time.monotonic()
        return self._offset_seconds

    def now_utc(self) -> datetime:
        """Heure « du Hub » estimée (UTC, timezone-aware)."""
        return datetime.now(timezone.utc) + timedelta(seconds=self._offset_seconds)


class HubTimeFormatter(logging.Formatter):
    """Formatter ISO 8601 UTC, horodatage sourcé de HubClock."""

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:  # noqa: N802
        dt = HubClock.shared().now_utc()
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{dt.microsecond // 1000:03d}Z"


def _resolve_level(level: int | str | None) -> int:
    """Résout le niveau : argument explicite > LOG_LEVEL (env) > INFO."""
    if isinstance(level, int):
        return level
    raw = str(level if level is not None else os.getenv("LOG_LEVEL", "INFO")).strip().upper()
    resolved = logging.getLevelName(raw)
    return resolved if isinstance(resolved, int) else logging.INFO


def setup_logging(level: int | str | None = None) -> None:
    """Configure root + loggers uvicorn avec le format horodaté Hub.

    Idempotent : ré-appeler ne duplique pas les handlers. À appeler au boot
    (import de main.py / create_app) avant les premiers logs applicatifs.
    Les filtres attachés aux loggers (ex. _SuppressLegacySSE401Filter sur
    uvicorn.access) sont préservés : seuls les handlers sont remplacés.
    """
    resolved = _resolve_level(level)
    handler = logging.StreamHandler()
    handler.setFormatter(HubTimeFormatter(LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)

    for name in _UVICORN_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.setLevel(resolved)
        lg.propagate = False
