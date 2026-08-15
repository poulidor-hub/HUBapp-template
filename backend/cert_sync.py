"""Re-synchro périodique des certs HTTPS émis par la PKI du HUB.

Au démarrage puis toutes les 6h (si HTTPS_ENABLED) :
1. POST /api/apps/cert/issue avec le token M2M de l'app.
2. Comparaison avec ssl/ ; réécriture + reload nginx si différence.
Le renouvellement du cert du HUB (changement d'IP, rotation de CA) se
propage donc automatiquement, sans intervention manuelle.

Reload nginx — choix documenté :
- Le répertoire ssl/ est un volume partagé hôte ↔ frontend (./ssl:/etc/nginx/ssl)
  et hôte ↔ backend (./ssl:/app/ssl) : la réécriture des fichiers est visible
  du conteneur frontend.
- Le backend n'a PAS accès au socket Docker (cap_drop ALL) : un `docker exec`
  depuis le conteneur backend est impossible. On tente quand même `docker exec`
  en best-effort (utile en dev, quand le backend tourne sur l'hôte avec la CLI
  docker). Si ça échoue : les nouveaux certs seront chargés par nginx à son
  prochain restart — on log un avertissement « restart requis ».
"""
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("cert_sync")

CERT_FILES = {"cert": "server.crt", "key": "server.key", "ca": "ca.crt"}
SYNC_INTERVAL_SECONDS = 6 * 3600
_ssl_dir = Path(__file__).resolve().parent.parent / "ssl"


def _same_content(directory: Path, filename: str, expected: str) -> bool:
    f = directory / filename
    return f.exists() and f.read_text() == expected


def _write_if_changed(directory: Path, filename: str, content: str) -> bool:
    if _same_content(directory, filename, content):
        return False
    (directory / filename).write_text(content)
    return True


def _reload_nginx() -> None:
    """Reload nginx dans le conteneur frontend (best-effort).

    Ne fonctionne que si la CLI docker est disponible (backend sur l'hôte,
    typiquement en dev). En conteneur (prod), pas de socket docker :
    les certs réécrits seront pris en compte au restart du frontend.
    """
    from config import get_settings
    container = f"{get_settings().APP_SLUG}-frontend"
    try:
        result = subprocess.run(
            ["docker", "exec", container, "nginx", "-s", "reload"],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info(f"🔄 nginx reloadé ({container})")
        else:
            logger.warning(
                f"⚠️ Reload nginx impossible (rc={result.returncode}) — "
                f"restart du conteneur frontend requis pour charger les nouveaux certs"
            )
    except Exception:
        logger.warning(
            "⚠️ Reload nginx impossible (pas de CLI docker / dev local ?) — "
            "restart du conteneur frontend requis pour charger les nouveaux certs"
        )


async def sync_certs_once() -> bool:
    """Récupère le cert auprès du HUB, réécrit ssl/ si différent.

    Returns:
        True si des fichiers ont été réécrits, False sinon (y compris erreur).
    """
    from hub_client import hub_client
    data = await hub_client.fetch_app_cert()
    if not data:
        return False
    _ssl_dir.mkdir(parents=True, exist_ok=True)
    changed = False
    for field, filename in CERT_FILES.items():
        if data.get(field):
            changed = _write_if_changed(_ssl_dir, filename, data[field]) or changed
    if changed:
        logger.info("🔐 Certificats HTTPS re-synchronisés depuis le HUB")
        _reload_nginx()
    return changed


async def cert_sync_loop():
    """Boucle de fond : synchro immédiate au démarrage puis toutes les 6h.

    No-op par itération si HTTPS_ENABLED est false (vérifié à chaque cycle
    pour réagir à un changement de config sans redémarrage).
    """
    from config import get_settings
    while True:
        try:
            if get_settings().HTTPS_ENABLED:
                await sync_certs_once()
        except Exception:
            logger.exception("cert_sync: échec du cycle (réessai dans 6h)")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
