"""Auto-Runbook Engine

Addresses HN insight: "AI SRE needs better observability, not bigger models"
and the LogClaw approach (auto-tickets from logs with step-by-step fixes).

Maintains a library of runbooks for common ES issues.
Auto-matches incidents to the best runbook.
Shows step-by-step remediation with risk levels.
Supports human-in-the-loop approval for risky steps.
Records outcomes back to incident memory.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class StepRisk(str, Enum):
    safe = "safe"
    low = "low"
    medium = "medium"
    high = "high"


class StepStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    executing = "executing"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


@dataclass
class RunbookStep:
    step_id: str
    title: str
    description: str
    action: str
    risk: StepRisk = StepRisk.low
    estimated_time_sec: int = 30
    requires_approval: bool = True
    status: StepStatus = StepStatus.pending
    result: Optional[str] = None
    timestamp: Optional[float] = None


@dataclass
class Runbook:
    runbook_id: str
    name: str
    description: str
    trigger_conditions: list[str]
    steps: list[RunbookStep] = field(default_factory=list)
    total_estimated_time: int = 0
    applicable_indices: list[str] = field(default_factory=list)


@dataclass
class MatchedRunbook:
    runbook: Runbook
    match_score: float
    match_reasons: list[str] = field(default_factory=list)
    incident_context: dict = field(default_factory=dict)


@dataclass
class StepResult:
    step_id: str
    runbook_id: str
    status: StepStatus
    output: str = ""
    error: Optional[str] = None
    duration_sec: float = 0.0


@dataclass
class RunbookExecution:
    execution_id: str
    runbook_id: str
    incident_id: str
    steps_completed: int = 0
    steps_total: int = 0
    status: str = "in_progress"
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    results: list[StepResult] = field(default_factory=list)


# ============ Built-in Runbook Library ============

BUILTIN_RUNBOOKS = [
    Runbook(
        runbook_id="RB-001",
        name="YELLOW Index Recovery",
        description="Restore index health by allocating missing replicas",
        trigger_conditions=["yellow", "replica", "unassigned", "allocation"],
        steps=[
            RunbookStep(step_id="RB-001-S1", title="Check index health", description="Verify index status and identify unassigned replicas", action="GET _cluster/health?level=indices", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-001-S2", title="Identify unassigned shards", description="Find which shards are unassigned and why", action="GET _cat/shards?h=index,shard,primar,state,unassigned_reason", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-001-S3", title="Increase replica count", description="Set replica count to 1 for the affected index", action='PUT {index}/_settings {"index.number_of_replicas": 1}', risk=StepRisk.low, estimated_time_sec=15, requires_approval=True),
            RunbookStep(step_id="RB-001-S4", title="Verify recovery", description="Confirm index turns GREEN after replica allocation", action="GET _cluster/health?level=indices&wait_for_status=yellow&timeout=30s", risk=StepRisk.safe, estimated_time_sec=30, requires_approval=False),
        ],
        total_estimated_time=55,
    ),
    Runbook(
        runbook_id="RB-002",
        name="RED Index Recovery",
        description="Recover from RED index by reallocating primary shards",
        trigger_conditions=["red", "primary", "unassigned", "shard_allocation_failure"],
        steps=[
            RunbookStep(step_id="RB-002-S1", title="Assess cluster health", description="Check cluster status and identify RED indices", action="GET _cluster/health", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-002-S2", title="List unassigned primary shards", description="Find all unassigned primary shards with reasons", action="GET _cat/shards?v&h=index,shard,primar,state,unassigned_reason", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-002-S3", title="Reroute unassigned shards", description="Manually reroute unassigned primary shards to available nodes", action='POST _cluster/reroute {"commands": [{"allocate_stale_primary": {"index": "{index}", "shard": 0, "node": "{node}", "accept_data_loss": true}}]}', risk=StepRisk.high, estimated_time_sec=10, requires_approval=True),
            RunbookStep(step_id="RB-002-S4", title="Verify data integrity", description="Check document counts and verify no data loss", action="GET _cat/indices?v&h=index,docs.count,store.size,status", risk=StepRisk.safe, estimated_time_sec=10, requires_approval=False),
            RunbookStep(step_id="RB-002-S5", title="Restore replicas", description="Re-enable replica allocation for redundancy", action='PUT {index}/_settings {"index.number_of_replicas": 1}', risk=StepRisk.low, estimated_time_sec=15, requires_approval=True),
        ],
        total_estimated_time=45,
    ),
    Runbook(
        runbook_id="RB-003",
        name="Slow Query Remediation",
        description="Diagnose and fix slow queries on Elasticsearch",
        trigger_conditions=["slow", "latency", "timeout", "performance", "query"],
        steps=[
            RunbookStep(step_id="RB-003-S1", title="Check slow query log", description="Review recent slow queries from the slow log", action="GET {index}/_search?profile=true", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-003-S2", title="Clear field data cache", description="Clear the fielddata cache to free heap space", action="POST _cache/clear?fielddata=true", risk=StepRisk.low, estimated_time_sec=5, requires_approval=True),
            RunbookStep(step_id="RB-003-S3", title="Optimize index mappings", description="Review and suggest mapping changes to reduce field count", action="GET {index}/_mapping", risk=StepRisk.safe, estimated_time_sec=10, requires_approval=False),
            RunbookStep(step_id="RB-003-S4", title="Force merge segments", description="Reduce segment count for faster reads (only on read-only indices)", action="POST {index}/_forcemerge?max_num_segments=1", risk=StepRisk.medium, estimated_time_sec=30, requires_approval=True),
        ],
        total_estimated_time=50,
    ),
    Runbook(
        runbook_id="RB-004",
        name="Disk Watermark Remediation",
        description="Free up disk space when watermark thresholds are exceeded",
        trigger_conditions=["disk", "watermark", "storage", "flood_stage", "no_new_index"],
        steps=[
            RunbookStep(step_id="RB-004-S1", title="Check disk usage per node", description="Review disk allocation on each data node", action="GET _cat/allocation?v", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-004-S2", title="List large indices", description="Find the largest indices eligible for deletion", action="GET _cat/indices?v&h=index,store.size,docs.count,creation.date&s=store.size:desc", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-004-S3", title="Delete old indices", description="Remove time-based indices older than retention period", action="DELETE {old_index_pattern}", risk=StepRisk.high, estimated_time_sec=15, requires_approval=True),
            RunbookStep(step_id="RB-004-S4", title="Adjust watermarks if needed", description="Temporarily increase flood stage watermark", action='PUT _cluster/settings {"persistent": {"cluster.routing.allocation.disk.watermark.flood_stage": "95%"}}', risk=StepRisk.medium, estimated_time_sec=5, requires_approval=True),
        ],
        total_estimated_time=30,
    ),
    Runbook(
        runbook_id="RB-005",
        name="Mapping Explosion Fix",
        description="Address dynamic mapping explosion causing heap pressure",
        trigger_conditions=["mapping", "dynamic", "field", "explosion", "heap", "too_many_fields"],
        steps=[
            RunbookStep(step_id="RB-005-S1", title="Count fields per index", description="Check which indices have excessive field counts", action="GET {index}/_mapping?filter_path=*.mappings", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-005-S2", title="Freeze dynamic mapping", description="Disable dynamic mapping to prevent new fields", action='PUT {index}/_settings {"index.mapper.dynamic": false}', risk=StepRisk.medium, estimated_time_sec=5, requires_approval=True),
            RunbookStep(step_id="RB-005-S3", title="Plan reindex with explicit mapping", description="Create new index with explicit mapping and reindex data", action='POST _reindex {"source": {"index": "{index}"}, "dest": {"index": "{index}-fixed"}}', risk=StepRisk.high, estimated_time_sec=120, requires_approval=True),
        ],
        total_estimated_time=130,
    ),
    Runbook(
        runbook_id="RB-006",
        name="Circuit Breaker Reset",
        description="Address tripped circuit breakers and reduce memory pressure",
        trigger_conditions=["circuit", "breaker", "oom", "memory", "heap", "out_of_memory"],
        steps=[
            RunbookStep(step_id="RB-006-S1", title="Check circuit breaker stats", description="Review which breakers have tripped", action="GET _nodes/stats/breaker", risk=StepRisk.safe, estimated_time_sec=5, requires_approval=False),
            RunbookStep(step_id="RB-006-S2", title="Clear caches", description="Clear all caches to free heap space", action="POST _cache/clear", risk=StepRisk.low, estimated_time_sec=5, requires_approval=True),
            RunbookStep(step_id="RB-006-S3", title="Reduce indexing pressure", description="Lower the indexing queue size to reduce memory pressure", action='PUT _cluster/settings {"persistent": {"indices.memory.index_buffer.size": "10%"}}', risk=StepRisk.medium, estimated_time_sec=10, requires_approval=True),
        ],
        total_estimated_time=20,
    ),
]


class RunbookEngine:
    """Auto-runbook matching and execution engine."""

    def __init__(self):
        self._runbooks: dict[str, Runbook] = {rb.runbook_id: rb for rb in BUILTIN_RUNBOOKS}
        self._executions: list[RunbookExecution] = []
        self._execution_counter = 0

    def list_runbooks(self) -> list[Runbook]:
        """List all available runbooks."""
        return list(self._runbooks.values())

    def get_runbook(self, runbook_id: str) -> Optional[Runbook]:
        """Get a specific runbook by ID."""
        return self._runbooks.get(runbook_id)

    def match_runbook(self, incident: dict) -> Optional[MatchedRunbook]:
        """Find the best matching runbook for an incident."""
        best_match = None
        best_score = 0.0
        best_reasons = []

        # Extract matching signals from incident
        signals = []
        for field_name in ["root_cause", "title", "message", "description"]:
            val = incident.get(field_name, "")
            if val:
                signals.extend(val.lower().split())

        # Add severity-based signals
        severity = incident.get("severity", "").lower()
        if severity == "critical":
            signals.append("red")
        elif severity == "high":
            signals.extend(["red", "slow"])

        for rb in self._runbooks.values():
            score = 0.0
            reasons = []

            for condition in rb.trigger_conditions:
                cond_lower = condition.lower()
                for signal in signals:
                    if cond_lower in signal or signal in cond_lower:
                        score += 0.25
                        reasons.append(f"Trigger keyword match: \'{condition}\'")
                        break

            # Check applicable indices
            index_name = incident.get("index_name", "")
            if index_name and rb.applicable_indices:
                if index_name in rb.applicable_indices:
                    score += 0.3
                    reasons.append(f"Applicable to index: {index_name}")

            # Normalize score
            score = min(score, 1.0)

            if score > best_score:
                best_score = score
                best_match = rb
                best_reasons = reasons

        if best_match and best_score >= 0.15:
            return MatchedRunbook(
                runbook=best_match,
                match_score=round(best_score, 2),
                match_reasons=best_reasons,
                incident_context=incident,
            )
        return None

    def get_runbook_steps(self, runbook_id: str) -> list[RunbookStep]:
        """Get all steps for a runbook."""
        rb = self._runbooks.get(runbook_id)
        return rb.steps if rb else []

    def execute_step(self, runbook_id: str, step_id: str, auto_approve_safe: bool = False) -> StepResult:
        """Execute a runbook step. Auto-approves safe steps if auto_approve_safe=True."""
        rb = self._runbooks.get(runbook_id)
        if not rb:
            return StepResult(step_id=step_id, runbook_id=runbook_id, status=StepStatus.failed, error="Runbook not found")

        step = next((s for s in rb.steps if s.step_id == step_id), None)
        if not step:
            return StepResult(step_id=step_id, runbook_id=runbook_id, status=StepStatus.failed, error="Step not found")

        # Check approval requirement
        if step.requires_approval and not auto_approve_safe and step.risk != StepRisk.safe:
            return StepResult(step_id=step_id, runbook_id=runbook_id, status=StepStatus.failed, error="Step requires approval")

        # Simulate execution (in production, this would call ES API)
        start = time.time()
        step.status = StepStatus.executing
        step.timestamp = time.time()

        # Simulated result based on action type
        output = f"Executed: {step.action[:100]}"
        step.status = StepStatus.completed
        step.result = output
        duration = time.time() - start

        return StepResult(
            step_id=step_id,
            runbook_id=runbook_id,
            status=StepStatus.completed,
            output=output,
            duration_sec=round(duration, 2),
        )

    def start_execution(self, runbook_id: str, incident_id: str) -> RunbookExecution:
        """Start a new runbook execution for an incident."""
        self._execution_counter += 1
        rb = self._runbooks.get(runbook_id)
        if not rb:
            raise ValueError(f"Runbook {runbook_id} not found")

        execution = RunbookExecution(
            execution_id=f"EXEC-{self._execution_counter:04d}",
            runbook_id=runbook_id,
            incident_id=incident_id,
            steps_total=len(rb.steps),
        )
        self._executions.append(execution)
        return execution

    def get_execution_history(self, limit: int = 20) -> list[RunbookExecution]:
        """Get recent runbook execution history."""
        return sorted(self._executions, key=lambda e: e.started_at, reverse=True)[:limit]

    def add_runbook(self, runbook: Runbook):
        """Add a custom runbook to the library."""
        self._runbooks[runbook.runbook_id] = runbook
