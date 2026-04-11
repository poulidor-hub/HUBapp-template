"""
Tests des endpoints de tests des services.

Ces tests vérifient :
- L'endpoint de test complet des services
- Les endpoints de test individuels (hub, slug, m2m, sse, backup)
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone


class TestAllServicesEndpoint:
    """Tests de l'endpoint /api/tests/services."""
    
    @pytest.mark.asyncio
    async def test_test_services_requires_auth(self, client: AsyncClient):
        """L'endpoint de test nécessite une authentification."""
        response = await client.get("/api/tests/services")
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_test_services_returns_all_tests(self, authenticated_client: AsyncClient):
        """L'endpoint retourne les résultats de tous les tests."""
        with patch('routes.tests.hub_client') as mock_hub_client:
            # Mock des méthodes du hub_client
            mock_hub_client.is_registered = True
            mock_hub_client.credentials = MagicMock(
                client_id="test-client-id",
                access_token="test-token",
                token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
            )
            mock_hub_client.ensure_valid_credentials = AsyncMock(return_value=True)
            mock_hub_client.get_m2m_token = AsyncMock(return_value="test-m2m-token")
            mock_hub_client.list_discovered_services = AsyncMock(return_value=[])
            mock_hub_client._discovered_services_fetched_at = datetime.now(timezone.utc)
            mock_hub_client._resync_count = 0
            
            response = await authenticated_client.get("/api/tests/services")
        
        assert response.status_code == 200
        data = response.json()
        
        # Vérifier la structure de la réponse
        assert "timestamp" in data
        assert "app_slug" in data
        assert "app_version" in data
        assert "overall_success" in data
        assert "total_duration_ms" in data
        assert "tests" in data
        assert "summary" in data
        
        # Vérifier qu'il y a 5 tests
        assert len(data["tests"]) == 5
        
        # Vérifier les noms des tests
        test_names = [t["name"] for t in data["tests"]]
        assert "Hub Connection" in test_names
        assert "X-Slug Recovery" in test_names
        assert "M2M Service" in test_names
        assert "SSE Stream" in test_names
        assert "Backup System" in test_names
        
        # Vérifier le résumé
        assert "total_tests" in data["summary"]
        assert data["summary"]["total_tests"] == 5


class TestHubConnectionEndpoint:
    """Tests de l'endpoint /api/tests/hub-connection."""
    
    @pytest.mark.asyncio
    async def test_hub_connection_requires_auth(self, client: AsyncClient):
        """L'endpoint nécessite une authentification."""
        response = await client.get("/api/tests/hub-connection")
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_hub_connection_returns_result(self, authenticated_client: AsyncClient):
        """L'endpoint retourne un résultat de test."""
        with patch('routes.tests.hub_client') as mock_hub_client:
            mock_hub_client.is_registered = True
            mock_hub_client.credentials = MagicMock(client_id="test-client-id")
            mock_hub_client.ensure_valid_credentials = AsyncMock(return_value=True)
            
            response = await authenticated_client.get("/api/tests/hub-connection")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "Hub Connection"
        assert "success" in data
        assert "duration_ms" in data
        assert "message" in data
        assert "details" in data


class TestSlugRecoveryEndpoint:
    """Tests de l'endpoint /api/tests/slug-recovery."""
    
    @pytest.mark.asyncio
    async def test_slug_recovery_requires_auth(self, client: AsyncClient):
        """L'endpoint nécessite une authentification."""
        response = await client.get("/api/tests/slug-recovery")
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_slug_recovery_returns_user_info(self, authenticated_client: AsyncClient):
        """L'endpoint retourne les informations X-Slug de l'utilisateur."""
        response = await authenticated_client.get("/api/tests/slug-recovery")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "X-Slug Recovery"
        assert data["success"] == True
        assert "details" in data
        assert "username" in data["details"]
        assert "app_role" in data["details"]


class TestM2MServiceEndpoint:
    """Tests de l'endpoint /api/tests/m2m."""
    
    @pytest.mark.asyncio
    async def test_m2m_requires_auth(self, client: AsyncClient):
        """L'endpoint nécessite une authentification."""
        response = await client.get("/api/tests/m2m")
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_m2m_returns_result(self, authenticated_client: AsyncClient):
        """L'endpoint retourne un résultat de test M2M."""
        with patch('routes.tests.hub_client') as mock_hub_client:
            mock_hub_client.get_m2m_token = AsyncMock(return_value="test-m2m-token")
            mock_hub_client.list_discovered_services = AsyncMock(return_value=[])
            mock_hub_client.credentials = MagicMock(
                client_id="test-client-id",
                access_token="test-token",
                token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
            )
            mock_hub_client._resync_count = 0
            
            response = await authenticated_client.get("/api/tests/m2m")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "M2M Service"
        assert "success" in data
        assert "details" in data
        assert "has_m2m_token" in data["details"]


