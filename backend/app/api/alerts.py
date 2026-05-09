"""
Alerts API — Real-time alert management and broadcasting.
"""

from fastapi import APIRouter, Request

router = APIRouter()


def _build_sample_alerts():
    """Generate sample alerts when no health analyzer is available."""
    return [
        {
            "id": "alert-001",
            "type": "warning",
            "title": "Cluster Health YELLOW",
            "message": "4 unassigned replica shards detected across 2 indices.",
            "service": "elasticsearch",
            "severity": "warning",
            "index": "orders-2026",
        }
    ]


# In-memory alert store
try:
    import orjson as json
except ImportError:
    import json

_alert_store: list = []


def add_alert(alert: dict) -> dict:
    alert["id"] = f"alert-{len(_alert_store) + 1}"
    _alert_store.append(alert)
    return alert


@router.get("")
async def get_alerts(request: Request):
    """Get all active alerts."""
    app_state = getattr(request.app.state, 'health_analyzer', None)
    if app_state:
        try:
            alerts = await app_state.get_alerts()
            return {
                "alerts": alerts,
                "count": len(alerts),
                "critical": len([a for a in alerts if isinstance(a, dict) and a.get("severity") == "critical"]),
                "warning": len([a for a in alerts if isinstance(a, dict) and a.get("severity") == "warning"]),
            }
        except Exception:
            pass
    return {
        "alerts": _build_sample_alerts(),
        "count": 1,
        "critical": 0,
        "warning": 1,
    }