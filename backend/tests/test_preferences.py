"""
Tests des préférences utilisateur.
"""
import pytest
from httpx import AsyncClient


class TestPreferences:
    """Tests des préférences utilisateur."""
    
    @pytest.mark.asyncio
    async def test_get_preferences_requires_auth(self, client: AsyncClient):
        """Les préférences requièrent une authentification."""
        response = await client.get("/api/preferences")
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_get_preferences_creates_default(self, authenticated_client: AsyncClient):
        """Si pas de préférences, des valeurs par défaut sont créées."""
        response = await authenticated_client.get("/api/preferences")
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["theme"] == "system"
        assert data["language"] == "fr"
        assert data["items_per_page"] == 20
    
    @pytest.mark.asyncio
    async def test_update_preferences(self, authenticated_client: AsyncClient):
        """Mise à jour des préférences."""
        response = await authenticated_client.put("/api/preferences", json={
            "theme": "dark",
            "items_per_page": 50
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["theme"] == "dark"
        assert data["items_per_page"] == 50
        # Les autres champs gardent leur valeur
        assert data["language"] == "fr"
    
    @pytest.mark.asyncio
    async def test_update_preferences_validation(self, authenticated_client: AsyncClient):
        """Validation des valeurs de préférences."""
        # Thème invalide
        response = await authenticated_client.put("/api/preferences", json={
            "theme": "invalid"
        })
        assert response.status_code == 422
        
        # items_per_page hors limites
        response = await authenticated_client.put("/api/preferences", json={
            "items_per_page": 1000
        })
        assert response.status_code == 422
