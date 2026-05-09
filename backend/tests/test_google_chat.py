"""Tests for Google Chat API client (TDD RED phase)."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.google_chat import GoogleChatClient, IncidentCard


class TestGoogleChatClient:
    """Test suite for GoogleChatClient."""

    @pytest.fixture
    def client(self):
        """Create a GoogleChatClient with mocked config."""
        with patch("app.services.google_chat.GoogleChatClient.__init__", return_value=None):
            client = GoogleChatClient()
            client.space_id = "spaces/test-space-123"
            client.credentials = MagicMock()
            client._get_access_token = AsyncMock(return_value="test-token-456")
            return client

    @pytest.mark.asyncio
    async def test_send_message_calls_correct_api_endpoint(self, client):
        """RED: Test send_message sends POST to correct Google Chat API URL."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"name": "spaces/test/messages/123"})
            await client.send_message("spaces/test-space-123", "Test alert message")
            
            mock_post.assert_called_once_with(
                "https://chat.googleapis.com/v1/spaces/test-space-123/messages",
                headers={"Authorization": "Bearer test-token-456", "Content-Type": "application/json"},
                json={"text": "Test alert message"}
            )

    @pytest.mark.asyncio
    async def test_create_incident_card_generates_valid_card(self, client):
        """RED: Test create_incident_card returns a valid IncidentCard with required fields."""
        incident = MagicMock()
        incident.id = "INC-12345678"
        incident.title = "Index logs-red is RED"
        incident.severity.value = "critical"
        incident.to_dict.return_value = {"id": "INC-12345678", "title": "Index logs-red is RED"}
        
        card = await client.create_incident_card(incident)
        
        assert isinstance(card, IncidentCard)
        assert card.incident_id == "INC-12345678"
        assert "Approve Fix" in card.card_json
        assert "INC-12345678" in card.card_json
        assert "CRITICAL" in card.card_json  # severity is uppercased in card

    @pytest.mark.asyncio
    async def test_handle_webhook_callback_processes_approve_action(self, client):
        """RED: Test handle_webhook_callback processes 'approve_fix' action correctly."""
        event = {
            "type": "CARD_CLICKED",
            "action": {
                "actionId": "approve_fix",
                "parameters": [{"key": "incident_id", "value": "INC-12345678"}]
            }
        }
        
        result = await client.handle_webhook_callback(event)
        
        assert result["action"] == "approve_fix"
        assert result["incident_id"] == "INC-12345678"
        assert result["status"] == "processed"


class TestIncidentCard:
    """Test suite for IncidentCard data class."""

    def test_incident_card_has_required_fields(self):
        """RED: Test IncidentCard has incident_id, card_json, and action buttons."""
        card = IncidentCard(
            incident_id="INC-87654321",
            card_json='{"text": "test card"}',
            action_buttons=[{"text": "Approve Fix", "actionId": "approve_fix"}]
        )
        
        assert card.incident_id == "INC-87654321"
        assert "test card" in card.card_json
        assert len(card.action_buttons) == 1
        assert card.action_buttons[0]["text"] == "Approve Fix"
