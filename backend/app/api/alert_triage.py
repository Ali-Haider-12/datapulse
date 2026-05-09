"""API endpoints for Smart Alert Triage + Correlation Engine"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..services.alert_triage import AlertTriageService, Alert, AlertGroup, TriageResult, TriageSummary, SuppressedAlert

router = APIRouter()
triage_service = AlertTriageService()


class AlertInput(BaseModel):
    id: str
    severity: str = "warning"
    message: str
    index_name: Optional[str] = None
    source: str = "elasticsearch"


class TriageRequest(BaseModel):
    alerts: list[AlertInput]


@router.post("/alerts/triage")
async def triage_alerts(req: TriageRequest):
    """Triage current alerts — group, correlate, suppress noise."""
    alerts = [
        Alert(id=a.id, severity=a.severity, message=a.message, index_name=a.index_name, source=a.source)
        for a in req.alerts
    ]
    result = triage_service.triage_alerts(alerts)
    return {
        "groups": [
            {
                "group_id": g.group_id,
                "root_cause_hint": g.root_cause_hint,
                "alert_count": len(g.alerts),
                "severity_score": g.combined_severity_score,
                "affected_indices": g.affected_indices,
                "suppressed_count": g.suppressed_count,
            }
            for g in result.groups
        ],
        "suppressed_count": len(result.suppressed),
        "summary": {
            "total_alerts": result.summary.total_alerts,
            "active_groups": result.summary.active_groups,
            "suppressed_count": result.summary.suppressed_count,
            "noise_reduction_pct": result.summary.noise_reduction_pct,
            "recommendation": result.summary.recommendation,
        } if result.summary else None,
    }


@router.get("/alerts/triage/summary")
async def get_triage_summary():
    """Get the latest triage summary."""
    summary = triage_service.get_triage_summary()
    return {
        "total_alerts": summary.total_alerts,
        "active_groups": summary.active_groups,
        "suppressed_count": summary.suppressed_count,
        "noise_reduction_pct": summary.noise_reduction_pct,
        "recommendation": summary.recommendation if summary.recommendation else "No triage data yet. Run POST /api/alerts/triage first.",
    }


@router.get("/alerts/groups")
async def get_alert_groups():
    """Get correlated alert groups."""
    groups = triage_service._groups
    return {
        "groups": [
            {
                "group_id": g.group_id,
                "root_cause_hint": g.root_cause_hint,
                "severity_score": g.combined_severity_score,
                "affected_indices": g.affected_indices,
                "alert_count": len(g.alerts),
                "suppressed_count": g.suppressed_count,
                "alerts": [{"id": a.id, "severity": a.severity, "message": a.message} for a in g.alerts],
            }
            for g in groups
        ]
    }
