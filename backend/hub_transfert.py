"""
Client Hub Transfert (service partagé `exemple-app`) — module OPT-IN.

Activé par `HUB_TRANSFERT_ENABLED=true` (défaut : désactivé, pattern VPN).
Réutilise le singleton `hub_client` : discovery du service, token M2M,
client httpx partagé. N'utilise PAS `call_discovered_service` (retour
JSON forcé, timeout 30 s) : ce module gère du binaire avec timeout dédié.

Contrat dispatch HFT (routes/routes/dispatch_m2m.py) :
- POST /api/dispatch/m2m/flux/{flux_id}/push   (multipart: file)
- GET  /api/dispatch/m2m/flux                  (mes flux)
- GET  /api/dispatch/m2m/transfers/{id}        (statut)
Headers : Authorization Bearer + X-App-Slug (slug de l'app appelante).
"""
import asyncio
import logging
import mimetypes
from pathlib import Path
from typing import Optional

import httpx

from config import get_settings
from hub_client import hub_client

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300.0  # binaire : généreux par défaut (design §2)


class HubTransfertError(Exception):
    """Échec d'un appel au service Hub Transfert (statut HTTP + détail)."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"hub_transfert: HTTP {status} — {detail}")


class HubTransfertDisabledError(HubTransfertError):
    """Module désactivé : HUB_TRANSFERT_ENABLED=false."""

    def __init__(self):
        super().__init__(0, "module désactivé — activer HUB_TRANSFERT_ENABLED=true")


def _require_enabled() -> None:
    if not get_settings().HUB_TRANSFERT_ENABLED:
        raise HubTransfertDisabledError()


async def _resolve(slug: Optional[str] = None) -> tuple[str, str]:
    """Résout le service transfert → (api_url, token M2M)."""
    settings = get_settings()
    slug = slug or settings.HUB_TRANSFERT_SLUG
    service = await hub_client.get_service_by_slug(slug)
    if not service:
        service = await hub_client.get_service_by_slug(slug, force_refresh=True)
    if not service or not service.api_url:
        raise HubTransfertError(0, f"service '{slug}' introuvable (discovery)")
    token = await hub_client.get_m2m_token()
    if not token:
        raise HubTransfertError(0, "token M2M indisponible")
    return service.api_url.rstrip("/"), token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-App-Slug": get_settings().APP_SLUG,
    }


async def _request(method: str, url: str, *, token: str, timeout: float,
                   **kwargs) -> httpx.Response:
    """Requête authentifiée directe via le client httpx partagé de hub_client."""
    client = await hub_client._get_client()
    response = await client.request(method, url, headers=_headers(token),
                                    timeout=timeout, **kwargs)
    if response.status_code == 401:  # token expiré → resync → 1 retry
        if await hub_client._auto_resync():
            token = await hub_client.get_m2m_token()
            response = await client.request(method, url, headers=_headers(token),
                                            timeout=timeout, **kwargs)
    if response.status_code >= 400:
        raise HubTransfertError(response.status_code, response.text[:300])
    return response


async def _push_simple(api_url: str, token: str, flux_id: str, path: Path,
                       filename: str, timeout: float) -> dict:
    url = f"{api_url}/api/dispatch/m2m/flux/{flux_id}/push"
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        files = {"file": (filename, fh, mime)}
        client = await hub_client._get_client()
        response = await client.post(url, headers=_headers(token), files=files,
                                     timeout=timeout)
        if response.status_code == 401 and await hub_client._auto_resync():
            token = await hub_client.get_m2m_token()
            fh.seek(0)
            response = await client.post(url, headers=_headers(token), files=files,
                                         timeout=timeout)
    if response.status_code >= 400:
        raise HubTransfertError(response.status_code, response.text[:300])
    return response.json()


async def _upload_chunked(api_url: str, token: str, path: Path,
                          filename: str, timeout: float) -> dict:
    raise NotImplementedError("chunked upload — Task 4")


async def upload_file(flux_id: str, file_path, *, filename: Optional[str] = None,
                      chunk_threshold: int = 50 * 1024 * 1024,
                      timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Pousse un fichier dans un flux dispatch.

    En-dessous de `chunk_threshold` : push multipart simple.
    Au-dessus : upload sessionné chunké (voir `_upload_chunked`, Task 4).
    """
    _require_enabled()
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    api_url, token = await _resolve()
    filename = filename or path.name
    if path.stat().st_size > chunk_threshold:
        return await _upload_chunked(api_url, token, path, filename, timeout)
    return await _push_simple(api_url, token, flux_id, path, filename, timeout)


async def list_flux() -> list[dict]:
    """Mes flux dispatch (X-App-Slug)."""
    _require_enabled()
    api_url, token = await _resolve()
    response = await _request("GET", f"{api_url}/api/dispatch/m2m/flux",
                              token=token, timeout=DEFAULT_TIMEOUT)
    return response.json()
