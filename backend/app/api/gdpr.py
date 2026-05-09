"""API endpoints for GDPR Erasure Engine."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.es_write_client import ESWriteClient
from app.services.gdpr_erasure import GDPRErasureEngine
from app.api.healer import get_write_client

router = APIRouter()


class ErasureSearchRequest(BaseModel):
    user_identifier: str
    identifier_field: Optional[str] = None  # e.g. "email", "user_id". If None, searches all PII fields.


class ErasureVerifyRequest(BaseModel):
    user_identifier: str
    identifier_field: Optional[str] = None


@router.post("/gdpr/search")
async def search_user_data(request: ErasureSearchRequest):
    """Search ALL indices for a user's personal data.

    Returns:
    - Indices containing the user's data
    - Document counts per index
    - Sample documents showing matched fields
    - Proposed delete-by-query actions (NOT executed until approved)

    ⚠️ HIGH RISK — Deletion actions require explicit approval.
    """
    engine = GDPRErasureEngine(
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
    result = await engine.search_user_data(
        user_identifier=request.user_identifier,
        identifier_field=request.identifier_field,
    )
    return result.to_dict()


@router.post("/gdpr/verify")
async def verify_erasure(request: ErasureVerifyRequest):
    """Verify that all user data has been deleted (re-search after erasure).

    Returns:
    - verified: True if no residual data found
    - residual_data: List of indices still containing user data (if any)
    """
    engine = GDPRErasureEngine(
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
    return await engine.verify_erasure(
        user_identifier=request.user_identifier,
        identifier_field=request.identifier_field,
    )


@router.get("/gdpr/audit-log")
async def get_audit_log(limit: int = 50):
    """Get the audit log of all GDPR erasure operations."""
    engine = GDPRErasureEngine(
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
    return {"audit_log": engine.get_audit_log(limit=limit)}
