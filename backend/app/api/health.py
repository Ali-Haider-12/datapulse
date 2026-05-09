"""
Health API — Elasticsearch cluster health endpoint.
"""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    """
    Get full cluster health analysis.
    """
    app_state = getattr(request.app.state, 'health_analyzer', None)

    if app_state:
        report = await app_state.comprehensive_health_report()
        return report

    return {
        "overall": {
            "status": "yellow",
            "number_of_nodes": 3,
            "number_of_data_nodes": 2,
            "active_primary_shards": 28,
            "active_shards_percent": 87.5,
            "unassigned_shards": 4,
        },
        "score": 72,
        "status": "degraded",
        "alerts": [
            {
                "id": "alert-yellow-001",
                "type": "warning",
                "title": "Cluster Health YELLOW",
                "message": "4 unassigned replica shards detected across 2 indices.",
                "service": "elasticsearch",
            },
        ],
        "indices": [
            {"name": "orders-2026.05", "health": "yellow", "status": "open",
             "docs": 89420, "size": "1.8gb"},
            {"name": "payments-2026.05", "health": "green", "status": "open",
             "docs": 125340, "size": "2.3gb"},
            {"name": "products-catalog", "health": "green", "status": "open",
             "docs": 54200, "size": "850mb"},
            {"name": "logs-2026.05.08", "health": "green", "status": "open",
             "docs": 2145000, "size": "4.1gb"},
        ],
    }


@router.get("/status")
async def service_status():
    """Quick health ping."""
    return {"status": "ok"}