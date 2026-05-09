"""API endpoints for Cross-Incident Memory Layer"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..services.incident_memory import IncidentMemoryService

router = APIRouter()
memory_service = IncidentMemoryService()


class StoreIncidentRequest(BaseModel):
    title: str
    severity: str = "medium"
    index_name: Optional[str] = None
    root_cause: str = "Unknown"
    impact: str = ""
    remediation: str = ""
    resolution_time_min: float = 0.0
    outcome: str = "resolved"
    tags: list[str] = []


class SearchRequest(BaseModel):
    index_name: Optional[str] = None
    root_cause: Optional[str] = None
    severity: Optional[str] = None
    tags: list[str] = []


@router.post("/memory/store")
async def store_incident(req: StoreIncidentRequest):
    """Store an incident in persistent memory."""
    memory_id = memory_service.store_incident(req.dict())
    return {"memory_id": memory_id, "status": "stored"}


@router.post("/memory/search")
async def search_similar(req: SearchRequest):
    """Search for similar past incidents."""
    results = memory_service.search_similar(req.dict())
    return {
        "matches": [
            {
                "memory_id": r.incident.memory_id,
                "title": r.incident.title,
                "similarity_score": r.similarity_score,
                "match_reasons": r.match_reasons,
                "root_cause": r.incident.root_cause,
                "remediation": r.incident.remediation,
                "resolution_time_min": r.incident.resolution_time_min,
                "outcome": r.incident.outcome,
            }
            for r in results
        ],
        "total_matches": len(results),
    }


@router.get("/memory/patterns")
async def get_patterns():
    """Get recurring incident patterns."""
    patterns = memory_service.get_patterns()
    return {
        "patterns": [
            {
                "pattern_id": p.pattern_id,
                "description": p.description,
                "frequency": p.frequency,
                "affected_indices": p.affected_indices,
                "avg_resolution_time": p.avg_resolution_time,
                "common_root_cause": p.common_root_cause,
            }
            for p in patterns
        ]
    }


@router.get("/memory/stats")
async def get_resolution_stats():
    """Get resolution statistics across all incidents."""
    stats = memory_service.get_resolution_stats()
    return {
        "total_incidents": stats.total_incidents,
        "avg_resolution_time": stats.avg_resolution_time,
        "resolution_rate": stats.resolution_rate,
        "top_root_causes": stats.top_root_causes,
        "recurring_incidents": stats.recurring_incidents,
        "mttr_by_severity": stats.mttr_by_severity,
    }


@router.get("/memory/recent")
async def get_recent(limit: int = 20):
    """Get recent incidents from memory."""
    incidents = memory_service.get_recent(limit)
    return {
        "incidents": [
            {
                "memory_id": inc.memory_id,
                "title": inc.title,
                "severity": inc.severity,
                "index_name": inc.index_name,
                "root_cause": inc.root_cause,
                "remediation": inc.remediation,
                "resolution_time_min": inc.resolution_time_min,
                "outcome": inc.outcome,
            }
            for inc in incidents
        ]
    }


@router.post("/memory/seed")
async def seed_demo_data():
    """Seed memory with demo data for hackathon demo."""
    memory_service.seed_demo_data()
    return {"status": "seeded", "incident_count": len(memory_service._incidents)}
