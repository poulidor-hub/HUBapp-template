"""Client HTTP standalone pour hub-mcp (sans dépendance au ``backend`` d'une app).

Utilisé quand hub-mcp tourne hors d'une app HUBapp_TEMPLATE_base — typiquement
depuis le méta-repo POULIDOR. Configuré via les variables d'environnement :

  HUB_BASE_URL        URL de base de l'API du Hub (ex: ``http://192.0.2.10:8000``)
  HUB_ADMIN_USERNAME  login admin du Hub (ex: ``admin``)
  HUB_ADMIN_PASSWORD  mot de passe admin du Hub

S'authentifie au premier appel (``POST /api/auth/token``, ``grant_type=password``)
et utilise le token pour tous les ``call_hub_endpoint``, avec un re-login
automatique sur ``401``. Le contrat (``call_hub_endpoint(path, method, json)``)
est identique à celui de ``backend.hub_client.hub_client`` → transparent pour
``tools.py`` (les lambdas n'ont pas à changer).

Pour passer en mode standalone depuis le méta-repo : définir les 3 variables
ci-dessus (ex: dans le fichier ``.secrets`` sourcé par ``~/.bashrc``).
"""
import os
import threading

import httpx


class StandaloneHubClient:
    """Client HTTP direct vers le Hub (mode standalone du MCP ``hub``)."""

    def __init__(self):
        base = (os.environ.get("HUB_BASE_URL") or "").rstrip("/")
        username = os.environ.get("HUB_ADMIN_USERNAME")
        password = os.environ.get("HUB_ADMIN_PASSWORD")
        missing = [
            name for name, value in (
                ("HUB_BASE_URL", base),
                ("HUB_ADMIN_USERNAME", username),
                ("HUB_ADMIN_PASSWORD", password),
            ) if not value
        ]
        if missing:
            raise RuntimeError(
                "hub_mcp standalone: variables d'environnement manquantes : "
                + ", ".join(missing)
                + ". Définir HUB_BASE_URL, HUB_ADMIN_USERNAME et HUB_ADMIN_PASSWORD "
                "(ex: dans le fichier .secrets sourcé par ~/.bashrc)."
            )
        self._base_url = base
        self._username = username
        self._password = password
        self._token = None
        self._lock = threading.Lock()

    def _login(self) -> None:
        """Authentifie l'admin et cache l'access_token."""
        r = httpx.post(
            f"{self._base_url}/api/auth/token",
            data={
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
            },
            timeout=10,
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"hub_mcp standalone: échec login (HTTP {r.status_code}) : {r.text[:200]}"
            )
        token = r.json().get("access_token")
        if not token:
            raise RuntimeError(
                f"hub_mcp standalone: login sans access_token : {r.text[:200]}"
            )
        self._token = token

    async def call_hub_endpoint(self, path: str, method: str = "GET", json=None, params=None, data=None, **_kwargs):
        """Appelle une route du Hub et retourne le JSON (ou le texte sinon).

        Signature compatible avec ``backend.hub_client.hub_client.call_hub_endpoint``.
        Accepte ``params`` (query string) et ``data`` (form-encoded body).
        """
        with self._lock:
            if self._token is None:
                self._login()
            url = f"{self._base_url}{path}"
            # 2 tentatives max : la 2e après un re-login si 401 (token expiré).
            for attempt in (1, 2):
                headers = {"Authorization": f"Bearer {self._token}"}
                # follow_redirects=True : FastAPI redirige souvent les routes sans
                # trailing slash (ex: /api/apps → 307 /api/apps/). Sans ça, l'appel
                # retourne un body vide non-JSON.
                r = httpx.request(method, url, json=json, params=params, data=data, headers=headers, timeout=30, follow_redirects=True)
                if r.status_code == 401 and attempt == 1:
                    self._login()
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(
                        f"hub_mcp standalone: {method} {path} → HTTP {r.status_code} "
                        f": {r.text[:300]}"
                    )
                try:
                    return r.json()
                except ValueError:
                    return r.text
            return None

    # --- Propriétés et méthodes attendues par les handlers tools.py ---

    @property
    def is_registered(self) -> bool:
        """En mode standalone, pas d'enregistrement d'app locale."""
        return False

    @property
    def credentials(self):
        """En mode standalone, pas de credentials locales."""
        return None

    async def discover_services(self) -> dict:
        """GET /api/apps/discover — liste les services partagés."""
        result = await self.call_hub_endpoint("/api/apps/discover", method="GET")
        # Transformer en dict {slug: info} pour compatibilité avec le handler existant
        if isinstance(result, dict) and "shared_services" in result:
            return {s["slug"]: s for s in result["shared_services"]}
        return result

    async def fetch_jwks(self) -> dict:
        """GET /api/auth/.well-known/jwks.json — récupère les clés JWKS."""
        return await self.call_hub_endpoint("/api/auth/.well-known/jwks.json", method="GET")

    async def get_m2m_token(self) -> str | None:
        """POST /api/auth/token avec client_credentials — obtient un token M2M."""
        try:
            result = await self.call_hub_endpoint(
                "/api/auth/token", method="POST",
                data={"grant_type": "client_credentials"},
            )
            return result.get("access_token") if isinstance(result, dict) else None
        except Exception:
            return None

    async def call_discovered_service(self, service_slug: str, endpoint: str,
                                      method: str = "GET", json=None) -> dict:
        """Appelle un endpoint d'un service découvert via le Hub.

        Résout l'URL du service via ``discover_services``, puis appelle l'endpoint.
        """
        services = await self.discover_services()
        svc = services.get(service_slug)
        if not svc:
            raise RuntimeError(
                f"hub_mcp standalone: service '{service_slug}' non trouvé "
                f"parmi les services découverts"
            )
        api_url = svc.get("api_url") or svc.get("url") or ""
        if not api_url:
            raise RuntimeError(
                f"hub_mcp standalone: service '{service_slug}' sans api_url"
            )
        full_url = f"{api_url.rstrip('/')}{endpoint}"
        with self._lock:
            if self._token is None:
                self._login()
            headers = {"Authorization": f"Bearer {self._token}"}
            r = httpx.request(method, full_url, json=json, headers=headers, timeout=30, follow_redirects=True)
            if r.status_code >= 400:
                raise RuntimeError(
                    f"hub_mcp standalone: {method} {full_url} → HTTP {r.status_code} "
                    f": {r.text[:300]}"
                )
            try:
                return r.json()
            except ValueError:
                return {"text": r.text}
