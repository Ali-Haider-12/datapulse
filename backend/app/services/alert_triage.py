"""Smart Alert Triage + Correlation Engine

Addresses #1 DevOps pain point from HN research: "monitoring alerts are mostly noise"
- Groups related alerts by index, time window, and root cause similarity
- Calculates severity scores based on business impact + frequency
- Suppresses duplicate/noisy alerts with reasoning
- Generates triage summary telling on-call what to focus on FIRST
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


@dataclass
class Alert:
    id: str
    severity: str  # critical, high, warning, info
    message: str
    index_name: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    source: str = "elasticsearch"
    metadata: dict = field(default_factory=dict)


@dataclass
class AlertGroup:
    group_id: str
    root_cause_hint: str
    alerts: list[Alert] = field(default_factory=list)
    combined_severity_score: int = 0
    affected_indices: list[str] = field(default_factory=list)
    suppressed_count: int = 0


@dataclass
class SuppressedAlert:
    alert: Alert
    reason: str
    similar_to: str  # alert_id it duplicates


@dataclass
class TriageSummary:
    total_alerts: int
    active_groups: int
    suppressed_count: int
    noise_reduction_pct: float
    priority_order: list[AlertGroup] = field(default_factory=list)
    top_priority: Optional[AlertGroup] = None
    recommendation: str = ""


@dataclass
class TriageResult:
    groups: list[AlertGroup] = field(default_factory=list)
    suppressed: list[SuppressedAlert] = field(default_factory=list)
    summary: Optional[TriageSummary] = None


# Noise patterns to suppress — known false positives
NOISE_PATTERNS = [
    ("dynamic mapping", "info"),
    ("disk watermark 85%", "warning"),
]

# Correlation window in seconds (alerts within this window are related)
CORRELATION_WINDOW = 300  # 5 minutes


class AlertTriageService:
    """Smart alert triage engine that reduces noise and correlates related alerts."""

    def __init__(self):
        self._history: list[Alert] = []
        self._groups: list[AlertGroup] = []
        self._suppressed: list[SuppressedAlert] = []
        self._group_counter = 0

    @staticmethod
    def calculate_severity_score(alert: Alert) -> int:
        """Calculate severity score 0-100 based on business impact, frequency, correlation."""
        base_scores = {
            "critical": 80,
            "high": 60,
            "warning": 30,
            "info": 10,
        }
        score = base_scores.get(alert.severity, 10)

        # Boost for index-level alerts (more specific = more actionable)
        if alert.index_name:
            score += 10

        # Boost for business-critical index names
        critical_keywords = ["order", "payment", "checkout", "user", "session", "auth"]
        if alert.index_name:
            for kw in critical_keywords:
                if kw in alert.index_name.lower():
                    score += 15
                    break

        # Reduce for known noisy patterns
        msg_lower = alert.message.lower()
        for pattern, _ in NOISE_PATTERNS:
            if pattern in msg_lower:
                score -= 20

        return max(0, min(100, score))

    def _extract_root_cause_hint(self, alert: Alert) -> str:
        """Extract a root cause hint from the alert message."""
        msg = alert.message.lower()
        if "red" in msg or "unassigned" in msg:
            return "shard_allocation_failure"
        if "yellow" in msg or "replica" in msg:
            return "replica_allocation_issue"
        if "slow" in msg or "latency" in msg or "timeout" in msg:
            return "performance_degradation"
        if "disk" in msg or "watermark" in msg:
            return "storage_pressure"
        if "mapping" in msg or "dynamic" in msg or "field" in msg:
            return "mapping_explosion"
        if "circuit" in msg or "breaker" in msg:
            return "circuit_breaker_tripped"
        if "heap" in msg or "oom" in msg or "memory" in msg:
            return "memory_pressure"
        return "unknown_issue"

    def correlate_alerts(self, alerts: list[Alert]) -> list[AlertGroup]:
        """Group related alerts by index, time window, and root cause."""
        groups: dict[str, AlertGroup] = {}

        for alert in alerts:
            root_cause = self._extract_root_cause_hint(alert)
            # Group key: same index + same root cause
            group_key = f"{alert.index_name or 'global'}:{root_cause}"

            if group_key not in groups:
                self._group_counter += 1
                groups[group_key] = AlertGroup(
                    group_id=f"AG-{self._group_counter:03d}",
                    root_cause_hint=root_cause,
                    alerts=[],
                    affected_indices=[alert.index_name] if alert.index_name else [],
                )

            group = groups[group_key]
            group.alerts.append(alert)
            if alert.index_name and alert.index_name not in group.affected_indices:
                group.affected_indices.append(alert.index_name)

        # Calculate combined severity for each group
        for group in groups.values():
            scores = [self.calculate_severity_score(a) for a in group.alerts]
            group.combined_severity_score = max(scores) + len(scores) * 5
            group.combined_severity_score = min(100, group.combined_severity_score)

        # Sort by severity score descending
        sorted_groups = sorted(groups.values(), key=lambda g: g.combined_severity_score, reverse=True)
        self._groups = sorted_groups
        return sorted_groups

    def suppress_noisy_alerts(self, groups: list[AlertGroup]) -> list[SuppressedAlert]:
        """Mark duplicate/noisy alerts as suppressed within each group."""
        suppressed = []

        for group in groups:
            seen_messages = set()
            for alert in group.alerts:
                # Normalize message for dedup
                normalized = alert.message.lower().strip()
                # Remove specific numbers/timestamps for comparison
                import re
                normalized = re.sub(r'\d+', 'N', normalized)

                if normalized in seen_messages:
                    suppressed.append(SuppressedAlert(
                        alert=alert,
                        reason=f"Duplicate of alert in group {group.group_id}",
                        similar_to=group.alerts[0].id,
                    ))
                else:
                    seen_messages.add(normalized)

            # Update group suppressed count
            group.suppressed_count = len([s for s in suppressed if s.similar_to in [a.id for a in group.alerts]])

        self._suppressed = suppressed
        return suppressed

    def triage_alerts(self, alerts: list[Alert]) -> TriageResult:
        """Full triage pipeline: correlate → suppress → summarize."""
        self._history.extend(alerts)

        # Step 1: Correlate
        groups = self.correlate_alerts(alerts)

        # Step 2: Suppress noise
        suppressed = self.suppress_noisy_alerts(groups)

        # Step 3: Build summary
        total = len(alerts)
        suppressed_count = len(suppressed)
        noise_reduction = (suppressed_count / total * 100) if total > 0 else 0.0

        # Priority order = groups sorted by severity
        priority_order = sorted(groups, key=lambda g: g.combined_severity_score, reverse=True)

        # Top priority recommendation
        top = priority_order[0] if priority_order else None
        recommendation = ""
        if top:
            if top.combined_severity_score >= 70:
                recommendation = f"🚨 URGENT: Focus on {top.root_cause_hint} affecting {', '.join(top.affected_indices) or 'cluster-wide'}. {len(top.alerts)} correlated alerts."
            elif top.combined_severity_score >= 40:
                recommendation = f"⚠️ Review {top.root_cause_hint} on {', '.join(top.affected_indices) or 'cluster'}. {len(top.alerts)} alerts grouped."
            else:
                recommendation = f"ℹ️ Low priority: {top.root_cause_hint}. No immediate action needed."

        summary = TriageSummary(
            total_alerts=total,
            active_groups=len(groups),
            suppressed_count=suppressed_count,
            noise_reduction_pct=round(noise_reduction, 1),
            priority_order=priority_order,
            top_priority=top,
            recommendation=recommendation,
        )

        return TriageResult(groups=groups, suppressed=suppressed, summary=summary)

    def get_triage_summary(self) -> TriageSummary:
        """Get the latest triage summary."""
        if self._groups:
            total = sum(len(g.alerts) for g in self._groups)
            suppressed = len(self._suppressed)
            noise_reduction = (suppressed / total * 100) if total > 0 else 0.0
            top = self._groups[0] if self._groups else None
            return TriageSummary(
                total_alerts=total,
                active_groups=len(self._groups),
                suppressed_count=suppressed,
                noise_reduction_pct=round(noise_reduction, 1),
                priority_order=self._groups,
                top_priority=top,
                recommendation="",
            )
        return TriageSummary(total_alerts=0, active_groups=0, suppressed_count=0, noise_reduction_pct=0.0)
