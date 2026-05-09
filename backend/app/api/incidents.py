"""
Incidents API — Manage security and infrastructure incidents.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

router = APIRouter()

# In-memory incidents store (replace with DB in production)
_incidents: list[dict] = []
_incounter = 0


@router.get("")
async def list_incidents(status: str = None, severity: str = None, limit: int = 50):
    """List incidents with optional filters."""
    result = [i for i in _incidents]

    if status:
        result = [i for i in result if i["status"] == status]
    if severity:
        result = [i for i in result if i["severity"] == severity]

    return {
        "incidents": result[-limit:],
        "total": len(result),
        "filtered": len(result[-limit:]),
    }


@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    """Get incident details."""
    for inc in _incidents:
        if inc["id"] == incident_id:
            return inc
    raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")


@router.post("")
async def create_incident(incident: dict):
    """Create a new incident."""
    global _incounter
    _incounter += 1

    now = datetime.now(timezone.utc).isoformat()
    new_incident = {
        "id": f"INC-{_incounter:04d}",
        "title": incident.get("title", "Untitled Incident"),
        "severity": incident.get("severity", "medium"),
        "status": incident.get("status", "open"),
        "description": incident.get("description", ""),
        "affected_services": incident.get("affected_services", []),
        "assignee": incident.get("assignee", ""),
        "created_at": now,
        "updated_at": now,
        "timeline": [
            {
                "timestamp": now,
                "event": "Incident created",
                "actor": "system",
            }
        ],
        "remediation_actions": incident.get("remediation_actions", []),
        "notes": incident.get("notes", ""),
        "tags": incident.get("tags", []),
    }

    _incidents.append(new_incident)

    # Broadcast to WebSocket
    try:
        from app.main import alert_manager
        await alert_manager.broadcast({
            "type": "incident_created",
            "incident": new_incident,
        })
    except Exception:
        pass

    return new_incident


@router.patch("/{incident_id}")
async def update_incident(incident_id: str, updates: dict):
    """Update an incident."""
    for inc in _incidents:
        if inc["id"] == incident_id:
            updatable = ["status", "assignee", "severity", "description", "notes", "tags"]
            for key in updatable:
                if key in updates:
                    inc[key] = updates[key]

            inc["updated_at"] = datetime.now(timezone.utc).isoformat()
            inc["timeline"].append({
                "timestamp": inc["updated_at"],
                "event": f"Updated: {', '.join(updates.keys())}",
                "actor": "api",
            })

            # Broadcast update
            try:
                from app.main import alert_manager
                await alert_manager.broadcast({
                    "type": "incident_updated",
                    "incident_id": incident_id,
                    "changes": updates,
                })
            except Exception:
                pass

            return inc

    raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")


@router.delete("/{incident_id}")
async def delete_incident(incident_id: str):
    """Archive/delete an incident."""
    global _incidents
    original_count = len(_incidents)
    _incidents = [i for i in _incidents if i["id"] != incident_id]

    if len(_incidents) < original_count:
        return {"status": "deleted", "incident_id": incident_id}
    raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")


@router.get("/{incident_id}/timeline")
async def get_incident_timeline(incident_id: str):
    """Get the timeline for an incident."""
    for inc in _incidents:
        if inc["id"] == incident_id:
            return {
                "timeline": inc.get("timeline", []),
                "incident_id": incident_id,
            }
    raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")


@router.post("/{incident_id}/remediation")
async def add_remediation(incident_id: str, action: dict):
    """Add a remediation action to an incident."""
    for inc in _incidents:
        if inc["id"] == incident_id:
            from uuid import uuid4
            remediation = {
                "action_id": f"ACT-{str(uuid4())[:8]}",
                "description": action.get("description", ""),
                "risk_level": action.get("risk_level", "medium"),
                "status": action.get("status", "proposed"),
                "assigned_to": action.get("assigned_to", ""),
                "executed_at": action.get("executed_at"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            inc["remediation_actions"].append(remediation)
            return remediation

    raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")