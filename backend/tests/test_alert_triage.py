"""Tests for Smart Alert Triage + Correlation Engine"""

import pytest
import time
from app.services.alert_triage import (
    AlertTriageService, Alert, AlertGroup, TriageResult,
    TriageSummary, SuppressedAlert
)


@pytest.fixture
def service():
    return AlertTriageService()


@pytest.fixture
def sample_alerts():
    return [
        Alert(id="a1", severity="critical", message="Index orders-2026 is RED — unassigned primary shards", index_name="orders-2026"),
        Alert(id="a2", severity="warning", message="Index logs-2026-05 is YELLOW — replica unassigned", index_name="logs-2026-05"),
        Alert(id="a3", severity="warning", message="Index logs-2026-05 is YELLOW — replica unassigned (duplicate)", index_name="logs-2026-05"),
        Alert(id="a4", severity="info", message="Index products has 150 dynamic fields", index_name="products"),
        Alert(id="a5", severity="high", message="Slow queries detected on products index — p99 latency > 800ms", index_name="products"),
        Alert(id="a6", severity="critical", message="Disk watermark exceeded on data-node-3", index_name=None),
        Alert(id="a7", severity="info", message="Dynamic mapping warning on user-events — 200+ fields", index_name="user-events"),
    ]


class TestSeverityScoring:
    def test_critical_alert_high_score(self):
        alert = Alert(id="t1", severity="critical", message="Index down", index_name="orders-2026")
        score = AlertTriageService.calculate_severity_score(alert)
        assert score >= 80  # Critical + business index

    def test_info_alert_low_score(self):
        alert = Alert(id="t2", severity="info", message="Some info", index_name=None)
        score = AlertTriageService.calculate_severity_score(alert)
        assert score <= 30

    def test_business_index_boost(self):
        alert_payment = Alert(id="t3", severity="high", message="Issue", index_name="payment-gateway")
        alert_logs = Alert(id="t4", severity="high", message="Issue", index_name="logs-dev")
        score_payment = AlertTriageService.calculate_severity_score(alert_payment)
        score_logs = AlertTriageService.calculate_severity_score(alert_logs)
        assert score_payment > score_logs

    def test_noisy_pattern_reduces_score(self):
        alert_noisy = Alert(id="t5", severity="warning", message="dynamic mapping detected on index", index_name="test")
        alert_normal = Alert(id="t6", severity="warning", message="replica allocation failed", index_name="test")
        score_noisy = AlertTriageService.calculate_severity_score(alert_noisy)
        score_normal = AlertTriageService.calculate_severity_score(alert_normal)
        assert score_noisy < score_normal

    def test_score_bounded_0_100(self):
        for sev in ["critical", "high", "warning", "info"]:
            alert = Alert(id=f"b_{sev}", severity=sev, message="test", index_name="orders-payment-checkout")
            score = AlertTriageService.calculate_severity_score(alert)
            assert 0 <= score <= 100


class TestCorrelation:
    def test_correlate_by_index_and_root_cause(self, service, sample_alerts):
        groups = service.correlate_alerts(sample_alerts)
        assert len(groups) >= 1
        # Each group should have alerts
        total_alerts = sum(len(g.alerts) for g in groups)
        assert total_alerts == len(sample_alerts)

    def test_same_index_same_cause_grouped(self, service):
        alerts = [
            Alert(id="c1", severity="warning", message="Index orders-2026 YELLOW — replica issue", index_name="orders-2026"),
            Alert(id="c2", severity="warning", message="Index orders-2026 YELLOW — another replica issue", index_name="orders-2026"),
        ]
        groups = service.correlate_alerts(alerts)
        # Both should be in the same group (same index + same root cause)
        assert len(groups) == 1
        assert len(groups[0].alerts) == 2

    def test_different_root_causes_different_groups(self, service):
        alerts = [
            Alert(id="d1", severity="critical", message="Index orders-2026 RED — unassigned shards", index_name="orders-2026"),
            Alert(id="d2", severity="warning", message="Index orders-2026 slow queries detected", index_name="orders-2026"),
        ]
        groups = service.correlate_alerts(alerts)
        assert len(groups) == 2  # shard_allocation_failure vs performance_degradation

    def test_groups_sorted_by_severity(self, service, sample_alerts):
        groups = service.correlate_alerts(sample_alerts)
        if len(groups) >= 2:
            assert groups[0].combined_severity_score >= groups[1].combined_severity_score


class TestSuppression:
    def test_duplicate_alerts_suppressed(self, service):
        alerts = [
            Alert(id="s1", severity="warning", message="Index logs-2026-05 is YELLOW", index_name="logs-2026-05"),
            Alert(id="s2", severity="warning", message="Index logs-2026-05 is YELLOW", index_name="logs-2026-05"),
            Alert(id="s3", severity="warning", message="Index logs-2026-05 is YELLOW again", index_name="logs-2026-05"),
        ]
        groups = service.correlate_alerts(alerts)
        suppressed = service.suppress_noisy_alerts(groups)
        assert len(suppressed) >= 1

    def test_unique_alerts_not_suppressed(self, service):
        alerts = [
            Alert(id="u1", severity="critical", message="RED index — primary shards lost", index_name="orders"),
            Alert(id="u2", severity="warning", message="YELLOW index — replica unassigned", index_name="logs"),
        ]
        groups = service.correlate_alerts(alerts)
        suppressed = service.suppress_noisy_alerts(groups)
        assert len(suppressed) == 0  # Different messages


class TestTriagePipeline:
    def test_full_triage(self, service, sample_alerts):
        result = service.triage_alerts(sample_alerts)
        assert isinstance(result, TriageResult)
        assert result.summary is not None
        assert result.summary.total_alerts == len(sample_alerts)
        assert result.summary.active_groups >= 1
        assert result.summary.noise_reduction_pct >= 0

    def test_triage_empty_alerts(self, service):
        result = service.triage_alerts([])
        assert result.summary.total_alerts == 0
        assert result.summary.active_groups == 0
        assert result.summary.noise_reduction_pct == 0.0

    def test_triage_generates_recommendation(self, service, sample_alerts):
        result = service.triage_alerts(sample_alerts)
        assert result.summary.recommendation != ""

    def test_triage_priority_order(self, service, sample_alerts):
        result = service.triage_alerts(sample_alerts)
        if len(result.groups) >= 2:
            assert result.summary.priority_order[0].combined_severity_score >= result.summary.priority_order[1].combined_severity_score

    def test_noise_reduction_calculation(self, service):
        # 2 identical + 1 unique = 33% noise reduction
        alerts = [
            Alert(id="n1", severity="warning", message="YELLOW replica issue on logs", index_name="logs"),
            Alert(id="n2", severity="warning", message="YELLOW replica issue on logs", index_name="logs"),
            Alert(id="n3", severity="critical", message="RED primary shard failure", index_name="orders"),
        ]
        result = service.triage_alerts(alerts)
        assert result.summary.suppressed_count >= 1
        assert result.summary.noise_reduction_pct > 0

    def test_get_triage_summary(self, service, sample_alerts):
        service.triage_alerts(sample_alerts)
        summary = service.get_triage_summary()
        assert summary.total_alerts > 0
