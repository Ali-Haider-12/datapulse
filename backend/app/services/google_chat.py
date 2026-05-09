"""Google Chat API client for DataPulse incident alerts."""
import httpx
import json
from dataclasses import dataclass
from typing import Dict, Any, Optional
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from app.core.config import settings


@dataclass
class IncidentCard:
    """Data class for Google Chat interactive incident card."""
    incident_id: str
    card_json: str
    action_buttons: list


class GoogleChatClient:
    """Client for sending messages and cards to Google Chat."""

    def __init__(self):
        self.space_id = settings.GOOGLE_CHAT_SPACE_ID
        self.credentials = None
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            self.credentials = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_APPLICATION_CREDENTIALS,
                scopes=["https://www.googleapis.com/auth/chat.bot"]
            )

    async def _get_access_token(self) -> str:
        """Get OAuth2 access token from service account credentials."""
        if not self.credentials:
            return "test-token-456"  # For testing
        self.credentials.refresh(Request())
        return self.credentials.token

    async def send_message(self, space_id: str, text: str) -> Dict[str, Any]:
        """Send plain text message to Google Chat space."""
        token = await self._get_access_token()
        url = f"https://chat.googleapis.com/v1/{space_id}/messages"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={"text": text}
            )
            response.raise_for_status()
            return response.json()

    async def create_incident_card(self, incident: Any) -> IncidentCard:
        """Create interactive card for incident with Approve Fix button."""
        webhook_url = f"https://{settings.PROJECT_NAME.lower()}.example.com/api/chat_webhook/approve"
        
        card_json = json.dumps({
            "text": f"🚨 **Incident Alert**",
            "cardsV2": [{
                "card": {
                    "header": {
                        "title": f"Incident {incident.id}",
                        "subtitle": incident.title,
                        "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/googledotcom/chat/v12/192px.svg"
                    },
                    "sections": [{
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": f"Severity: **{incident.severity.value.upper()}**\nIncident ID: {incident.id}"
                                }
                            },
                            {
                                "buttonList": {
                                    "buttons": [{
                                        "text": "Approve Fix",
                                        "onClick": {
                                            "action": {
                                                "function": "approve_fix",
                                                "parameters": [{
                                                    "key": "incident_id",
                                                    "value": incident.id
                                                }],
                                                "loadIndicator": "LoadIndicator.SPINNER"
                                            }
                                        }
                                    }]
                                }
                            }
                        ]
                    }]
                }
            }]
        })
        
        return IncidentCard(
            incident_id=incident.id,
            card_json=card_json,
            action_buttons=[{"text": "Approve Fix", "actionId": "approve_fix"}]
        )

    async def handle_webhook_callback(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process Google Chat button click callbacks."""
        if event.get("type") != "CARD_CLICKED":
            return {"status": "ignored", "reason": "not a card click event"}
        
        action = event.get("action", {})
        action_id = action.get("actionId", "")
        parameters = action.get("parameters", [])
        
        incident_id = next(
            (p["value"] for p in parameters if p["key"] == "incident_id"),
            None
        )
        
        return {
            "action": action_id,
            "incident_id": incident_id,
            "status": "processed"
        }

    async def send_card(self, space_id: str, card: IncidentCard) -> Dict[str, Any]:
        """Send interactive card to Google Chat space."""
        token = await self._get_access_token()
        url = f"https://chat.googleapis.com/v1/{space_id}/messages"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=json.loads(card.card_json)
            )
            response.raise_for_status()
            return response.json()
