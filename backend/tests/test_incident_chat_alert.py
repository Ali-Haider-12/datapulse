"""Tests for incident alert to Google Chat (TDD RED phase)."""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.incident_response import IncidentResponseEngine, Incident, IncidentSeverity
from app.services.google_chat import GoogleChatClient


class TestIncidentChatAlert:
    """Test incident detection triggers Google Chat alert."""

    @pytest.mark.asyncio
    async def test_incident_detect_sends_chat_alert(self):
        """RED: Test that detecting an incident sends a Google Chat message."""
        mock_mcp = AsyncMock()
        mock_mcp.list_indices.return_value = {
            "indices": [{"name": "logs-red", "health": "red", "docs": 100}]
        }
        mock_mcp.esql.return_value = {"values": []}
        
        # Mock GoogleChatClient
        with patch("app.services.incident_response.GoogleChatClient") as MockChatClient:
            mock_client = MockChatClient.return_value
            mock_client.space_id = "spaces/test-space"
            mock_client.send_card = AsyncMock()
            # Mock create_incident_card to return a proper IncidentCard
            mock_card = MagicMock()
            mock_card.incident_id = "INC-12345678"
            mock_card.card_json = '{"text": "test", "buttons": ["Approve Fix"]}'
            mock_client.create_incident_card = AsyncMock(return_value=mock_card)
            
            # Create incident response engine
            engine = IncidentResponseEngine(mock_mcp)
            incidents = await engine.detect_incidents()
            
            # Verify Google Chat client was called
            assert len(incidents) > 0
            mock_client.send_card.assert_called_once()
            
            # Verify the card sent includes incident details
            call_args = mock_client.send_card.call_args
            space_id = call_args[0][0]
            card = call_args[0][1]
            # Verify card has Approve Fix button
            assert "Approve Fix" in card.card_json

    @pytest.mark.asyncio
    async def test_no_incident_no_chat_alert(self):
        """RED: Test that no incidents means no Google Chat alert."""
        mock_mcp = AsyncMock()
        mock_mcp.list_indices.return_value = {
            "indices": [{"name": "logs-green", "health": "green", "docs": 100}]
        }
        mock_mcp.esql.return_value = {"values": []}
        
        with patch("app.services.incident_response.GoogleChatClient") as MockChatClient:
            mock_client = MockChatClient.return_value
            mock_client.send_card = AsyncMock()
            
            engine = IncidentResponseEngine(mock_mcp)
            incidents = await engine.detect_incidents()
            
            assert len(incidents) == 0
            mock_client.send_card.assert_not_called()
