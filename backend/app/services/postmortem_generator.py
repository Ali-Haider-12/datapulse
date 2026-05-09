"""Auto-Generated PDF Postmortems

Generates professional incident postmortem PDFs with:
- Timeline visualization (matplotlib)
- Root cause analysis
- Impact summary
- Action items
- Resolution details

Addresses the "blameless postmortem" pattern — auto-generate so engineers
don't have to manually write reports after exhausting incidents.
"""

from __future__ import annotations
import os
import time
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from fpdf import FPDF
from app.services.outage_timeline import OutageTimeline, TimelineEvent, TimelineEventType


@dataclass
class PostmortemData:
    incident_id: str
    title: str
    severity: str = "critical"
    date: str = ""
    authors: list[str] = field(default_factory=lambda: ["DataPulse AI Agent"])
    summary: str = ""
    root_cause: str = ""
    detection_method: str = ""
    timeline_events: list[dict] = field(default_factory=list)
    impact: str = ""
    blast_radius: list[str] = field(default_factory=list)
    total_duration_min: float = 0.0
    ttd_min: float = 0.0  # Time to detect
    ttm_min: float = 0.0  # Time to mitigate
    ttr_min: float = 0.0  # Time to resolve
    five_whys: list[str] = field(default_factory=list)
    action_items: list[dict] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    what_went_well: list[str] = field(default_factory=list)
    what_could_be_improved: list[str] = field(default_factory=list)
    timeline_image_path: Optional[str] = None


