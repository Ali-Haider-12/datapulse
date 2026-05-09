"""API endpoints for Auto-Runbook Engine"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..services.runbook_engine import RunbookEngine

router = APIRouter()
runbook_engine = RunbookEngine()


class MatchRequest(BaseModel):
    root_cause: str = ""
    title: str = ""
    message: str = ""
    severity: str = ""
    index_name: Optional[str] = None


class ExecuteStepRequest(BaseModel):
    auto_approve_safe: bool = False


@router.get("/runbooks")
async def list_runbooks():
    """List all available runbooks."""
    runbooks = runbook_engine.list_runbooks()
    return {
        "runbooks": [
            {
                "runbook_id": rb.runbook_id,
                "name": rb.name,
                "description": rb.description,
                "trigger_conditions": rb.trigger_conditions,
                "steps_count": len(rb.steps),
                "total_estimated_time": rb.total_estimated_time,
            }
            for rb in runbooks
        ]
    }


@router.get("/runbooks/{runbook_id}")
async def get_runbook(runbook_id: str):
    """Get a specific runbook with all steps."""
    rb = runbook_engine.get_runbook(runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return {
        "runbook_id": rb.runbook_id,
        "name": rb.name,
        "description": rb.description,
        "trigger_conditions": rb.trigger_conditions,
        "steps": [
            {
                "step_id": s.step_id,
                "title": s.title,
                "description": s.description,
                "action": s.action,
                "risk": s.risk.value,
                "estimated_time_sec": s.estimated_time_sec,
                "requires_approval": s.requires_approval,
            }
            for s in rb.steps
        ],
        "total_estimated_time": rb.total_estimated_time,
    }


@router.post("/runbooks/match")
async def match_runbook(req: MatchRequest):
    """Find the best matching runbook for an incident."""
    result = runbook_engine.match_runbook(req.dict())
    if not result:
        return {"match": None, "message": "No matching runbook found"}
    return {
        "match": {
            "runbook_id": result.runbook.runbook_id,
            "name": result.runbook.name,
            "description": result.runbook.description,
            "match_score": result.match_score,
            "match_reasons": result.match_reasons,
            "steps": [
                {
                    "step_id": s.step_id,
                    "title": s.title,
                    "risk": s.risk.value,
                    "requires_approval": s.requires_approval,
                    "estimated_time_sec": s.estimated_time_sec,
                }
                for s in result.runbook.steps
            ],
            "total_estimated_time": result.runbook.total_estimated_time,
        }
    }


@router.post("/runbooks/{runbook_id}/execute/{step_id}")
async def execute_step(runbook_id: str, step_id: str, req: ExecuteStepRequest):
    """Execute a specific runbook step."""
    result = runbook_engine.execute_step(runbook_id, step_id, auto_approve_safe=req.auto_approve_safe)
    return {
        "step_id": result.step_id,
        "runbook_id": result.runbook_id,
        "status": result.status.value,
        "output": result.output,
        "error": result.error,
        "duration_sec": result.duration_sec,
    }


@router.get("/runbooks/history")
async def get_execution_history(limit: int = 20):
    """Get recent runbook execution history."""
    history = runbook_engine.get_execution_history(limit)
    return {
        "executions": [
            {
                "execution_id": e.execution_id,
                "runbook_id": e.runbook_id,
                "incident_id": e.incident_id,
                "steps_completed": e.steps_completed,
                "steps_total": e.steps_total,
                "status": e.status,
            }
            for e in history
        ]
    }
