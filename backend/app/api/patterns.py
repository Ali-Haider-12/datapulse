"""API endpoints for Cross-Incident Pattern Engine."""
from fastapi import APIRouter
from typing import Optional

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.es_write_client import ESWriteClient
from app.services.cross_incident_engine import CrossIncidentEngine
from app.api.healer import get_write_client

router = APIRouter()


@router.get("/patterns/summary")
async def get_pattern_summary():
    """Get a summary of all known incident patterns."""
    engine = CrossIncidentEngine(
        mcp_client=ElasticMCPClient(
            base_url=(
                settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0]
                if "/mcp" in settings.MCP_SERVER_URL
                else settings.MCP_SERVER_URL
            ),
            api_key=settings.ES_API_KEY or None,
            es_url=settings.ES_URL,
        ),
        write_client=get_write_client(),
    )
    return await engine.get_pattern_summary()


@router.post("/patterns/analyze")
async def analyze_current_patterns():
    """Analyze current cluster state against known incident patterns.

    Returns:
    - Known patterns and their confidence levels
    - Current symptoms detected
    - Auto-fix proposals for matching patterns
    - Proposed actions (ready for approval via /healer/approve)
    """
    engine = CrossIncidentEngine(
        mcp_client=ElasticMCPClient(
            base_url=(
                settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0]
                if "/mcp" in settings.MCP_SERVER_URL
                else settings.MCP_SERVER_URL
            ),
            api_key=settings.ES_API_KEY or None,
            es_url=settings.ES_URL,
        ),
        write_client=get_write_client(),
    )
    result = await engine.analyze_patterns()
    return result.to_dict()
