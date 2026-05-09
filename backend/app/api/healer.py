"""API endpoints for the Autonomous Cluster Healer.

Endpoints:
- POST /api/healer/scan       — Scan cluster for issues, propose remediation actions
- GET  /api/healer/pending    — List all actions awaiting approval
- POST /api/healer/approve    — Approve & execute one or more actions
- POST /api/healer/approve/{id} — Approve & execute a single action
- POST /api/healer/reject/{id}  — Reject a proposed action
- GET  /api/healer/history    — View execution history
- GET  /api/healer/action/{id}  — Get details of a specific action
"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.es_write_client import ESWriteClient
from app.services.cluster_healer import ClusterHealer

router = APIRouter()

# Singleton write client shared across requests
_write_client: Optional[ESWriteClient] = None


def get_write_client() -> ESWriteClient:
    global _write_client
    if _write_client is None:
        _write_client = ESWriteClient(
            es_url=settings.ES_URL,
            api_key=settings.ES_API_KEY or None,
            username=settings.ES_USERNAME or None,
            password=settings.ES_PASSWORD or None,
        )
    return _write_client


def get_healer() -> ClusterHealer:
    mcp_client = ElasticMCPClient(
        base_url=(
            settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0]
            if "/mcp" in settings.MCP_SERVER_URL
            else settings.MCP_SERVER_URL
        ),
        api_key=settings.ES_API_KEY or None,
        es_url=settings.ES_URL,
    )
    return ClusterHealer(mcp_client=mcp_client, write_client=get_write_client())


class ActionApproval(BaseModel):
    action_ids: List[str]


class HealRequest(BaseModel):
    workflow: str = "full"  # full, yellow, red, mapping, stale
    days_threshold: int = 90


@router.get("/healer/pending")
async def get_pending_actions():
    """Get all pending actions awaiting approval."""
    client = get_write_client()
    actions = client.get_pending_actions()
    return {"pending_actions": actions, "count": len(actions)}


@router.get("/healer/history")
async def get_action_history(limit: int = 50):
    """Get execution history of all actions."""
    client = get_write_client()
    return {"history": client.get_action_history(limit=limit)}


@router.get("/healer/action/{action_id}")
async def get_action(action_id: str):
    """Get details of a specific action."""
    client = get_write_client()
    action = client.get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


@router.post("/healer/scan")
async def scan_cluster(request: HealRequest):
    """Scan the cluster for issues and propose remediation actions.

    This is the DETECT + PROPOSE step. Actions are NOT executed until approved.
    """
    healer = get_healer()

    if request.workflow == "yellow":
        result = await healer.heal_yellow_indices()
    elif request.workflow == "red":
        result = await healer.heal_red_indices()
    elif request.workflow == "mapping":
        result = await healer.heal_mapping_explosions()
    elif request.workflow == "stale":
        result = await healer.heal_stale_indices(
            days_threshold=request.days_threshold
        )
    else:
        result = await healer.full_cluster_heal()

    return result.to_dict()


@router.post("/healer/approve")
async def approve_actions(approval: ActionApproval):
    """Approve and execute proposed actions.

    Actions are executed in sequence. If any fails, subsequent ones still run.
    """
    client = get_write_client()
    results = await client.bulk_approve_and_execute(approval.action_ids)
    return {"results": results, "count": len(results)}


@router.post("/healer/approve/{action_id}")
async def approve_single_action(action_id: str):
    """Approve and execute a single action."""
    client = get_write_client()
    client.approve(action_id)
    result = await client.execute(action_id)
    return result


@router.post("/healer/reject/{action_id}")
async def reject_action(action_id: str):
    """Reject a proposed action."""
    client = get_write_client()
    return client.reject(action_id)


@router.delete("/healer/action/{action_id}")
async def cancel_action(action_id: str):
    """Cancel/reject a pending action."""
    client = get_write_client()
    return client.reject(action_id)
