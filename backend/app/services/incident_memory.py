"""Cross-Incident Memory Layer

Inspired by RobinRelay (HN: "Slack-native memory layer for noisy alerts") and Sentō article
("persistent memory across systems is the layer that actually matters").

Stores every incident, diagnosis, remediation, and outcome.
When new incidents occur, searches for similar past incidents.
Returns "last time this happened" context + recurring patterns.
"""

from __future__ import annotations
import json
import time
import os
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import Counter


@dataclass
class MemoryIncident:
    memory_id: str
    title: str
    severity: str
    index_name: Optional[str]
    root_cause: str
    impact: str
    remediation: str
    resolution_time_min: float
    outcome: str  # resolved, mitigated, escalated
    timestamp: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)


@dataclass
class SimilarIncident:
    incident: MemoryIncident
    similarity_score: float  # 0-1
    match_reasons: list[str] = field(default_factory=list)


@dataclass
class IncidentPattern:
    pattern_id: str
    description: str
    frequency: int
    affected_indices: list[str] = field(default_factory=list)
    avg_resolution_time: float = 0.0
    common_root_cause: str = ""
    first_seen: float = 0.0
    last_seen: float = 0.0


@dataclass
class ResolutionStats:
    total_incidents: int = 0
    avg_resolution_time: float = 0.0
    resolution_rate: float = 0.0  # % resolved
    top_root_causes: list[tuple[str, int]] = field(default_factory=list)
    recurring_incidents: int = 0
    mttr_by_severity: dict[str, float] = field(default_factory=dict)


