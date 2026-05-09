"""Tests for Auto-Runbook Engine"""

import pytest
from app.services.runbook_engine import (
    RunbookEngine, Runbook, RunbookStep, MatchedRunbook,
    StepResult, StepRisk, StepStatus, RunbookExecution, BUILTIN_RUNBOOKS
)


@pytest.fixture
def engine():
    return RunbookEngine()


class TestListRunbooks:
    def test_list_builtin_runbooks(self, engine):
        runbooks = engine.list_runbooks()
        assert len(runbooks) >= 6  # 6 builtin runbooks

    def test_runbook_has_required_fields(self, engine):
        for rb in engine.list_runbooks():
            assert rb.runbook_id.startswith("RB-")
            assert rb.name != ""
            assert rb.description != ""
            assert len(rb.steps) >= 1
            assert rb.total_estimated_time > 0

    def test_get_runbook_by_id(self, engine):
        rb = engine.get_runbook("RB-001")
        assert rb is not None
        assert rb.name == "YELLOW Index Recovery"

    def test_get_nonexistent_runbook(self, engine):
        rb = engine.get_runbook("RB-999")
        assert rb is None


class TestMatchRunbook:
    def test_match_red_index(self, engine):
        result = engine.match_runbook({
            "root_cause": "shard_allocation_failure",
            "title": "Index orders-2026 went RED",
            "severity": "critical",
        })
        assert result is not None
        assert result.runbook.runbook_id == "RB-002"  # RED Index Recovery
        assert result.match_score >= 0.15

    def test_match_yellow_index(self, engine):
        result = engine.match_runbook({
            "root_cause": "replica_allocation_issue",
            "message": "Index is YELLOW — replica unassigned",
            "severity": "warning",
        })
        assert result is not None
        assert result.runbook.runbook_id == "RB-001"  # YELLOW Index Recovery

    def test_match_slow_queries(self, engine):
        result = engine.match_runbook({
            "root_cause": "performance_degradation",
            "message": "Slow queries detected — latency timeout",
            "severity": "high",
        })
        assert result is not None
        assert result.runbook.runbook_id == "RB-003"

    def test_match_disk_watermark(self, engine):
        result = engine.match_runbook({
            "root_cause": "storage_pressure",
            "message": "Disk watermark exceeded on node",
        })
        assert result is not None
        assert result.runbook.runbook_id == "RB-004"

    def test_match_mapping_explosion(self, engine):
        result = engine.match_runbook({
            "root_cause": "mapping_explosion",
            "message": "Too many dynamic fields causing heap pressure",
        })
        assert result is not None
        assert result.runbook.runbook_id == "RB-005"

    def test_match_circuit_breaker(self, engine):
        result = engine.match_runbook({
            "root_cause": "circuit_breaker_tripped",
            "message": "Circuit breaker tripped — out of memory heap",
        })
        assert result is not None
        assert result.runbook.runbook_id == "RB-006"

    def test_no_match_for_unknown(self, engine):
        result = engine.match_runbook({
            "root_cause": "something_completely_unknown",
            "message": "Random issue no keywords match",
        })
        # Might return None or low-confidence match
        if result is not None:
            assert result.match_score < 0.3

    def test_match_score_bounded(self, engine):
        for rb_id in ["RB-001", "RB-002", "RB-003"]:
            rb = engine.get_runbook(rb_id)
            for condition in rb.trigger_conditions:
                result = engine.match_runbook({"message": condition})
                if result:
                    assert 0 <= result.match_score <= 1.0

    def test_match_reasons_populated(self, engine):
        result = engine.match_runbook({
            "root_cause": "shard_allocation_failure",
            "severity": "critical",
        })
        if result:
            assert len(result.match_reasons) >= 1


class TestRunbookSteps:
    def test_get_steps(self, engine):
        steps = engine.get_runbook_steps("RB-001")
        assert len(steps) >= 3
        for step in steps:
            assert step.step_id.startswith("RB-001-S")
            assert step.title != ""
            assert step.risk in [StepRisk.safe, StepRisk.low, StepRisk.medium, StepRisk.high]

    def test_steps_have_risk_levels(self, engine):
        for rb in engine.list_runbooks():
            for step in rb.steps:
                assert step.risk in StepRisk

    def test_safe_steps_dont_require_approval(self, engine):
        for rb in engine.list_runbooks():
            for step in rb.steps:
                if step.risk == StepRisk.safe:
                    assert step.requires_approval == False


class TestExecuteStep:
    def test_execute_safe_step_with_auto_approve(self, engine):
        result = engine.execute_step("RB-001", "RB-001-S1", auto_approve_safe=True)
        assert result.status == StepStatus.completed
        assert result.output != ""

    def test_execute_risky_step_requires_approval(self, engine):
        result = engine.execute_step("RB-001", "RB-001-S3", auto_approve_safe=False)
        # Step requires approval, should fail without it
        assert result.status == StepStatus.failed
        assert result.error is not None

    def test_execute_nonexistent_runbook(self, engine):
        result = engine.execute_step("RB-999", "S1", auto_approve_safe=True)
        assert result.status == StepStatus.failed

    def test_execute_nonexistent_step(self, engine):
        result = engine.execute_step("RB-001", "NONEXISTENT", auto_approve_safe=True)
        assert result.status == StepStatus.failed


class TestExecutionHistory:
    def test_empty_history(self, engine):
        history = engine.get_execution_history()
        assert len(history) == 0

    def test_execution_after_start(self, engine):
        execution = engine.start_execution("RB-001", "INC-001")
        assert execution.execution_id.startswith("EXEC-")
        assert execution.steps_total > 0
        assert execution.status == "in_progress"

    def test_execution_history_populated(self, engine):
        engine.start_execution("RB-001", "INC-001")
        engine.start_execution("RB-002", "INC-002")
        history = engine.get_execution_history()
        assert len(history) == 2


class TestCustomRunbook:
    def test_add_custom_runbook(self, engine):
        custom = Runbook(
            runbook_id="RB-CUSTOM-001",
            name="Custom Recovery",
            description="Custom runbook for testing",
            trigger_conditions=["custom", "test"],
            steps=[
                RunbookStep(step_id="RC-S1", title="Do something", description="Custom step", action="custom_action", risk=StepRisk.low),
            ],
            total_estimated_time=10,
        )
        engine.add_runbook(custom)
        assert engine.get_runbook("RB-CUSTOM-001") is not None
        runbooks = engine.list_runbooks()
        assert any(rb.runbook_id == "RB-CUSTOM-001" for rb in runbooks)
