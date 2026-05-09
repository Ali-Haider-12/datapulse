"""API endpoints for Intelligent Data Triage & Reindexing."""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.es_write_client import ESWriteClient
from app.services.data_triager import DataTriager
from app.api.healer import get_write_client

router = APIRouter()


def get_triager() -> DataTriager:
    mcp_client = ElasticMCPClient(
        base_url=(
            settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0]
            if "/mcp" in settings.MCP_SERVER_URL
            else settings.MCP_SERVER_URL
        ),
        api_key=settings.ES_API_KEY or None,
        es_url=settings.ES_URL,
    )
    return DataTriager(mcp_client=mcp_client, write_client=get_write_client())


class TriageRequest(BaseModel):
    scan_type: str = "full"  # full, oversized, mapping_conflicts, undersized


@router.post("/triage/scan")
async def scan_for_reindex(request: TriageRequest):
    """Scan indices for reindex candidates.

    Scans for: oversized shards, mapping conflicts, undersized shards.
    Returns proposed reindex actions — NOT executed until approved via /healer/approve.
    """
    triager = get_triager()

    if request.scan_type == "oversized":
        result = await triager.scan_oversized_shards()
    elif request.scan_type == "mapping_conflicts":
        result = await triager.scan_mapping_conflicts()
    elif request.scan_type == "undersized":
        result = await triager.scan_undersized_shards()
    else:
        result = await triager.full_triage()

    return result.to_dict()
