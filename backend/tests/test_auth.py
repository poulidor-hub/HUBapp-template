"""
Tests des endpoints publics et d'authentification.
"""
import pytest
from httpx import AsyncClient


class TestPublicEndpoints:
    """Tests des endpoints publics (sans authentification)."""
    
    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Le health check doit toujours fonctionner."""
        response = await client.get("/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_public_config(self, client: AsyncClient):
        """La config publique doit être accessible."""
        response = await client.get("/api/config")
        
        assert response.status_code == 200
        data = response.json()
        assert "app_slug" in data
        assert "hub_api_url" in data
        assert "hub_frontend_url" in data
    
    @pytest.mark.asyncio
    async def test_public_endpoint(self, client: AsyncClient):
        """L'endpoint public doit être accessible sans token."""
        response = await client.get("/api/public")
        
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] == False


class TestProtectedEndpoints:
    """Tests des endpoints protégés."""
    
    @pytest.mark.asyncio
    async def test_protected_without_token(self, client: AsyncClient):
        """Sans token, l'accès doit être refusé."""
        response = await client.get("/api/protected")
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_protected_with_token(self, authenticated_client: AsyncClient):
        """Avec un token valide, l'accès est autorisé."""
        response = await authenticated_client.get("/api/protected")
        
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
    
    @pytest.mark.asyncio
    async def test_me_endpoint(self, authenticated_client: AsyncClient):
        """L'endpoint /me retourne les infos utilisateur."""
        response = await authenticated_client.get("/api/me")
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["app_role"] == "user"


class TestRoleEndpoints:
    """Tests des endpoints par rôle."""
    
    @pytest.mark.asyncio
    async def test_viewer_access_viewer_endpoint(self, viewer_client: AsyncClient):
        """Un viewer peut accéder à viewer-only."""
        response = await viewer_client.get("/api/viewer-only")
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_viewer_cannot_access_user_endpoint(self, viewer_client: AsyncClient):
        """Un viewer ne peut pas accéder à user-only."""
        response = await viewer_client.get("/api/user-only")
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_user_access_user_endpoint(self, authenticated_client: AsyncClient):
        """Un user peut accéder à user-only."""
        response = await authenticated_client.get("/api/user-only")
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_user_cannot_access_admin_endpoint(self, authenticated_client: AsyncClient):
        """Un user ne peut pas accéder à admin-only."""
        response = await authenticated_client.get("/api/admin-only")
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_admin_access_all_endpoints(self, admin_client: AsyncClient):
        """Un admin peut accéder à tous les endpoints."""
        endpoints = [
            "/api/viewer-only",
            "/api/user-only",
            "/api/manager-only",
            "/api/admin-only"
        ]
        
        for endpoint in endpoints:
            response = await admin_client.get(endpoint)
            assert response.status_code == 200, f"Admin should access {endpoint}"
