"""Outage Timeline Generator

Auto-generates an incident timeline from Elasticsearch logs.
Addresses the "blameless postmortem" pattern — automatic timeline reconstruction
so engineers don't have to manually piece together what happened.

Inspired by HN: "The hardest part of an incident is reconstructing the timeline after"
"""

from __future__ import annotations
import time
import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class TimelineEventType(str, Enum):
    trigger = "trigger"          # Root cause / first signal
    detection = "detection"      # Alert fired
    escalation = "escalation"    # Eng paged / escalated
    diagnosis = "diagnosis"      # Root cause identified
    mitigation = "mitigation"    # Fix applied / impact reduced
    resolution = "resolution"    # Fully resolved
    communication = "communication"  # Status page / customer notified
    anomaly = "anomaly"          # Unusual event (not yet classified)
    action = "action"            # Manual action taken
    error = "error"              # Error observed


class TimelineSource(str, Enum):
    elasticsearch = "elasticsearch"
    alerts = "alerts"
    chat = "chat"
    deployment = "deployment"
    manual = "manual"
    datatulse = "datapulse"


@dataclass
class TimelineEvent:
    event_id: str
    timestamp: float  # Unix timestamp
    event_type: TimelineEventType
    source: TimelineSource
    title: str
    description: str
    severity: str = "info"  # info, warning, high, critical
    index_name: Optional[str] = None
    node_name: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    duration_sec: Optional[float] = None


@dataclass
class OutageTimeline:
    timeline_id: str
    incident_id: str
    title: str
    start_time: float
    end_time: Optional[float]
    total_duration_sec: float
    events: list[TimelineEvent] = field(default_factory=list)
    phases: list[dict] = field(default_factory=list)
    key_moments: list[dict] = field(default_factory=list)
    root_cause: Optional[str] = None
    impact_summary: str = ""
    blast_radius: list[str] = field(default_factory=list)


@dataclass
class TimelinePhase:
    name: str
    start_time: float
    end_time: float
    duration_sec: float
    event_count: int
    description: str


# Pattern matching for log classification
LOG_PATTERNS = [
    (r"RED.*index|index.*went.*RED|unassigned.*primary", TimelineEventType.trigger, "critical"),
    (r"YELLOW.*index|replica.*unassigned|allocation.*failed", TimelineEventType.anomaly, "warning"),
    (r"alert.*fired|threshold.*exceeded|monitor.*triggered", TimelineEventType.detection, "high"),
    (r"page.*on.call|escalat|incident.*declared", TimelineEventType.escalation, "high"),
    (r"root.*cause.*found|diagnos|identified.*issue", TimelineEventType.diagnosis, "info"),
    (r"fix.*applied|mitigat|workaround|reroute.*shard|cleared.*cache", TimelineEventType.mitigation, "info"),
    (r"resolved|GREEN|recovered|back.*normal", TimelineEventType.resolution, "info"),
    (r"status.*page|customer.*notified|communicat.*outage", TimelineEventType.communication, "info"),
    (r"deploy|release|config.*change|rollout", TimelineEventType.action, "info"),
    (r"error|exception|timeout|circuit.*breaker|OOM|heap.*exceeded", TimelineEventType.error, "warning"),
    (r"slow.*query|high.*latency|performance.*degrad", TimelineEventType.anomaly, "warning"),
    (r"disk.*watermark|storage.*full|no.*space", TimelineEventType.anomaly, "warning"),
]


