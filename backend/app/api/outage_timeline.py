"""API router for Outage Timeline Generator."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.outage_timeline import OutageTimelineGenerator

router = APIRouter()
generator = OutageTimelineGenerator()


class LogEntry(BaseModel):
    timestamp: float
    message: str
    source: str = "elasticsearch"
    index_name: Optional[str] = None
    node_name: Optional[str] = None
    severity: str = "info"
    metadata: dict = {}


class GenerateTimelineRequest(BaseModel):
    incident_id: str
    logs: list[LogEntry]
    title: str = ""


@router.post("/timeline/generate")
async def generate_timeline(req: GenerateTimelineRequest):
    """Generate an outage timeline from log entries."""
    logs = [log.model_dump() for log in req.logs]
    timeline = generator.generate_timeline(
        incident_id=req.incident_id,
        logs=logs,
        title=req.title,
    )
    return {
        "timeline_id": timeline.timeline_id,
        "title": timeline.title,
        "total_duration_sec": timeline.total_duration_sec,
        "event_count": len(timeline.events),
        "phases": timeline.phases,
        "key_moments": timeline.key_moments,
        "root_cause": timeline.root_cause,
        "impact_summary": timeline.impact_summary,
        "blast_radius": timeline.blast_radius,
    }


@router.get("/timeline/{timeline_id}")
async def get_timeline(timeline_id: str):
    """Get a stored timeline by ID."""
    timeline = generator.get_timeline(timeline_id)
    if not timeline:
        raise HTTPException(status_code=404, detail="Timeline not found")
    return timeline


@router.get("/timelines")
async def list_timelines():
    """List all stored timelines."""
    return generator.list_timelines()


@router.post("/timeline/demo")
async def generate_demo_timeline():
    """Generate a demo timeline for presentation."""
    timeline = generator.generate_demo_timeline()
    return {
        "timeline_id": timeline.timeline_id,
        "title": timeline.title,
        "total_duration_sec": timeline.total_duration_sec,
        "event_count": len(timeline.events),
        "phases": timeline.phases,
        "key_moments": timeline.key_moments,
        "root_cause": timeline.root_cause,
        "impact_summary": timeline.impact_summary,
        "blast_radius": timeline.blast_radius,
        "events": [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp,
                "event_type": e.event_type.value,
                "source": e.source.value,
                "title": e.title,
                "severity": e.severity,
                "index_name": e.index_name,
                "node_name": e.node_name,
            }
            for e in timeline.events
        ],
    }
