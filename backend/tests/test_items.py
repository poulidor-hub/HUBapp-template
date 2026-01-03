"""
Tests du CRUD Items.
"""
import pytest
from httpx import AsyncClient


class TestItemsCRUD:
    """Tests des opérations CRUD sur les Items."""
    
    @pytest.mark.asyncio
    async def test_list_items_public(self, client: AsyncClient):
        """La liste des items publics est accessible sans auth."""
        response = await client.get("/api/items")
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
    
    @pytest.mark.asyncio
    async def test_create_item_requires_auth(self, client: AsyncClient):
        """La création d'item requiert une authentification."""
        response = await client.post("/api/items", json={
            "title": "Test Item",
            "description": "Description",
            "is_public": True
        })
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_create_item_requires_user_role(self, viewer_client: AsyncClient):
        """Un viewer ne peut pas créer d'items (rôle user minimum)."""
        response = await viewer_client.post("/api/items", json={
            "title": "Test Item",
            "description": "Description",
            "is_public": True
        })
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_create_item_success(self, authenticated_client: AsyncClient):
        """Un user peut créer un item."""
        response = await authenticated_client.post("/api/items", json={
            "title": "Mon Item",
            "description": "Ma description",
            "is_public": False
        })
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Mon Item"
        assert data["owner"] == "testuser"
        assert data["is_public"] == False
        assert "id" in data
    
    @pytest.mark.asyncio
    async def test_get_public_item(self, client: AsyncClient, authenticated_client: AsyncClient):
        """Un item public est accessible sans auth."""
        # Créer un item public
        create_response = await authenticated_client.post("/api/items", json={
            "title": "Item Public",
            "is_public": True
        })
        item_id = create_response.json()["id"]
        
        # Récupérer sans auth
        response = await client.get(f"/api/items/{item_id}")
        
        assert response.status_code == 200
        assert response.json()["title"] == "Item Public"
    
    @pytest.mark.asyncio
    async def test_get_private_item_requires_auth(self, client: AsyncClient, authenticated_client: AsyncClient):
        """Un item privé requiert une auth."""
        # Créer un item privé
        create_response = await authenticated_client.post("/api/items", json={
            "title": "Item Privé",
            "is_public": False
        })
        item_id = create_response.json()["id"]
        
        # Récupérer sans auth
        response = await client.get(f"/api/items/{item_id}")
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_update_own_item(self, authenticated_client: AsyncClient):
        """Un user peut modifier son propre item."""
        # Créer
        create_response = await authenticated_client.post("/api/items", json={
            "title": "Original",
            "is_public": False
        })
        item_id = create_response.json()["id"]
        
        # Modifier
        response = await authenticated_client.put(f"/api/items/{item_id}", json={
            "title": "Modifié"
        })
        
        assert response.status_code == 200
        assert response.json()["title"] == "Modifié"
    
    @pytest.mark.asyncio
    async def test_delete_own_item(self, authenticated_client: AsyncClient):
        """Un user peut supprimer son propre item."""
        # Créer
        create_response = await authenticated_client.post("/api/items", json={
            "title": "À supprimer",
            "is_public": False
        })
        item_id = create_response.json()["id"]
        
        # Supprimer
        response = await authenticated_client.delete(f"/api/items/{item_id}")
        
        assert response.status_code == 200
        
        # Vérifier que supprimé
        get_response = await authenticated_client.get(f"/api/items/{item_id}")
        assert get_response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_admin_can_modify_any_item(self, authenticated_client: AsyncClient, admin_client: AsyncClient):
        """Un admin peut modifier n'importe quel item."""
        # User crée un item
        create_response = await authenticated_client.post("/api/items", json={
            "title": "Item de User",
            "is_public": False
        })
        item_id = create_response.json()["id"]
        
        # Admin modifie
        response = await admin_client.put(f"/api/items/{item_id}", json={
            "title": "Modifié par Admin"
        })
        
        assert response.status_code == 200
        assert response.json()["title"] == "Modifié par Admin"


class TestItemsValidation:
    """Tests de validation des données Items."""
    
    @pytest.mark.asyncio
    async def test_create_item_empty_title(self, authenticated_client: AsyncClient):
        """Le titre ne peut pas être vide."""
        response = await authenticated_client.post("/api/items", json={
            "title": "",
            "is_public": True
        })
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_create_item_title_too_long(self, authenticated_client: AsyncClient):
        """Le titre ne peut pas dépasser 255 caractères."""
        response = await authenticated_client.post("/api/items", json={
            "title": "x" * 300,
            "is_public": True
        })
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_item(self, authenticated_client: AsyncClient):
        """Un item inexistant retourne 404."""
        response = await authenticated_client.get("/api/items/99999")
        
        assert response.status_code == 404