class OutageTimelineGenerator:
    """Generate incident timelines from Elasticsearch log events."""

    def __init__(self):
        self._timelines: dict[str, OutageTimeline] = {}
        self._timeline_counter = 0
        self._event_counter = 0

    def generate_timeline(self, incident_id: str, logs: list[dict], title: str = "") -> OutageTimeline:
        """Generate a complete outage timeline from raw log entries.

        Args:
            incident_id: Incident identifier
            logs: List of log dicts with keys: timestamp, message, source, index_name, node_name, severity
            title: Optional incident title
        """
        self._timeline_counter += 1
        timeline_id = f"TL-{self._timeline_counter:04d}"

        # Classify log entries into timeline events
        events = []
        for log in logs:
            event = self._classify_log(log)
            if event:
                events.append(event)

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)

        # Derive timeline metadata
        start_time = events[0].timestamp if events else time.time()
        end_time = events[-1].timestamp if events else None
        total_duration = (end_time - start_time) if end_time else 0

        # Identify phases
        phases = self._identify_phases(events)

        # Extract key moments
        key_moments = self._extract_key_moments(events)

        # Infer root cause
        root_cause = self._infer_root_cause(events)

        # Build impact summary
        impact_summary = self._build_impact_summary(events, phases)

        # Determine blast radius
        blast_radius = list(set(
            e.index_name for e in events if e.index_name
        ))

        # Auto-generate title if not provided
        if not title:
            trigger_events = [e for e in events if e.event_type == TimelineEventType.trigger]
            if trigger_events:
                title = f"Incident: {trigger_events[0].title}"
            else:
                title = f"Incident {incident_id}"

        timeline = OutageTimeline(
            timeline_id=timeline_id,
            incident_id=incident_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            total_duration_sec=round(total_duration, 1),
            events=events,
            phases=phases,
            key_moments=key_moments,
            root_cause=root_cause,
            impact_summary=impact_summary,
            blast_radius=blast_radius,
        )

        self._timelines[timeline_id] = timeline
        return timeline

    def _classify_log(self, log: dict) -> Optional[TimelineEvent]:
        """Classify a log entry into a timeline event type."""
        message = log.get("message", "")
        if not message:
            return None

        self._event_counter += 1
        event_type = TimelineEventType.anomaly
        severity = log.get("severity", "info")

        # Try pattern matching
        for pattern, etype, eseverity in LOG_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                event_type = etype
                if eseverity:
                    severity = eseverity
                break

        # Determine source
        source_str = log.get("source", "elasticsearch")
        try:
            source = TimelineSource(source_str)
        except ValueError:
            source = TimelineSource.elasticsearch

        return TimelineEvent(
            event_id=f"TE-{self._event_counter:04d}",
            timestamp=log.get("timestamp", time.time()),
            event_type=event_type,
            source=source,
            title=message[:120],
            description=message,
            severity=severity,
            index_name=log.get("index_name"),
            node_name=log.get("node_name"),
            metadata=log.get("metadata", {}),
        )

    def _identify_phases(self, events: list[TimelineEvent]) -> list[dict]:
        """Break the timeline into standard incident phases."""
        if not events:
            return []

        phases = []
        start = events[0].timestamp

        # Phase 1: Detection (trigger + detection events)
        detection_events = [e for e in events if e.event_type in (TimelineEventType.trigger, TimelineEventType.detection, TimelineEventType.anomaly)]
        if detection_events:
            det_start = detection_events[0].timestamp
            det_end = detection_events[-1].timestamp
            phases.append({
                "name": "Detection",
                "start_time": det_start,
                "end_time": det_end,
                "duration_sec": round(det_end - det_start, 1),
                "event_count": len(detection_events),
                "description": f"Initial signals detected — {len(detection_events)} events",
            })

        # Phase 2: Escalation & Diagnosis
        diag_events = [e for e in events if e.event_type in (TimelineEventType.escalation, TimelineEventType.diagnosis, TimelineEventType.error)]
        if diag_events:
            diag_start = diag_events[0].timestamp
            diag_end = diag_events[-1].timestamp
            phases.append({
                "name": "Diagnosis",
                "start_time": diag_start,
                "end_time": diag_end,
                "duration_sec": round(diag_end - diag_start, 1),
                "event_count": len(diag_events),
                "description": f"Root cause identified — {len(diag_events)} events",
            })

        # Phase 3: Mitigation
        mit_events = [e for e in events if e.event_type in (TimelineEventType.mitigation, TimelineEventType.action, TimelineEventType.communication)]
        if mit_events:
            mit_start = mit_events[0].timestamp
            mit_end = mit_events[-1].timestamp
            phases.append({
                "name": "Mitigation",
                "start_time": mit_start,
                "end_time": mit_end,
                "duration_sec": round(mit_end - mit_start, 1),
                "event_count": len(mit_events),
                "description": f"Fix applied — {len(mit_events)} events",
            })

        # Phase 4: Resolution
        res_events = [e for e in events if e.event_type == TimelineEventType.resolution]
        if res_events:
            res_start = res_events[0].timestamp
            res_end = res_events[-1].timestamp
            phases.append({
                "name": "Resolution",
                "start_time": res_start,
                "end_time": res_end,
                "duration_sec": round(res_end - res_start, 1),
                "event_count": len(res_events),
                "description": f"Service restored — {len(res_events)} events",
            })

        return phases

    def _extract_key_moments(self, events: list[TimelineEvent]) -> list[dict]:
        """Extract the most important moments from the timeline."""
        key_moments = []

        # First trigger
        triggers = [e for e in events if e.event_type == TimelineEventType.trigger]
        if triggers:
            key_moments.append({
                "label": "First Signal",
                "timestamp": triggers[0].timestamp,
                "event_id": triggers[0].event_id,
                "description": triggers[0].title,
            })

        # First alert
        detections = [e for e in events if e.event_type == TimelineEventType.detection]
        if detections:
            ttd = detections[0].timestamp - events[0].timestamp if events else 0
            key_moments.append({
                "label": f"Alert Fired (TTD: {ttd:.0f}s)",
                "timestamp": detections[0].timestamp,
                "event_id": detections[0].event_id,
                "description": detections[0].title,
            })

        # Root cause identified
        diagnoses = [e for e in events if e.event_type == TimelineEventType.diagnosis]
        if diagnoses:
            ttdiag = diagnoses[0].timestamp - events[0].timestamp if events else 0
            key_moments.append({
                "label": f"Root Cause Found (TTD: {ttdiag:.0f}s)",
                "timestamp": diagnoses[0].timestamp,
                "event_id": diagnoses[0].event_id,
                "description": diagnoses[0].title,
            })

        # Mitigation applied
        mitigations = [e for e in events if e.event_type == TimelineEventType.mitigation]
        if mitigations:
            ttm = mitigations[0].timestamp - events[0].timestamp if events else 0
            key_moments.append({
                "label": f"Mitigation Applied (TTM: {ttm:.0f}s)",
                "timestamp": mitigations[0].timestamp,
                "event_id": mitigations[0].event_id,
                "description": mitigations[0].title,
            })

        # Resolution
        resolutions = [e for e in events if e.event_type == TimelineEventType.resolution]
        if resolutions:
            ttr = resolutions[0].timestamp - events[0].timestamp if events else 0
            key_moments.append({
                "label": f"Resolved (TTR: {ttr:.0f}s)",
                "timestamp": resolutions[0].timestamp,
                "event_id": resolutions[0].event_id,
                "description": resolutions[0].title,
            })

        return key_moments

    def _infer_root_cause(self, events: list[TimelineEvent]) -> Optional[str]:
        """Infer the most likely root cause from timeline events."""
        # Look for the earliest trigger event
        triggers = [e for e in events if e.event_type == TimelineEventType.trigger]
        if triggers:
            return triggers[0].title

        # Fall back to first error
        errors = [e for e in events if e.event_type == TimelineEventType.error]
        if errors:
            return errors[0].title

        # Fall back to first anomaly
        anomalies = [e for e in events if e.event_type == TimelineEventType.anomaly]
        if anomalies:
            return anomalies[0].title

        return None

    def _build_impact_summary(self, events: list[TimelineEvent], phases: list[dict]) -> str:
        """Build a human-readable impact summary."""
        if not events:
            return "No events recorded"

        affected_indices = list(set(e.index_name for e in events if e.index_name))
        affected_nodes = list(set(e.node_name for e in events if e.node_name))
        critical_events = [e for e in events if e.severity == "critical"]

        parts = []
        if critical_events:
            parts.append(f"{len(critical_events)} critical events")
        if affected_indices:
            parts.append(f"affected {len(affected_indices)} index(es)")
        if affected_nodes:
            parts.append(f"on {len(affected_nodes)} node(s)")

        # Add phase durations
        for phase in phases:
            if phase["duration_sec"] > 0:
                mins = phase["duration_sec"] / 60
                parts.append(f"{phase['name']}: {mins:.1f}min")

        return " | ".join(parts) if parts else "Impact assessment pending"

    def get_timeline(self, timeline_id: str) -> Optional[OutageTimeline]:
        """Retrieve a stored timeline."""
        return self._timelines.get(timeline_id)

    def list_timelines(self) -> list[OutageTimeline]:
        """List all stored timelines."""
        return sorted(self._timelines.values(), key=lambda t: t.start_time, reverse=True)

    def generate_demo_timeline(self, incident_id: str = "INC-DEMO-001") -> OutageTimeline:
        """Generate a realistic demo timeline for hackathon presentation."""
        base_time = time.time() - 3600  # 1 hour ago

        demo_logs = [
            {"timestamp": base_time, "message": "Index orders-2026 went RED — 3 unassigned primary shards detected", "source": "elasticsearch", "index_name": "orders-2026", "severity": "critical"},
            {"timestamp": base_time + 30, "message": "Disk watermark flood_stage exceeded on data-node-3 (93% full)", "source": "elasticsearch", "node_name": "data-node-3", "severity": "high"},
            {"timestamp": base_time + 60, "message": "Alert fired: Critical — orders-2026 index RED, checkout impacted", "source": "alerts", "severity": "high"},
            {"timestamp": base_time + 120, "message": "On-call engineer paged via PagerDuty", "source": "alerts", "severity": "high"},
            {"timestamp": base_time + 300, "message": "Engineer acknowledges page — begins investigation", "source": "chat", "severity": "info"},
            {"timestamp": base_time + 420, "message": "Slow queries detected on payments-2026 index — p99 latency > 5s", "source": "elasticsearch", "index_name": "payments-2026", "severity": "warning"},
            {"timestamp": base_time + 600, "message": "Root cause identified: data-node-3 disk full causing shard allocation failures", "source": "datapulse", "severity": "info"},
            {"timestamp": base_time + 720, "message": "Status page updated: Investigating checkout issues", "source": "chat", "severity": "info"},
            {"timestamp": base_time + 900, "message": "Mitigation: Cleared old log indices to free disk space on data-node-3", "source": "datapulse", "node_name": "data-node-3", "severity": "info"},
            {"timestamp": base_time + 960, "message": "Rerouting unassigned shards — shard allocation recovered", "source": "elasticsearch", "index_name": "orders-2026", "severity": "info"},
            {"timestamp": base_time + 1080, "message": "Index orders-2026 recovered to GREEN", "source": "elasticsearch", "index_name": "orders-2026", "severity": "info"},
            {"timestamp": base_time + 1140, "message": "Index payments-2026 latency returned to normal (< 200ms)", "source": "elasticsearch", "index_name": "payments-2026", "severity": "info"},
            {"timestamp": base_time + 1200, "message": "Incident resolved — all indices GREEN, checkout operational", "source": "datapulse", "severity": "info"},
            {"timestamp": base_time + 1500, "message": "Status page updated: Resolved — checkout fully operational", "source": "chat", "severity": "info"},
        ]

        return self.generate_timeline(
            incident_id=incident_id,
            logs=demo_logs,
            title="Orders Index RED — Disk Full on data-node-3",
        )
