"""
DataPulse API Entry Point — FastAPI application with all routes and services.
"""

from contextlib import asynccontextmanager
import asyncio
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.llm_provider import LLMProvider
from app.services.cache import TTLCache, get_cache, _in_memory_cache
from app.services.session_manager import SessionManager
from app.services.state_manager import StateManager
from app.services.war_room import AsyncWarRoom
from app.services.health_analyzer import HealthAnalyzer
from app.services.impact_calculator import ImpactCalculator
from app.services.postmortem import PostmortemGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup shared services."""
    logger.info("🚀 Initializing DataPulse services...")

    # LLM Provider — multi-tier fallback chain
    llm_provider = LLMProvider()
    logger.info("✓ LLM Provider initialized (Gemini → OpenRouter → Deepseek → Mock)")

    # MCP Client for Elasticsearch
    mcp_client = ElasticMCPClient(
        base_url=settings.MCP_SERVER_URL,
        api_key=settings.MCP_API_KEY,
        es_url=settings.ES_URL,
    )
    logger.info(f"✓ MCP Client initialized → {settings.ES_URL}")

    # Cache layer
    cache = TTLCache(default_ttl=120)

    # Session Manager
    session_manager = SessionManager(
        storage_path=os.environ.get("SESSIONS_DIR", "/tmp/datapulse_sessions"),
        max_history=50,
    )
    await session_manager.start()
    logger.info("✓ Session Manager started")

    # State Manager
    state_manager = StateManager(state_dir=os.environ.get("STATE_DIR", "/tmp/datapulse_state"))
    await state_manager.start()
    logger.info("✓ State Manager started")

    # Health Analyzer
    health_analyzer = HealthAnalyzer(mcp_client)

    # Impact Calculator
    impact_calculator = ImpactCalculator(mcp_client)

    # Postmortem Generator
    postmortem_gen = PostmortemGenerator(mcp_client, llm_provider)

    # War Rooms registry
    active_war_rooms: dict[str, AsyncWarRoom] = {}

    # Store in app state
    app.state.llm_provider = llm_provider
    app.state.mcp_client = mcp_client
    app.state.cache = cache
    app.state.session_manager = session_manager
    app.state.state_manager = state_manager
    app.state.health_analyzer = health_analyzer
    app.state.impact_calculator = impact_calculator
    app.state.postmortem_gen = postmortem_gen
    app.state.active_war_rooms = active_war_rooms

    # Start health monitoring background task
    async def health_monitor():
        """Periodic health check loop."""
        while True:
            try:
                await health_analyzer.run_analysis(mcp_client)
            except Exception as e:
                logger.warning(f"Health monitor error: {e}")
            await asyncio.sleep(60)  # Every 60 seconds

    app.state.health_monitor_task = asyncio.create_task(health_monitor())
    logger.info("✓ Health monitor started")

    yield

    # Cleanup
    logger.info("Shutting down DataPulse services...")
    app.state.health_monitor_task.cancel()
    try:
        app.state.health_monitor_task.result()
    except (asyncio.CancelledError, Exception):
        pass
    await session_manager.stop()
    await state_manager.stop()
    await mcp_client.close()
    await app.state.cache.close()
    logger.info("👋 DataPulse shutdown complete")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-Powered Elasticsearch Monitoring & Incident Response",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Import routes ──
from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.warroom import router as warroom_router
from app.api.impact import router as impact_router
from app.api.alerts import router as alerts_router
from app.api.incidents import router as incidents_router
from app.api.patrol import router as patrol_router
from app.api.voice import router as voice_router
from app.api.chat_webhook import router as webhook_router

app.include_router(health_router, prefix="/api/health", tags=["health"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(warroom_router, prefix="/api/warroom", tags=["warroom"])
app.include_router(impact_router, prefix="/api", tags=["impact"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["alerts"])
app.include_router(incidents_router, prefix="/api/incidents", tags=["incidents"])
app.include_router(patrol_router, prefix="/api/patrol", tags=["patrol"])
app.include_router(voice_router, prefix="/api/voice", tags=["voice"])
app.include_router(webhook_router, prefix="/api/webhook", tags=["webhook"])


# ── WebSocket Hub ──
from typing import Set


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        disconnected = set()
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.add(conn)
        for conn in disconnected:
            self.active_connections.discard(conn)


health_manager = ConnectionManager()
alert_manager = ConnectionManager()


@app.websocket("/ws/health")
async def websocket_health(websocket: WebSocket):
    await health_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        health_manager.disconnect(websocket)


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await alert_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        alert_manager.disconnect(websocket)


@app.websocket("/ws/impact")
async def websocket_impact(websocket: WebSocket):
    await health_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        health_manager.disconnect(websocket)


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await health_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        health_manager.disconnect(websocket)


# ── Expose manager for broadcast from other modules ──
def get_alert_manager() -> ConnectionManager:
    return alert_manager

def get_health_manager() -> ConnectionManager:
    return health_manager


# ── Root ──
@app.get("/", response_class=HTMLResponse)
async def root():
    return """<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="0;url=/dashboard"></head>
<body><p>Redirecting to <a href="/dashboard">dashboard</a>...</p></body></html>"""


# ── Health Check ──
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": "2.1.0",
        "timestamp": asyncio.get_event_loop().time(),
    }