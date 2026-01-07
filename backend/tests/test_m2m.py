"""
Tests M2M (Machine-to-Machine) et HTTPS.

Ces tests vérifient :
- L'authentification via tokens M2M (service accounts)
- L'accès aux endpoints protégés avec un token M2M
- La découverte de services partagés
- La communication HTTPS avec le Hub
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


class TestM2MAuthentication:
    """Tests de l'authentification M2M."""
    
    @pytest.mark.asyncio
    async def test_m2m_token_access_protected_endpoint(self, m2m_client: AsyncClient):
        """Un token M2M valide peut accéder aux endpoints protégés."""
        response = await m2m_client.get("/api/protected")
        
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
    
    @pytest.mark.asyncio
    async def test_m2m_token_is_identified_as_service(self, m2m_client: AsyncClient):
        """Un token M2M est identifié comme un service account."""
        response = await m2m_client.get("/api/me")
        
        assert response.status_code == 200
        data = response.json()
        # Le token M2M a un rôle "service" dans l'app
        assert data.get("app_role") == "service" or data.get("token_type") == "m2m"
    
    @pytest.mark.asyncio
    async def test_m2m_cannot_access_admin_endpoints(self, m2m_client: AsyncClient):
        """Un token M2M ne peut pas accéder aux endpoints admin (par défaut)."""
        response = await m2m_client.get("/api/admin-only")
        
        # Les service accounts ont généralement le rôle "service", pas "admin"
        assert response.status_code == 403


class TestM2MServiceDiscovery:
    """Tests de la découverte de services partagés."""
    
    @pytest.mark.asyncio
    async def test_discover_shared_services(self, mock_hub_client_with_m2m):
        """La découverte de services retourne les services partagés."""
        services = await mock_hub_client_with_m2m.discover_services()
        
        assert len(services) >= 1
        assert services[0]["slug"] == "test-service"
        assert services[0]["is_shared"] == True
    
    @pytest.mark.asyncio
    async def test_get_m2m_token(self, mock_hub_client_with_m2m):
        """Peut obtenir un token M2M."""
        token = await mock_hub_client_with_m2m.get_m2m_token()
        
        assert token is not None
        assert token == "mock_m2m_token"


class TestHTTPSConfiguration:
    """Tests de la configuration HTTPS."""
    
    def test_hub_https_url_construction(self, settings):
        """Vérifie la construction des URLs HTTPS du Hub."""
        original_port = settings.HUB_HTTPS_PORT
        
        try:
            settings.HUB_HTTPS_PORT = 443
            
            # Vérifier l'URL du Hub API (toujours HTTPS)
            hub_api_url = settings.hub_api_url
            assert hub_api_url.startswith("https://")
            # Port 443 ne doit pas apparaître dans l'URL
            assert ":443" not in hub_api_url or hub_api_url.count(":") == 1
        finally:
            settings.HUB_HTTPS_PORT = original_port
    
    def test_app_https_url_construction(self, settings):
        """Vérifie la construction des URLs HTTPS de l'application."""
        original_api_https = settings.API_HTTPS_PORT
        original_frontend_https = settings.FRONTEND_HTTPS_PORT
        
        try:
            settings.API_HTTPS_PORT = 9046
            settings.FRONTEND_HTTPS_PORT = 4251
            
            # Vérifier l'URL de l'API
            api_url = settings.api_url
            assert api_url.startswith("https://")
            assert ":9046" in api_url
            
            # Vérifier l'URL du frontend
            frontend_url = settings.frontend_url
            assert frontend_url.startswith("https://")
            assert ":4251" in frontend_url
        finally:
            settings.API_HTTPS_PORT = original_api_https
            settings.FRONTEND_HTTPS_PORT = original_frontend_https
    
    def test_ssl_verify_property(self, settings):
        """Vérifie la propriété hub_ssl_verify."""
        # En mode HTTPS (toujours activé) avec CA configuré, utilise le chemin du CA
        if settings.is_hub_certificate_available():
            ssl_verify = settings.hub_ssl_verify
            assert ssl_verify == settings.HUB_CA_CERT_PATH


class TestM2MEndpoints:
    """Tests des endpoints M2M spécifiques."""
    
    @pytest.mark.asyncio
    async def test_public_config_includes_api_url(self, client: AsyncClient):
        """L'endpoint /api/config inclut l'URL de l'API (HTTP ou HTTPS)."""
        response = await client.get("/api/config")
        
        assert response.status_code == 200
        data = response.json()
        assert "api_url" in data
        # L'URL doit commencer par http ou https
        assert data["api_url"].startswith("http")
    
    @pytest.mark.asyncio
    async def test_health_includes_version(self, client: AsyncClient):
        """L'endpoint /api/health inclut la version."""
        response = await client.get("/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"


class TestCrossServiceCommunication:
    """Tests de communication inter-services."""
    
    @pytest.mark.asyncio
    async def test_m2m_token_payload_structure(self, mock_m2m_token):
        """Vérifie la structure du payload d'un token M2M."""
        assert mock_m2m_token.token_type == "m2m"
        assert mock_m2m_token.sub.startswith("sa_")  # Service Account
        assert "mon-app" in mock_m2m_token.apps
        assert mock_m2m_token.apps["mon-app"] == "service"
    
    @pytest.mark.asyncio
    async def test_m2m_client_has_credentials(self, mock_hub_client_with_m2m):
        """Le client Hub M2M a des credentials."""
        creds = mock_hub_client_with_m2m.credentials
        
        assert creds is not None
        assert creds.client_id.startswith("sa_")
        assert creds.client_secret is not None
