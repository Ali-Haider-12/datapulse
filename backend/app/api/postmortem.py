"""API router for Postmortem PDF generation."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.services.postmortem_generator import PostmortemGenerator, PostmortemData
from app.services.outage_timeline import OutageTimelineGenerator

router = APIRouter()
generator = PostmortemGenerator()
timeline_gen = OutageTimelineGenerator()


class GeneratePostmortemRequest(BaseModel):
    incident_id: str
    title: str = ""
    severity: str = "critical"
    summary: str = ""
    root_cause: str = ""
    impact: str = ""
    blast_radius: list[str] = []
    timeline_events: list[dict] = []
    five_whys: list[str] = []
    action_items: list[dict] = []
    what_went_well: list[str] = []
    what_could_be_improved: list[str] = []


@router.post("/postmortem/generate")
async def generate_postmortem(req: GeneratePostmortemRequest):
    """Generate a PDF postmortem report."""
    data = PostmortemData(
        incident_id=req.incident_id,
        title=req.title or f"Incident {req.incident_id}",
        severity=req.severity,
        summary=req.summary,
        root_cause=req.root_cause,
        impact=req.impact,
        blast_radius=req.blast_radius,
        timeline_events=req.timeline_events,
        five_whys=req.five_whys,
        action_items=req.action_items,
        what_went_well=req.what_went_well,
        what_could_be_improved=req.what_could_be_improved,
    )
    filepath = generator.generate(data)
    filename = filepath.split("/")[-1]
    return {"status": "ok", "filepath": filepath, "filename": filename}


@router.post("/postmortem/generate-from-timeline/{incident_id}")
async def generate_from_timeline(incident_id: str):
    """Generate a postmortem from a stored timeline + demo data."""
    # Use demo timeline if not found
    timeline = timeline_gen.get_timeline(f"TL-0001")
    if not timeline:
        timeline = timeline_gen.generate_demo_timeline(incident_id=incident_id)

    data = generator.generate_from_timeline(timeline)
    filepath = generator.generate(data)
    filename = filepath.split("/")[-1]
    return {"status": "ok", "filepath": filepath, "filename": filename}


@router.get("/postmortem/download/{filename}")
async def download_postmortem(filename: str):
    """Download a generated PDF postmortem."""
    filepath = f"/tmp/postmortems/{filename}"
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(filepath, media_type="application/pdf", filename=filename)


import os
