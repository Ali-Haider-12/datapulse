"""Tests for Outage Timeline Generator."""

import pytest
import time
from app.services.outage_timeline import (
    OutageTimelineGenerator, OutageTimeline, TimelineEvent,
    TimelineEventType, TimelineSource
)


@pytest.fixture
def generator():
    return OutageTimelineGenerator()


@pytest.fixture
def sample_logs():
    base = time.time() - 3600
    return [
        {"timestamp": base, "message": "Index orders-2026 went RED — unassigned primary shards", "source": "elasticsearch", "index_name": "orders-2026", "severity": "critical"},
        {"timestamp": base + 60, "message": "Alert fired: Critical — orders index RED", "source": "alerts", "severity": "high"},
        {"timestamp": base + 120, "message": "On-call engineer paged", "source": "alerts", "severity": "high"},
        {"timestamp": base + 600, "message": "Root cause identified: disk full on data-node-3", "source": "datapulse", "severity": "info"},
        {"timestamp": base + 900, "message": "Mitigation: Cleared old indices, freed disk space", "source": "datapulse", "severity": "info"},
        {"timestamp": base + 1200, "message": "Index orders-2026 recovered to GREEN", "source": "elasticsearch", "index_name": "orders-2026", "severity": "info"},
        {"timestamp": base + 1500, "message": "Incident resolved — all systems operational", "source": "datapulse", "severity": "info"},
    ]


class TestGenerateTimeline:
    def test_generates_timeline(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        assert timeline.timeline_id.startswith("TL-")
        assert timeline.incident_id == "INC-001"
        assert len(timeline.events) == len(sample_logs)

    def test_events_sorted_by_time(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        timestamps = [e.timestamp for e in timeline.events]
        assert timestamps == sorted(timestamps)

    def test_duration_calculated(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        assert timeline.total_duration_sec > 0

    def test_root_cause_inferred(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        assert timeline.root_cause is not None
        assert "RED" in timeline.root_cause or "unassigned" in timeline.root_cause

    def test_blast_radius(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        assert "orders-2026" in timeline.blast_radius

    def test_impact_summary(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        assert timeline.impact_summary != ""
        assert len(timeline.impact_summary) > 10

    def test_auto_title_from_trigger(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs, title="")
        assert "RED" in timeline.title or "unassigned" in timeline.title or "Incident" in timeline.title

    def test_empty_logs(self, generator):
        timeline = generator.generate_timeline("INC-EMPTY", [])
        assert timeline.timeline_id.startswith("TL-")
        assert len(timeline.events) == 0


class TestPhases:
    def test_phases_detected(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        assert len(timeline.phases) >= 1

    def test_phase_structure(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        for phase in timeline.phases:
            assert "name" in phase
            assert "duration_sec" in phase
            assert "event_count" in phase
            assert phase["duration_sec"] >= 0

    def test_detection_phase(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        detection_phases = [p for p in timeline.phases if p["name"] == "Detection"]
        assert len(detection_phases) >= 1

    def test_mitigation_phase(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        mitigation_phases = [p for p in timeline.phases if p["name"] == "Mitigation"]
        assert len(mitigation_phases) >= 1


class TestKeyMoments:
    def test_key_moments_extracted(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        assert len(timeline.key_moments) >= 1

    def test_first_signal_moment(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        first_signals = [km for km in timeline.key_moments if km["label"] == "First Signal"]
        assert len(first_signals) >= 1

    def test_resolved_moment(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-001", sample_logs)
        resolved = [km for km in timeline.key_moments if "Resolved" in km["label"]]
        assert len(resolved) >= 1


class TestLogClassification:
    def test_red_classified_as_trigger(self, generator):
        logs = [{"timestamp": time.time(), "message": "Index went RED — shards unassigned", "source": "elasticsearch", "severity": "critical"}]
        timeline = generator.generate_timeline("INC-CLASS", logs)
        trigger_events = [e for e in timeline.events if e.event_type == TimelineEventType.trigger]
        assert len(trigger_events) >= 1

    def test_alert_classified_as_detection(self, generator):
        logs = [{"timestamp": time.time(), "message": "Alert fired: threshold exceeded", "source": "alerts", "severity": "high"}]
        timeline = generator.generate_timeline("INC-CLASS", logs)
        detection_events = [e for e in timeline.events if e.event_type == TimelineEventType.detection]
        assert len(detection_events) >= 1

    def test_mitigation_classified(self, generator):
        logs = [{"timestamp": time.time(), "message": "Fix applied: rerouted shards, cache cleared", "source": "datapulse", "severity": "info"}]
        timeline = generator.generate_timeline("INC-CLASS", logs)
        mit_events = [e for e in timeline.events if e.event_type == TimelineEventType.mitigation]
        assert len(mit_events) >= 1


class TestDemoTimeline:
    def test_demo_generates(self, generator):
        timeline = generator.generate_demo_timeline()
        assert timeline.timeline_id.startswith("TL-")
        assert len(timeline.events) == 14
        assert timeline.total_duration_sec > 0

    def test_demo_has_phases(self, generator):
        timeline = generator.generate_demo_timeline()
        assert len(timeline.phases) >= 2

    def test_demo_has_key_moments(self, generator):
        timeline = generator.generate_demo_timeline()
        assert len(timeline.key_moments) >= 2

    def test_demo_root_cause(self, generator):
        timeline = generator.generate_demo_timeline()
        assert timeline.root_cause is not None

    def test_demo_blast_radius(self, generator):
        timeline = generator.generate_demo_timeline()
        assert "orders-2026" in timeline.blast_radius


class TestStoreAndRetrieve:
    def test_get_timeline(self, generator, sample_logs):
        timeline = generator.generate_timeline("INC-STORE", sample_logs)
        retrieved = generator.get_timeline(timeline.timeline_id)
        assert retrieved is not None
        assert retrieved.timeline_id == timeline.timeline_id

    def test_list_timelines(self, generator, sample_logs):
        generator.generate_timeline("INC-1", sample_logs)
        generator.generate_timeline("INC-2", sample_logs)
        timelines = generator.list_timelines()
        assert len(timelines) == 2

    def test_nonexistent_timeline(self, generator):
        assert generator.get_timeline("TL-9999") is None
