"""API endpoints for Predictive Capacity Planner."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.es_write_client import ESWriteClient
from app.services.capacity_planner import CapacityPlanner
from app.api.healer import get_write_client

router = APIRouter()


class CapacityRequest(BaseModel):
    action: str = "analyze"  # analyze, templates


@router.post("/capacity/analyze")
async def analyze_capacity():
    """Analyze cluster capacity and forecast growth.

    Returns capacity forecasts and proposed ILM policies.
    ILM policies are NOT created until approved via /healer/approve.
    """
    mcp_client = ElasticMCPClient(
        base_url=(
            settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0]
            if "/mcp" in settings.MCP_SERVER_URL
            else settings.MCP_SERVER_URL
        ),
        api_key=settings.ES_API_KEY or None,
        es_url=settings.ES_URL,
    )
    planner = CapacityPlanner(mcp_client=mcp_client, write_client=get_write_client())
    result = await planner.analyze_capacity()
    return result.to_dict()


@router.post("/capacity/templates")
async def generate_index_templates():
    """Generate index templates for common time-series patterns.

    Templates are NOT created until approved via /healer/approve.
    """
    mcp_client = ElasticMCPClient(
        base_url=(
            settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0]
            if "/mcp" in settings.MCP_SERVER_URL
            else settings.MCP_SERVER_URL
        ),
        api_key=settings.ES_API_KEY or None,
        es_url=settings.ES_URL,
    )
    planner = CapacityPlanner(mcp_client=mcp_client, write_client=get_write_client())
    result = await planner.generate_index_templates()
    return result.to_dict()
