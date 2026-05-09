"""
War Room API — Enhanced with async support and progress streaming.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.services.war_room import AsyncWarRoom, WarRoom
from app.services.mcp_client import ElasticMCPClient
from app.core.config import settings
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Store active war rooms
_active_war_rooms: dict = {}
_active_async_war_rooms: dict = {}


def _get_mcp_client() -> ElasticMCPClient:
    """Create an MCP client from settings with direct ES fallback."""
    base_url = settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0] if "/mcp" in settings.MCP_SERVER_URL else settings.MCP_SERVER_URL
    return ElasticMCPClient(
        base_url=base_url,
        api_key=settings.ES_API_KEY or None,
        es_url=settings.ES_URL if hasattr(settings, 'ES_URL') and settings.ES_URL else "http://localhost:9200",
    )


@router.post("/warroom/start")
async def start_war_room(incident_id: str, async_mode: bool = True):
    """
    Start a war room for an incident — 3 agents collaborate.

    Args:
        incident_id: The incident to investigate
        async_mode: If True, uses concurrent async agents (recommended)
    """
    if incident_id in _active_async_war_rooms:
        raise HTTPException(status_code=400, detail="War room already active for this incident")

    if async_mode:
        mcp_client = _get_mcp_client()
        war_room = AsyncWarRoom(incident_id, mcp_client=mcp_client)

        # Register progress callback for logging
        def on_progress(update):
            logger.info(f"WarRoom [{incident_id}] progress: {update.get('phase', 'unknown')} - {update.get('status', '')}")

        war_room.on_progress(on_progress)

        # Run in background task
        import asyncio
        task = asyncio.create_task(war_room.start(timeout_seconds=120))

        _active_async_war_rooms[incident_id] = {
            "war_room": war_room,
            "task": task,
        }

        return {
            "status": "started",
            "mode": "async",
            "incident_id": incident_id,
        }
    else:
        # Legacy sync mode
        if incident_id in _active_war_rooms:
            raise HTTPException(status_code=400, detail="War room already active")

        war_room = WarRoom(incident_id)
        war_room.start()
        _active_war_rooms[incident_id] = war_room

        return {
            "status": "started",
            "mode": "sync",
            "incident_id": incident_id,
        }


@router.get("/warroom/status")
async def get_war_room_status(incident_id: str = None):
    """Get war room status (async or sync)."""
    result = {}

    if incident_id:
        # Check async rooms first
        if incident_id in _active_async_war_rooms:
            entry = _active_async_war_rooms[incident_id]
            war_room = entry["war_room"]
            result = war_room.get_result() if entry["task"].done() else war_room.get_status()
            result["mode"] = "async"
        elif incident_id in _active_war_rooms:
            result = _active_war_rooms[incident_id].get_status()
            result["mode"] = "sync"
        else:
            raise HTTPException(status_code=404, detail="War room not found")
    else:
        # Return all active war rooms
        all_rooms = {}
        for inc_id, entry in _active_async_war_rooms.items():
            all_rooms[inc_id] = entry["war_room"].get_result() if entry["task"].done() else entry["war_room"].get_status()
            all_rooms[inc_id]["mode"] = "async"
        for inc_id, wr in _active_war_rooms.items():
            all_rooms[inc_id] = wr.get_status()
            all_rooms[inc_id]["mode"] = "sync"
        result = all_rooms

    return result


@router.get("/warroom/log")
async def get_war_room_log(incident_id: str):
    """Get full conversation log from war room."""
    if incident_id in _active_async_war_rooms:
        return {
            "incident_id": incident_id,
            "log": _active_async_war_rooms[incident_id]["war_room"].get_conversation_log(),
            "mode": "async",
        }
    elif incident_id in _active_war_rooms:
        return {
            "incident_id": incident_id,
            "log": _active_war_rooms[incident_id].get_conversation_log(),
            "mode": "sync",
        }
    raise HTTPException(status_code=404, detail="War room not found")


@router.delete("/warroom/{incident_id}")
async def stop_war_room(incident_id: str):
    """Stop and clean up a war room."""
    if incident_id in _active_async_war_rooms:
        entry = _active_async_war_rooms.pop(incident_id)
        await entry["war_room"].cancel()
        if not entry["task"].done():
            entry["task"].cancel()
        return {"status": "stopped", "mode": "async"}

    if incident_id in _active_war_rooms:
        _active_war_rooms.pop(incident_id)
        return {"status": "stopped", "mode": "sync"}

    raise HTTPException(status_code=404, detail="War room not found")


@router.websocket("/ws/warroom/{incident_id}")
async def warroom_websocket(websocket: WebSocket, incident_id: str):
    """WebSocket endpoint for real-time war room progress streaming."""
    await websocket.accept()

    if incident_id not in _active_async_war_rooms:
        await websocket.close(code=1008, reason="War room not found")
        return

    entry = _active_async_war_rooms[incident_id]
    war_room = entry["war_room"]

    # Progress callback to push updates via WebSocket
    async def ws_callback(update: dict):
        try:
            await websocket.send_text(json.dumps(update))
        except WebSocketDisconnect:
            pass

    war_room.on_progress(ws_callback)

    try:
        # Send current status immediately
        await websocket.send_text(json.dumps({
            "type": "status",
            "data": war_room.get_result() if entry["task"].done() else war_room.get_status(),
        }))

        # Keep connection alive and send final result when done
        while not entry["task"].done():
            await asyncio.sleep(1)

        result = entry["task"].result()
        await websocket.send_text(json.dumps({
            "type": "completed",
            "data": result,
        }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WarRoom WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass


@router.get("/warroom/health")
async def warroom_health():
    """Quick health check for war room capability."""
    active_count = len(_active_async_war_rooms) + len(_active_war_rooms)
    return {
        "status": "ready" if active_count < 5 else "busy",
        "active_war_rooms": active_count,
        "max_concurrent": 10,
    }