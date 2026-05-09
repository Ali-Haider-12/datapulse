"""
Chat Webhook API — Incoming webhook integration for Slack/Teams/etc.
"""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat")
async def chat_webhook(req: Request):
    """
    Incoming chat webhook — process messages from external services.

    Supports Slack-compatible webhook format.
    """
    body = await req.json()

    # Slack challenge verification
    challenge = body.get("challenge")
    if challenge:
        return PlainTextResponse(challenge)

    # Get message text
    text = ""
    if "event" in body:
        text = body["event"].get("text", "")
    elif "text" in body:
        text = body["text"]

    if not text:
        return {"status": "error", "message": "No text provided"}

    # Route to chat processing
    from app.services.llm_provider import LLMProvider
    provider = LLMProvider()

    response_text = ""
    async for chunk in provider.chat(text):
        if chunk.get("type") == "text":
            response_text += chunk.get("content", "")

    return {
        "response_type": "in_channel",
        "text": response_text[:3000],  # Slack message limit
    }


@router.post("/alert")
async def alert_webhook(req: Request):
    """
    Incoming alert webhook — receive alerts from monitoring tools.

    Accepts alerts in generic format and forwards to DataPulse alert system.
    """
    body = await req.json()
    logger.info(f"Alert webhook received: {body}")

    # Extract alert fields (support multiple formats)
    alert_data = {
        "title": body.get("title") or body.get("summary") or body.get("alertname") or "Unknown Alert",
        "severity": body.get("severity", body.get("priority", "warning")).lower(),
        "message": body.get("message") or body.get("description") or body.get("text", ""),
        "source": body.get("source", body.get("service", "webhook")),
        "timestamp": body.get("timestamp") or body.get("@timestamp", ""),
        "labels": body.get("labels", {}),
    }

    # Broadcast to WebSocket clients
    try:
        from app.main import alert_manager
        await alert_manager.broadcast({
            "type": "webhook_alert",
            "alert": alert_data,
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast alert: {e}")

    return {"status": "received", "alert": alert_data}


@router.post("/es")
async def es_webhook(req: Request):
    """
    Elasticsearch webhook — process ES alerts/notifications.
    """
    body = await req.json()
    logger.info(f"ES webhook received: {body}")

    # Transform ES notification to DataPulse format
    alert_data = {
        "title": body.get("type", "ES Alert"),
        "severity": "critical" if body.get("severity", "").lower() in ("critical", "red") else "warning",
        "message": body.get("message", str(body)),
        "source": "elasticsearch",
    }

    try:
        from app.main import alert_manager
        await alert_manager.broadcast({
            "type": "es_alert",
            "alert": alert_data,
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast ES alert: {e}")

    return {"status": "received"}