class TestSSEEndpoint:
    """Tests de l'endpoint /api/tests/sse."""
    
    @pytest.mark.asyncio
    async def test_sse_requires_auth(self, client: AsyncClient):
        """L'endpoint nécessite une authentification."""
        response = await client.get("/api/tests/sse")
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_sse_returns_result(self, authenticated_client: AsyncClient):
        """L'endpoint retourne un résultat de test SSE."""
        response = await authenticated_client.get("/api/tests/sse")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "SSE Stream"
        assert "success" in data
        assert "details" in data
        assert "sse_url" in data["details"]


class TestBackupEndpoint:
    """Tests de l'endpoint /api/tests/backup."""
    
    @pytest.mark.asyncio
    async def test_backup_requires_auth(self, client: AsyncClient):
        """L'endpoint nécessite une authentification."""
        response = await client.get("/api/tests/backup")
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_backup_returns_result(self, authenticated_client: AsyncClient):
        """L'endpoint retourne un résultat de test backup."""
        with patch('routes.tests.hub_client') as mock_hub_client:
            mock_hub_client.is_registered = True
            mock_hub_client.get_m2m_token = AsyncMock(return_value="test-m2m-token")
            
            response = await authenticated_client.get("/api/tests/backup")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "Backup System"
        assert "success" in data
        assert "details" in data
        assert "local_data" in data["details"]


class TestSendTestMessageEndpoint:
    """Tests de l'endpoint /api/tests/messages/send."""

    @pytest.mark.asyncio
    async def test_send_test_message_requires_auth(self, client: AsyncClient):
        """L'endpoint nécessite une authentification."""
        response = await client.post("/api/tests/messages/send")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_send_test_message_requires_admin_role(self, authenticated_client: AsyncClient):
        """L'endpoint est réservé aux admins."""
        response = await authenticated_client.post("/api/tests/messages/send")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_send_test_message_defaults_to_current_admin(self, admin_client: AsyncClient):
        """Sans payload, le message est envoyé à l'admin courant."""
        mock_send = AsyncMock(return_value={"status": "sent", "queued": 1})

        with patch("routes.tests.hub_client.send_user_message", new=mock_send):
            response = await admin_client.post("/api/tests/messages/send")

        assert response.status_code == 200
        data = response.json()

        assert data["message"] == "Message de test envoye avec succes"
        assert data["sent_by"] == "admin"
        assert data["target_usernames"] == ["admin"]
        assert data["title"] == "Message de test HUB"
        assert data["priority"] == "info"
        assert data["hub_response"] == {"status": "sent", "queued": 1}

        mock_send.assert_awaited_once()
        assert mock_send.await_args.kwargs["target_usernames"] == ["admin"]
        assert mock_send.await_args.kwargs["title"] == "Message de test HUB"
        assert mock_send.await_args.kwargs["priority"] == "info"

    @pytest.mark.asyncio
    async def test_send_test_message_normalizes_payload(self, admin_client: AsyncClient):
        """L'endpoint nettoie les champs texte et déduplique les destinataires."""
        mock_send = AsyncMock(return_value={"status": "sent", "queued": 2})

        with patch("routes.tests.hub_client.send_user_message", new=mock_send):
            response = await admin_client.post(
                "/api/tests/messages/send",
                json={
                    "target_usernames": [" alice ", "alice", "bob", "  "],
                    "title": "  Validation requise  ",
                    "body": "  Merci de verifier le dossier.  ",
                    "priority": "warning",
                    "action_url": "  https://example.test/items/12  ",
                    "action_label": "  Ouvrir  ",
                    "expires_at": " 2026-04-30T18:00:00Z "
                }
            )

        assert response.status_code == 200
        data = response.json()

        assert data["target_usernames"] == ["alice", "bob"]
        assert data["title"] == "Validation requise"
        assert data["priority"] == "warning"

        assert mock_send.await_args.kwargs == {
            "target_usernames": ["alice", "bob"],
            "title": "Validation requise",
            "body": "Merci de verifier le dossier.",
            "priority": "warning",
            "action_url": "https://example.test/items/12",
            "action_label": "Ouvrir",
            "expires_at": "2026-04-30T18:00:00Z"
        }

    @pytest.mark.asyncio
    async def test_send_test_message_returns_502_when_hub_fails(self, admin_client: AsyncClient):
        """Une erreur Hub est propagée en 502."""
        with patch(
            "routes.tests.hub_client.send_user_message",
            new=AsyncMock(return_value={"error": "hub indisponible"})
        ):
            response = await admin_client.post(
                "/api/tests/messages/send",
                json={"target_usernames": ["alice"], "title": "Test Hub"}
            )

        assert response.status_code == 502
        assert response.json()["detail"] == "hub indisponible"


class TestSSEDemoEndpoint:
    """Tests de l'endpoint /api/tests/sse/demo."""
    
    @pytest.mark.asyncio
    async def test_sse_demo_requires_auth(self, client: AsyncClient):
        """L'endpoint nécessite une authentification."""
        response = await client.get("/api/tests/sse/demo")
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_sse_demo_returns_stream(self, authenticated_client: AsyncClient):
        """L'endpoint retourne un flux SSE."""
        response = await authenticated_client.get("/api/tests/sse/demo")
        
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