class IncidentMemoryService:
    """Persistent memory layer for cross-incident context."""

    MEMORY_DIR = os.environ.get("DATA_DIR", "/tmp/datapulse/data")
    MEMORY_FILE = "incident_memory.json"

    def __init__(self, memory_dir: Optional[str] = None):
        self._dir = memory_dir or self.MEMORY_DIR
        self._file = os.path.join(self._dir, self.MEMORY_FILE)
        self._incidents: list[MemoryIncident] = []
        self._counter = 0
        os.makedirs(self._dir, exist_ok=True)
        self._load()

    def _load(self):
        """Load incidents from disk."""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r") as f:
                    data = json.load(f)
                self._counter = data.get("counter", 0)
                self._incidents = [MemoryIncident(**inc) for inc in data.get("incidents", [])]
            except (json.JSONDecodeError, KeyError):
                self._incidents = []

    def _save(self):
        """Persist incidents to disk."""
        data = {
            "counter": self._counter,
            "incidents": [asdict(inc) for inc in self._incidents],
        }
        with open(self._file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def store_incident(self, incident_data: dict) -> str:
        """Store an incident in memory. Returns memory_id."""
        self._counter += 1
        memory_id = f"MEM-{self._counter:04d}"

        incident = MemoryIncident(
            memory_id=memory_id,
            title=incident_data.get("title", "Unknown Incident"),
            severity=incident_data.get("severity", "medium"),
            index_name=incident_data.get("index_name"),
            root_cause=incident_data.get("root_cause", "Unknown"),
            impact=incident_data.get("impact", ""),
            remediation=incident_data.get("remediation", ""),
            resolution_time_min=incident_data.get("resolution_time_min", 0.0),
            outcome=incident_data.get("outcome", "resolved"),
            tags=incident_data.get("tags", []),
        )

        self._incidents.append(incident)
        self._save()
        return memory_id

    def search_similar(self, query: dict) -> list[SimilarIncident]:
        """Search for similar past incidents based on index, root cause, severity."""
        query_index = query.get("index_name", "").lower()
        query_root = query.get("root_cause", "").lower()
        query_severity = query.get("severity", "").lower()
        query_tags = set(t.lower() for t in query.get("tags", []))

        results = []
        for inc in self._incidents:
            score = 0.0
            reasons = []

            # Index match (highest weight)
            if query_index and inc.index_name:
                if query_index == inc.index_name.lower():
                    score += 0.4
                    reasons.append(f"Same index: {inc.index_name}")
                elif query_index in inc.index_name.lower() or inc.index_name.lower() in query_index:
                    score += 0.2
                    reasons.append(f"Related index: {inc.index_name}")

            # Root cause match
            if query_root and inc.root_cause:
                inc_root = inc.root_cause.lower()
                if query_root == inc_root:
                    score += 0.35
                    reasons.append(f"Same root cause: {inc.root_cause}")
                elif any(word in inc_root for word in query_root.split() if len(word) > 3):
                    score += 0.15
                    reasons.append(f"Similar root cause: {inc.root_cause}")

            # Severity match
            if query_severity and query_severity == inc.severity.lower():
                score += 0.1
                reasons.append(f"Same severity: {inc.severity}")

            # Tag overlap
            if query_tags:
                inc_tags = set(t.lower() for t in inc.tags)
                overlap = query_tags & inc_tags
                if overlap:
                    score += 0.15 * (len(overlap) / max(len(query_tags), 1))
                    reasons.append(f"Shared tags: {', '.join(overlap)}")

            if score > 0.1:
                results.append(SimilarIncident(
                    incident=inc,
                    similarity_score=round(min(score, 1.0), 2),
                    match_reasons=reasons,
                ))

        # Sort by similarity score
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:10]  # Top 10 matches

    def get_patterns(self) -> list[IncidentPattern]:
        """Detect recurring incident patterns."""
        if not self._incidents:
            return []

        # Group by root cause + index combination
        pattern_map: dict[str, list[MemoryIncident]] = {}
        for inc in self._incidents:
            key = f"{inc.root_cause}|{inc.index_name or 'global'}"
            if key not in pattern_map:
                pattern_map[key] = []
            pattern_map[key].append(inc)

        patterns = []
        pattern_counter = 0
        for key, incidents in pattern_map.items():
            if len(incidents) < 1:
                continue
            pattern_counter += 1
            root_cause, index_name = key.split("|", 1)
            indices = list(set(inc.index_name for inc in incidents if inc.index_name))
            resolution_times = [inc.resolution_time_min for inc in incidents if inc.resolution_time_min > 0]
            avg_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0

            patterns.append(IncidentPattern(
                pattern_id=f"PAT-{pattern_counter:03d}",
                description=f"{root_cause} on {index_name}" if index_name != "global" else f"{root_cause} (cluster-wide)",
                frequency=len(incidents),
                affected_indices=indices,
                avg_resolution_time=round(avg_time, 1),
                common_root_cause=root_cause,
                first_seen=min(inc.timestamp for inc in incidents),
                last_seen=max(inc.timestamp for inc in incidents),
            ))

        # Sort by frequency
        patterns.sort(key=lambda p: p.frequency, reverse=True)
        return patterns

    def get_resolution_stats(self) -> ResolutionStats:
        """Get resolution statistics across all incidents."""
        if not self._incidents:
            return ResolutionStats()

        total = len(self._incidents)
        resolved = [inc for inc in self._incidents if inc.outcome == "resolved"]
        resolution_times = [inc.resolution_time_min for inc in self._incidents if inc.resolution_time_min > 0]
        avg_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0.0

        # Top root causes
        cause_counter = Counter(inc.root_cause for inc in self._incidents)
        top_causes = cause_counter.most_common(5)

        # Recurring incidents (same root cause seen 2+ times)
        recurring = sum(1 for count in cause_counter.values() if count >= 2)

        # MTTR by severity
        mttr_by_sev: dict[str, list[float]] = {}
        for inc in self._incidents:
            if inc.resolution_time_min > 0:
                mttr_by_sev.setdefault(inc.severity, []).append(inc.resolution_time_min)

        mttr_dict = {
            sev: round(sum(times) / len(times), 1)
            for sev, times in mttr_by_sev.items()
        }

        return ResolutionStats(
            total_incidents=total,
            avg_resolution_time=round(avg_time, 1),
            resolution_rate=round(len(resolved) / total * 100, 1) if total > 0 else 0,
            top_root_causes=top_causes,
            recurring_incidents=recurring,
            mttr_by_severity=mttr_dict,
        )

    def get_recent(self, limit: int = 20) -> list[MemoryIncident]:
        """Get recent incidents sorted by timestamp."""
        sorted_incidents = sorted(self._incidents, key=lambda x: x.timestamp, reverse=True)
        return sorted_incidents[:limit]

    def seed_demo_data(self):
        """Seed with demo data for hackathon demo."""
        demo_incidents = [
            {
                "title": "Index orders-2026 went RED",
                "severity": "critical",
                "index_name": "orders-2026",
                "root_cause": "shard_allocation_failure",
                "impact": "23% checkout failures, $2,850/hr revenue at risk",
                "remediation": "Reroute unassigned shards, increase replica count",
                "resolution_time_min": 47.0,
                "outcome": "resolved",
                "tags": ["shard", "red-index", "revenue-impact"],
            },
            {
                "title": "Slow queries on products index",
                "severity": "high",
                "index_name": "products",
                "impact": "Product catalog p99 > 800ms",
                "root_cause": "performance_degradation",
                "remediation": "Clear cache, optimize field mapping",
                "resolution_time_min": 12.0,
                "outcome": "resolved",
                "tags": ["slow-query", "cache", "products"],
            },
            {
                "title": "YELLOW index logs-2026-05",
                "severity": "warning",
                "index_name": "logs-2026-05",
                "root_cause": "replica_allocation_issue",
                "impact": "Reduced redundancy for logging data",
                "remediation": "Increase replica count to 1",
                "resolution_time_min": 5.0,
                "outcome": "resolved",
                "tags": ["yellow", "replica", "logs"],
            },
            {
                "title": "Disk watermark exceeded on data-node-3",
                "severity": "high",
                "index_name": None,
                "root_cause": "storage_pressure",
                "impact": "Indexing blocked on affected node",
                "remediation": "Deleted old indices (pre-2025), cleared disk space",
                "resolution_time_min": 23.0,
                "outcome": "resolved",
                "tags": ["disk", "watermark", "storage"],
            },
            {
                "title": "Mapping explosion on user-events index",
                "severity": "medium",
                "index_name": "user-events",
                "root_cause": "mapping_explosion",
                "impact": "150+ dynamic fields causing high heap usage",
                "remediation": "Frozen dynamic mapping, planned reindex with explicit mapping",
                "resolution_time_min": 35.0,
                "outcome": "mitigated",
                "tags": ["mapping", "dynamic", "heap"],
            },
        ]

        for inc_data in demo_incidents:
            self.store_incident(inc_data)
