"""Tests for Google Chat webhook approval (TDD RED phase)."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.google_chat import GoogleChatClient

client = TestClient(app)


class TestChatWebhook:
    """Test suite for chat webhook endpoint."""

    @pytest.mark.asyncio
    async def test_webhook_approve_calls_incident_approve(self):
        """RED: Test that webhook approve action calls incident approve endpoint."""
        with patch("app.api.chat_webhook.IncidentResponseEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.approve_action = MagicMock(return_value=True)
            
            with patch("app.api.chat_webhook.GoogleChatClient") as MockChatClient:
                mock_chat = MockChatClient.return_value
                mock_chat.send_message = AsyncMock()
                
                # Simulate Google Chat callback
                callback_event = {
                    "type": "CARD_CLICKED",
                    "action": {
                        "actionId": "approve_fix",
                        "parameters": [{"key": "incident_id", "value": "INC-12345678"}]
                    }
                }
                
                response = client.post(
                    "/api/chat_webhook/approve",
                    json=callback_event
                )
                
                assert response.status_code == 200
                assert response.json()["status"] == "approved"
                
                # Verify incident approve was called
                mock_engine.approve_action.assert_called_once_with("INC-12345678", "approve_fix")
                
                # Verify confirmation message sent
                mock_chat.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_invalid_action_returns_error(self):
        """RED: Test that invalid action returns error."""
        callback_event = {
            "type": "CARD_CLICKED",
            "action": {
                "actionId": "invalid_action",
                "parameters": []
            }
        }
        
        response = client.post(
            "/api/chat_webhook/approve",
            json=callback_event
        )
        
        assert response.status_code == 400
        assert "detail" in response.json()