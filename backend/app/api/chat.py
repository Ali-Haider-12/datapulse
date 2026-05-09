"""
Chat API — Streaming LLM responses with session management and caching.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request
from app.services.mcp_client import ElasticMCPClient
from app.services.llm_provider import LLMProvider
from app.services.cache import cached
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_chat_llm(app):
    """Get LLM provider from app state, or create a fallback."""
    if hasattr(app.state, 'llm_provider'):
        return app.state.llm_provider
    # Fallback: create one (for testing without lifespan)
    from app.services.llm_provider import LLMProvider
    return LLMProvider()


async def get_mcp_client(app) -> Optional[ElasticMCPClient]:
    """Get MCP client from app state."""
    if hasattr(app.state, 'mcp_client'):
        return app.state.mcp_client
    return None


@router.get("/sessions")
async def list_sessions(request: Request):
    """List available chat sessions."""
    sm = getattr(request.app.state, 'session_manager', None)
    if sm:
        return {"sessions": [s.session_id for s in sm.sessions.values()]}
    return {"sessions": []}


@router.post("/session")
async def create_session(request: Request):
    """Create a new chat session."""
    sm = getattr(request.app.state, 'session_manager', None)
    if sm:
        session = await sm.create_session(user_id="web-user")
        return {
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat(),
            "message_count": 0,
        }
    return {"session_id": "default", "created_at": datetime.now(timezone.utc).isoformat(), "message_count": 0}


@router.get("/session/{session_id}/history")
async def get_history(request: Request, session_id: str):
    """Get message history for a session."""
    sm = getattr(request.app.state, 'session_manager', None)
    if sm and session_id in sm.sessions:
        history = await sm.get_session_history(session_id)
        return {"history": history}
    return {"history": []}


@router.post("/query")
async def chat_query(request: Request):
    """Non-streaming chat endpoint — useful for programmatic access."""
    from app.models.schemas import ChatMessage

    body = await request.json()
    message = body.get("message", "")
    session_id = body.get("session_id")
    mode = body.get("mode", "chat")
    max_tokens = body.get("max_tokens", 500)

    if not message:
        raise HTTPException(status_code=400, detail="Message required")

    # Get LLM
    llm = await get_chat_llm(request.app)
    mcp = await get_mcp_client(request.app)

    # Build context from session history
    context = ""
    if mcp:
        try:
            from app.services.cache import get_cache
            cache = get_cache()
            cache_key = f"chat:{hash(message)}"
            cached_resp = await cache.get(cache_key)
            if cached_resp:
                return {"response": cached_resp, "cached": True}
        except Exception:
            pass

    # Build prompt based on mode
    if mode == "chat":
        prompt = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}] User: {message}"
    elif mode == "analyze":
        prompt = f"Analyze this Elasticsearch situation: {message}. Provide structured JSON with root_cause, severity, and recommendation fields."
    elif mode == "remediate":
        prompt = f"Given this ES issue: {message}, provide step-by-step remediation as JSON with actions array."
    else:
        prompt = message

    # Stream response
    response_text = ""
    async for chunk in llm.chat(prompt, history=[]):
        if chunk.get("type") == "text":
            response_text += chunk.get("content", "")

    # Cache result
    if mcp and response_text:
        try:
            await cache.set(cache_key, response_text, ttl=60)
        except Exception:
            pass

    # Log to session
    if session_id and hasattr(request.app.state, 'session_manager'):
        sm = request.app.state.session_manager
        if session_id in sm.sessions:
            await sm.add_message(session_id, "user", message)
            await sm.add_message(session_id, "assistant", response_text)

    return {
        "response": response_text,
        "cached": False,
        "mode": mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── WebSocket chat ──
connected_clients: set = set()


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    logger.debug(f"Chat WS client connected. Total: {len(connected_clients)}")

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            session_id = data.get("session_id")
            mode = data.get("mode", "chat")

            if not message:
                continue

            llm = await get_chat_llm(websocket.app)

            # Build prompt
            prompt = f"[{datetime.now(timezone.utc).strftime('%H:%M')}] {message}"

            # Stream response back
            response_chunks = []
            async for chunk in llm.chat(prompt, history=[]):
                if chunk.get("type") == "text":
                    text = chunk.get("content", "")
                    response_chunks.append(text)
                    await websocket.send_json({
                        "type": "stream",
                        "content": text,
                    })

            response_text = "".join(response_chunks)

            # Log to session
            if session_id and hasattr(websocket.app.state, 'session_manager'):
                sm = websocket.app.state.session_manager
                if session_id in sm.sessions:
                    await sm.add_message(session_id, "user", message)
                    await sm.add_message(session_id, "assistant", response_text)

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(websocket)
        logger.debug(f"Chat WS client disconnected. Total: {len(connected_clients)}")