class PostmortemPDF(FPDF):
    """Custom PDF class for postmortem reports."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "DataPulse — Incident Postmortem Report", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(30, 30, 120)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(30, 30, 120)
        self.line(10, self.get_y(), 120, self.get_y())
        self.ln(4)

    def body_text(self, text: str, bold: bool = False):
        self.set_font("Helvetica", "B" if bold else "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def bullet_list(self, items: list[str]):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        for item in items:
            self.cell(5, 6, chr(8226))  # bullet char
            self.multi_cell(0, 6, f" {item}")
            self.ln(1)

    def key_value(self, key: str, value: str, indent: int = 0):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(40, 40, 40)
        x = self.get_x() + indent
        self.set_x(x)
        self.cell(50, 6, f"{key}:")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def severity_badge(self, severity: str):
        colors = {
            "critical": (220, 50, 50),
            "high": (255, 140, 0),
            "warning": (255, 200, 0),
            "info": (100, 180, 100),
        }
        r, g, b = colors.get(severity, (100, 100, 100))
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 10)
        self.cell(30, 8, severity.upper(), fill=True, align="C")
        self.ln(10)


class PostmortemGenerator:
    """Generate PDF postmortem reports from incident data."""

    def __init__(self, output_dir: str = "/tmp/postmortems"):
        self._output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, data: PostmortemData) -> str:
        """Generate a PDF postmortem report. Returns the file path."""
        if not data.date:
            data.date = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

        # Generate timeline image if we have events
        if data.timeline_events and not data.timeline_image_path:
            data.timeline_image_path = self._generate_timeline_image(data)

        pdf = PostmortemPDF()
        pdf.alias_nb_pages()
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(20, 20, 80)
        pdf.multi_cell(0, 12, data.title)
        pdf.ln(3)

        # Severity badge + metadata
        pdf.severity_badge(data.severity)
        pdf.key_value("Incident ID", data.incident_id)
        pdf.key_value("Date", data.date)
        pdf.key_value("Authors", ", ".join(data.authors))
        pdf.key_value("Duration", f"{data.total_duration_min:.1f} minutes")
        pdf.key_value("TTD", f"{data.ttd_min:.1f} min" if data.ttd_min else "N/A")
        pdf.key_value("TTM", f"{data.ttm_min:.1f} min" if data.ttm_min else "N/A")
        pdf.key_value("TTR", f"{data.ttr_min:.1f} min" if data.ttr_min else "N/A")
        pdf.ln(5)

        # Summary
        if data.summary:
            pdf.section_title("Summary")
            pdf.body_text(data.summary)

        # Root Cause
        if data.root_cause:
            pdf.section_title("Root Cause")
            pdf.body_text(data.root_cause)

        # Five Whys
        if data.five_whys:
            pdf.section_title("5-Why Analysis")
            for i, why in enumerate(data.five_whys, 1):
                pdf.key_value(f"Why #{i}", why, indent=5)

        # Timeline Image
        if data.timeline_image_path and os.path.exists(data.timeline_image_path):
            pdf.section_title("Incident Timeline")
            try:
                pdf.image(data.timeline_image_path, x=10, w=190)
            except Exception:
                pdf.body_text("[Timeline visualization could not be rendered]")

        # Timeline Events
        if data.timeline_events:
            pdf.section_title("Timeline Events")
            for event in data.timeline_events:
                ts = event.get("timestamp_str", "")
                title = event.get("title", "")
                etype = event.get("event_type", "")
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(40, 5, ts)
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(30, 5, f"[{etype}]")
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(0, 5, title)
                pdf.ln(1)

        # Impact
        if data.impact:
            pdf.section_title("Impact")
            pdf.body_text(data.impact)

        if data.blast_radius:
            pdf.body_text("Affected Systems:", bold=True)
            pdf.bullet_list(data.blast_radius)

        # What Went Well
        if data.what_went_well:
            pdf.section_title("What Went Well")
            pdf.bullet_list(data.what_went_well)

        # What Could Be Improved
        if data.what_could_be_improved:
            pdf.section_title("What Could Be Improved")
            pdf.bullet_list(data.what_could_be_improved)

        # Lessons Learned
        if data.lessons_learned:
            pdf.section_title("Lessons Learned")
            pdf.bullet_list(data.lessons_learned)

        # Action Items
        if data.action_items:
            pdf.section_title("Action Items")
            for i, item in enumerate(data.action_items, 1):
                priority = item.get("priority", "medium")
                owner = item.get("owner", "TBD")
                desc = item.get("description", "")
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, f"#{i} [{priority.upper()}] {desc}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(100, 100, 100)
                pdf.cell(0, 5, f"   Owner: {owner}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(40, 40, 40)
                pdf.ln(2)

        # Save PDF
        filename = f"postmortem_{data.incident_id}_{int(time.time())}.pdf"
        filepath = os.path.join(self._output_dir, filename)
        pdf.output(filepath)
        return filepath

    def _generate_timeline_image(self, data: PostmortemData) -> str:
        """Generate a matplotlib timeline visualization."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from datetime import datetime, timedelta
        except ImportError:
            return ""

        events = data.timeline_events
        if not events:
            return ""

        fig, ax = plt.subplots(figsize=(10, 4))

        # Color mapping by event type
        colors = {
            "trigger": "#e74c3c",
            "detection": "#f39c12",
            "escalation": "#e67e22",
            "diagnosis": "#3498db",
            "mitigation": "#2ecc71",
            "resolution": "#27ae60",
            "communication": "#9b59b6",
            "anomaly": "#f1c40f",
            "action": "#1abc9c",
            "error": "#c0392b",
        }

        base_time = events[0].get("timestamp", time.time())

        y_positions = []
        labels = []
        for i, event in enumerate(events):
            ts = event.get("timestamp", base_time)
            offset_sec = ts - base_time
            offset_min = offset_sec / 60

            etype = event.get("event_type", "action")
            color = colors.get(etype, "#95a5a6")

            ax.plot(offset_min, i, "o", color=color, markersize=10, zorder=5)
            title = event.get("title", "")[:50]
            ax.annotate(title, (offset_min, i), textcoords="offset points",
                       xytext=(10, 0), fontsize=7, va="center")
            y_positions.append(i)

        ax.set_yticks(y_positions)
        ax.set_yticklabels([e.get("event_type", "")[:12] for e in events], fontsize=8)
        ax.set_xlabel("Time (minutes from first event)", fontsize=9)
        ax.set_title(f"Incident Timeline: {data.title[:60]}", fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        plt.tight_layout()
        img_path = os.path.join(self._output_dir, f"timeline_{data.incident_id}_{int(time.time())}.png")
        fig.savefig(img_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return img_path

    def generate_from_timeline(self, timeline: OutageTimeline) -> PostmortemData:
        """Convert an OutageTimeline into PostmortemData for PDF generation."""
        duration_min = timeline.total_duration_sec / 60

        # Calculate TTD, TTM, TTR
        ttd = ttm = ttr = 0.0
        triggers = [e for e in timeline.events if e.event_type == TimelineEventType.trigger]
        detections = [e for e in timeline.events if e.event_type == TimelineEventType.detection]
        mitigations = [e for e in timeline.events if e.event_type == TimelineEventType.mitigation]
        resolutions = [e for e in timeline.events if e.event_type == TimelineEventType.resolution]

        if triggers and detections:
            ttd = (detections[0].timestamp - triggers[0].timestamp) / 60
        if triggers and mitigations:
            ttm = (mitigations[0].timestamp - triggers[0].timestamp) / 60
        if triggers and resolutions:
            ttr = (resolutions[0].timestamp - triggers[0].timestamp) / 60

        # Determine severity
        critical_events = [e for e in timeline.events if e.severity == "critical"]
        severity = "critical" if critical_events else "high"

        # Auto-generate 5-whys
        five_whys = self._auto_five_whys(timeline)

        # Auto-generate action items
        action_items = self._auto_action_items(timeline)

        # Auto-generate lessons
        what_went_well = self._auto_what_went_well(timeline)
        what_could_be_improved = self._auto_what_could_be_improved(timeline)

        # Format timeline events for PDF
        timeline_events = []
        base_ts = timeline.events[0].timestamp if timeline.events else time.time()
        for e in timeline.events:
            offset = e.timestamp - base_ts
            timeline_events.append({
                "timestamp": e.timestamp,
                "timestamp_str": f"+{offset/60:.1f}min",
                "title": e.title,
                "event_type": e.event_type.value,
            })

        return PostmortemData(
            incident_id=timeline.incident_id,
            title=timeline.title,
            severity=severity,
            summary=timeline.impact_summary,
            root_cause=timeline.root_cause or "Root cause not yet determined",
            detection_method="DataPulse AI monitoring agent",
            timeline_events=timeline_events,
            impact=timeline.impact_summary,
            blast_radius=timeline.blast_radius,
            total_duration_min=duration_min,
            ttd_min=ttd,
            ttm_min=ttm,
            ttr_min=ttr,
            five_whys=five_whys,
            action_items=action_items,
            what_went_well=what_went_well,
            what_could_be_improved=what_could_be_improved,
        )

    def _auto_five_whys(self, timeline: OutageTimeline) -> list[str]:
        """Auto-generate a 5-why analysis from the timeline."""
        root_cause = timeline.root_cause or "Unknown issue detected"
        whys = [f"The system experienced: {root_cause}"]

        # Build causal chain from events
        if any("disk" in e.title.lower() or "watermark" in e.title.lower() for e in timeline.events):
            whys.extend([
                "Because disk space was exhausted on a data node",
                "Because old indices were not cleaned up by ILM policy",
                "Because ILM policy was not configured for time-based indices",
                "Because there was no automated index lifecycle management in place",
            ])
        elif any("shard" in e.title.lower() for e in timeline.events):
            whys.extend([
                "Because primary shards became unassigned",
                "Because the node hosting them ran out of disk/memory",
                "Because resource limits were not monitored with auto-scaling",
                "Because cluster capacity planning did not account for growth",
            ])
        elif any("slow" in e.title.lower() or "latency" in e.title.lower() for e in timeline.events):
            whys.extend([
                "Because queries were performing full scans without caching",
                "Because index mappings had grown due to dynamic field creation",
                "Because no explicit mapping schema was enforced",
                "Because developer guidelines for ES mappings were not documented",
            ])
        else:
            whys.extend([
                "Because a system component failed unexpectedly",
                "Because there was insufficient redundancy for that component",
                "Because the failure mode was not covered by existing monitoring",
                "Because monitoring coverage gaps were not identified in prior reviews",
            ])

        return whys[:5]

    def _auto_action_items(self, timeline: OutageTimeline) -> list[dict]:
        """Auto-generate action items from the timeline."""
        items = []

        if any("disk" in e.title.lower() for e in timeline.events):
            items.append({"description": "Configure ILM policies for all time-based indices", "priority": "high", "owner": "Platform Team"})
            items.append({"description": "Set up disk usage alerts at 80% watermark", "priority": "high", "owner": "SRE Team"})

        if any("shard" in e.title.lower() for e in timeline.events):
            items.append({"description": "Review shard allocation strategy and add capacity buffers", "priority": "high", "owner": "Platform Team"})
            items.append({"description": "Implement auto-scaling for data nodes", "priority": "medium", "owner": "Infrastructure Team"})

        if any("slow" in e.title.lower() or "latency" in e.title.lower() for e in timeline.events):
            items.append({"description": "Enforce explicit index mappings to prevent mapping explosion", "priority": "high", "owner": "Dev Team"})
            items.append({"description": "Add query profiling to CI pipeline", "priority": "medium", "owner": "Dev Team"})

        # Generic items
        items.append({"description": "Update runbook with lessons from this incident", "priority": "medium", "owner": "On-call Team"})
        items.append({"description": "Add this failure pattern to DataPulse incident memory", "priority": "low", "owner": "DataPulse AI"})

        return items

    def _auto_what_went_well(self, timeline: OutageTimeline) -> list[str]:
        items = ["Incident was detected and alerted automatically"]
        mitigations = [e for e in timeline.events if e.event_type == TimelineEventType.mitigation]
        if mitigations:
            items.append("Mitigation was applied successfully")
        resolutions = [e for e in timeline.events if e.event_type == TimelineEventType.resolution]
        if resolutions:
            items.append("Service was fully restored")
        if timeline.total_duration_sec < 3600:
            items.append("Incident was resolved within 1 hour")
        comms = [e for e in timeline.events if e.event_type == TimelineEventType.communication]
        if comms:
            items.append("Stakeholders were proactively communicated with")
        return items

    def _auto_what_could_be_improved(self, timeline: OutageTimeline) -> list[str]:
        items = []
        triggers = [e for e in timeline.events if e.event_type == TimelineEventType.trigger]
        detections = [e for e in timeline.events if e.event_type == TimelineEventType.detection]
        if triggers and detections:
            ttd = (detections[0].timestamp - triggers[0].timestamp) / 60
            if ttd > 5:
                items.append(f"Detection took {ttd:.1f} minutes — could be faster with proactive monitoring")
        if timeline.total_duration_sec > 1800:
            items.append("Resolution took over 30 minutes — could benefit from auto-remediation")
        diagnoses = [e for e in timeline.events if e.event_type == TimelineEventType.diagnosis]
        if not diagnoses:
            items.append("Root cause was not formally diagnosed — improve AI diagnosis capabilities")
        return items if items else ["Improve monitoring coverage for early detection"]
