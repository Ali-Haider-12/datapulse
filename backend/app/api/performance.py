"""API endpoints for Auto-Performance Optimizer."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.es_write_client import ESWriteClient
from app.services.performance_optimizer import PerformanceOptimizer
from app.api.healer import get_write_client

router = APIRouter()


class MappingAnalysisRequest(BaseModel):
    index: str


@router.post("/performance/analyze")
async def analyze_performance():
    """Full cluster performance analysis.

    Scans all indices for:
    - Oversized/undersized shards
    - Excessive replicas on small indices
    - Suboptimal refresh intervals
    - Yellow health issues
    - Stale open indices
    - Missing index templates

    Returns proposed fixes (ready for approval via /healer/approve).
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
    optimizer = PerformanceOptimizer(mcp_client=mcp_client, write_client=get_write_client())
    result = await optimizer.analyze_performance()
    return result.to_dict()


@router.post("/performance/mapping-analysis")
async def analyze_mapping(request: MappingAnalysisRequest):
    """Analyze a specific index's mapping for anti-patterns.

    Checks:
    - Mapping explosion (too many fields)
    - Text fields without keyword sub-field
    - Dynamic mapping enabled with many fields
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
    optimizer = PerformanceOptimizer(mcp_client=mcp_client, write_client=get_write_client())
    return await optimizer.analyze_mappings(index=request.index)
