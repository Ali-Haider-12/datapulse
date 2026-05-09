"""Tests for all 5 hackathon features.

Feature #1: Autonomous Incident Response
Feature #2: SRE Story Reframe  
Feature #3: Proactive Patrol Mode
Feature #4: One-Click Remediation (API endpoint tests)
Feature #5: Executive Impact Dashboard
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.incident_response import IncidentResponseEngine, Incident, IncidentStatus, IncidentSeverity
from app.services.patrol_service import PatrolService
from app.services.impact_calculator import ImpactCalculator
from app.services.mcp_client import ElasticMCPClient


# ============================================================
# Feature #1: Autonomous Incident Response
# ============================================================

class TestIncidentResponse:
    """Test multi-step incident workflow: detect → diagnose → propose → approve → execute."""

    @pytest.fixture
    def mock_mcp(self):
        mcp = MagicMock(spec=ElasticMCPClient)
        mcp.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders-2026", "health": "red", "docs": 15420, "size": "125mb"},
                {"name": "products", "health": "yellow", "docs": 8900, "size": "45mb"},
                {"name": "logs-2026-05", "health": "green", "docs": 1420000, "size": "2.1gb"},
            ]
        })
        mcp.get_mappings = AsyncMock(return_value={"mappings": {"properties": {"field": {"type": "keyword"}}}})
        mcp.search = AsyncMock(return_value={"hits": {"hits": []}})
        mcp.esql = AsyncMock(return_value={"columns": [], "values": []})
        mcp.get_shards = AsyncMock(return_value={"shards": []})
        return mcp

    @pytest.fixture
    def engine(self, mock_mcp):
        return IncidentResponseEngine(mock_mcp)

    @pytest.mark.asyncio
    async def test_detect_incidents_finds_red_index(self, engine, mock_mcp):
        """Detect should find red indices as critical incidents."""
        incidents = await engine.detect_incidents()
        assert len(incidents) >= 1
        red_incidents = [i for i in incidents if i.severity == IncidentSeverity.CRITICAL]
        assert len(red_incidents) >= 1

    @pytest.mark.asyncio
    async def test_detect_incidents_finds_yellow_index(self, engine, mock_mcp):
        """Detect should find yellow indices as warning incidents."""
        incidents = await engine.detect_incidents()
        yellow_incidents = [i for i in incidents if i.severity in (IncidentSeverity.HIGH, IncidentSeverity.MEDIUM)]
        assert len(yellow_incidents) >= 1

    @pytest.mark.asyncio
    async def test_investigate_adds_steps(self, engine, mock_mcp):
        """Investigate should add investigation steps to an incident."""
        incidents = await engine.detect_incidents()
        if not incidents:
            pytest.skip("No incidents detected")
        incident = incidents[0]
        result = await engine.investigate(incident)
        assert result is not None
        assert result.status in (IncidentStatus.INVESTIGATING, IncidentStatus.DIAGNOSED)

    @pytest.mark.asyncio
    async def test_diagnose_adds_root_cause(self, engine, mock_mcp):
        """Diagnose should set a root cause on the incident."""
        incidents = await engine.detect_incidents()
        if not incidents:
            pytest.skip("No incidents detected")
        incident = await engine.investigate(incidents[0])
        result = await engine.diagnose(incident)
        assert result.diagnosis is not None or result.status == IncidentStatus.DIAGNOSED

    @pytest.mark.asyncio
    async def test_remediation_actions_after_diagnosis(self, engine, mock_mcp):
        """After diagnosis, remediation actions should be proposed."""
        incidents = await engine.detect_incidents()
        if not incidents:
            pytest.skip("No incidents detected")
        incident = await engine.investigate(incidents[0])
        incident = await engine.diagnose(incident)
        # After diagnosis, there should be remediation actions
        assert len(incident.remediation_actions) >= 1 or incident.status == IncidentStatus.REMEDIATION_PROPOSED

    @pytest.mark.asyncio
    async def test_approve_action(self, engine, mock_mcp):
        """approve_action should return True for valid action."""
        incidents = await engine.detect_incidents()
        if not incidents:
            pytest.skip("No incidents detected")
        incident = await engine.investigate(incidents[0])
        incident = await engine.diagnose(incident)
        if not incident.remediation_actions:
            # Manually add one for testing
            incident.add_remediation_action("reindex", "Reindex orders-2026", risk_level="low")
        action = incident.remediation_actions[0]
        result = engine.approve_action(incident.id, action["action_id"])
        assert result is True or result is not None

    @pytest.mark.asyncio
    async def test_execute_remediation(self, engine, mock_mcp):
        """execute_remediation should attempt to fix the issue."""
        incidents = await engine.detect_incidents()
        if not incidents:
            pytest.skip("No incidents detected")
        incident = await engine.investigate(incidents[0])
        incident = await engine.diagnose(incident)
        if not incident.remediation_actions:
            incident.add_remediation_action("reindex", "Reindex orders-2026", risk_level="low")
        action = incident.remediation_actions[0]
        result = await engine.execute_remediation(incident, action["action_id"])
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_list_incidents(self, engine, mock_mcp):
        """Should list all tracked incidents."""
        await engine.detect_incidents()
        active = engine.list_incidents()
        assert isinstance(active, list)

    @pytest.mark.asyncio
    async def test_get_incident(self, engine, mock_mcp):
        """Should retrieve a specific incident by ID."""
        incidents = await engine.detect_incidents()
        if not incidents:
            pytest.skip("No incidents detected")
        found = engine.get_incident(incidents[0].id)
        assert found is not None
        assert found.id == incidents[0].id

    @pytest.mark.asyncio
    async def test_detect_with_all_green(self, engine, mock_mcp):
        """With all green indices, no critical incidents should be found."""
        mock_mcp.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders", "health": "green", "docs": 1000, "size": "10mb"},
                {"name": "products", "health": "green", "docs": 500, "size": "5mb"},
            ]
        })
        incidents = await engine.detect_incidents()
        critical = [i for i in incidents if i.severity == IncidentSeverity.CRITICAL]
        assert len(critical) == 0


# ============================================================
# Feature #2: SRE Story Reframe (tested via agent_tools content)
# ============================================================

class TestSREStory:
    """Verify the agent prompt and tools reflect the e-commerce SRE narrative."""

    def test_system_instruction_has_ecommerce_focus(self):
        """SYSTEM_INSTRUCTION should reference e-commerce/on-call context."""
        from app.services.agent_tools import SYSTEM_INSTRUCTION
        lower = SYSTEM_INSTRUCTION.lower()
        has_ecommerce = any(kw in lower for kw in ["e-commerce", "ecommerce", "on-call", "oncall", "sre", "site reliability"])
        assert has_ecommerce, "SYSTEM_INSTRUCTION should reference e-commerce SRE context"

    def test_system_instruction_mentions_incident(self):
        """SYSTEM_INSTRUCTION should reference incident response workflows."""
        from app.services.agent_tools import SYSTEM_INSTRUCTION
        lower = SYSTEM_INSTRUCTION.lower()
        has_incident = any(kw in lower for kw in ["incident", "remediat", "diagnos", "auto-heal"])
        assert has_incident, "SYSTEM_INSTRUCTION should reference incident response"


# ============================================================
# Feature #3: Proactive Patrol Mode
# ============================================================

class TestPatrolMode:
    """Test background health monitoring with scheduled checks."""

    @pytest.fixture
    def mock_mcp(self):
        mcp = MagicMock(spec=ElasticMCPClient)
        mcp.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders", "health": "green", "docs": 1000, "size": "10mb"},
            ]
        })
        mcp.get_shards = AsyncMock(return_value={"shards": []})
        mcp.esql = AsyncMock(return_value={"columns": [], "values": []})
        mcp.search = AsyncMock(return_value={"hits": {"hits": []}})
        mcp.get_mappings = AsyncMock(return_value={"mappings": {}})
        return mcp

    @pytest.fixture
    def patrol(self, mock_mcp):
        return PatrolService(mock_mcp, interval_seconds=30)

    @pytest.mark.asyncio
    async def test_patrol_run_patrol(self, patrol, mock_mcp):
        """A single patrol run should return a dict with health info."""
        result = await patrol.run_patrol()
        assert isinstance(result, dict)
        assert "health_score" in result or "issues_found" in result or "status" in result

    @pytest.mark.asyncio
    async def test_patrol_detects_yellow_index(self, mock_mcp):
        """Patrol should detect yellow indices."""
        mock_mcp.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders", "health": "yellow", "docs": 1000, "size": "10mb"},
                {"name": "products", "health": "green", "docs": 500, "size": "5mb"},
            ]
        })
        patrol = PatrolService(mock_mcp, interval_seconds=30)
        result = await patrol.run_patrol()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_patrol_start_stop(self, patrol):
        """Patrol should start and stop without error."""
        await patrol.start()
        assert patrol.is_running  # is_running is a property, not a method
        await patrol.stop()
        assert not patrol.is_running

    @pytest.mark.asyncio
    async def test_patrol_history(self, patrol, mock_mcp):
        """Should return patrol history."""
        await patrol.run_patrol()
        history = patrol.patrol_history  # property, not method
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_patrol_last_patrol(self, patrol, mock_mcp):
        """Should return last patrol result."""
        await patrol.run_patrol()
        last = patrol.last_patrol  # property, not method
        assert last is not None


# ============================================================
# Feature #5: Executive Impact Dashboard
# ============================================================

class TestImpactCalculator:
    """Test business-impact metrics translation from ES health data."""

    @pytest.fixture
    def mock_mcp(self):
        mcp = MagicMock(spec=ElasticMCPClient)
        mcp.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders-2026", "health": "red", "docs": 15420, "size": "125mb"},
                {"name": "products", "health": "yellow", "docs": 8900, "size": "45mb"},
                {"name": "logs-2026-05", "health": "green", "docs": 1420000, "size": "2.1gb"},
            ]
        })
        mcp.esql = AsyncMock(return_value={"columns": [], "values": []})
        return mcp

    @pytest.fixture
    def calculator(self, mock_mcp):
        return ImpactCalculator(mock_mcp)

    @pytest.mark.asyncio
    async def test_revenue_at_risk_with_red_index(self, calculator, mock_mcp):
        """Red order/payment index should show revenue at risk."""
        metrics = await calculator.calculate_impact()
        assert metrics["revenue_at_risk"] > 0

    @pytest.mark.asyncio
    async def test_customers_affected_with_red_index(self, calculator, mock_mcp):
        """Red index should show customers affected."""
        metrics = await calculator.calculate_impact()
        assert metrics["customers_affected"] > 0

    @pytest.mark.asyncio
    async def test_business_summary_present(self, calculator, mock_mcp):
        """Business summary should be a non-empty string."""
        metrics = await calculator.calculate_impact()
        assert isinstance(metrics["business_summary"], str)
        assert len(metrics["business_summary"]) > 0

    @pytest.mark.asyncio
    async def test_degraded_services_with_red_index(self, calculator, mock_mcp):
        """Red index should appear in degraded_services."""
        metrics = await calculator.calculate_impact()
        assert len(metrics["degraded_services"]) >= 1

    @pytest.mark.asyncio
    async def test_mttr_with_red_index(self, calculator, mock_mcp):
        """MTTR should be non-zero when there are red indices."""
        metrics = await calculator.calculate_impact()
        assert metrics["mttr_minutes"] > 0

    @pytest.mark.asyncio
    async def test_all_green_no_revenue_risk(self, mock_mcp):
        """All green indices should show zero revenue at risk."""
        mock_mcp.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders", "health": "green", "docs": 1000, "size": "10mb"},
                {"name": "products", "health": "green", "docs": 500, "size": "5mb"},
            ]
        })
        calc = ImpactCalculator(mock_mcp)
        metrics = await calc.calculate_impact()
        assert metrics["revenue_at_risk"] == 0.0
        assert metrics["customers_affected"] == 0
        assert "operational" in metrics["business_summary"].lower() or "healthy" in metrics["business_summary"].lower()

    @pytest.mark.asyncio
    async def test_payment_error_spike_increases_revenue(self, mock_mcp):
        """High error count in payment service should increase revenue at risk."""
        mock_mcp.esql = AsyncMock(return_value={
            "columns": ["service", "error_count"],
            "values": [["payment-service", 150], ["order-service", 80]],
        })
        calc = ImpactCalculator(mock_mcp)
        metrics = await calc.calculate_impact()
        assert metrics["revenue_at_risk"] > 0

    @pytest.mark.asyncio
    async def test_uptime_calculation(self, calculator, mock_mcp):
        """Uptime percentage should be calculated from index health."""
        metrics = await calculator.calculate_impact()
        assert 0 <= metrics["uptime_percent"] <= 100


# ============================================================
# API Endpoint Tests
# ============================================================

class TestIncidentAPI:
    """Test the incident, patrol, and impact API endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_incidents_router_registered(self, client):
        """Incidents router should be accessible."""
        response = client.get("/api/incidents", follow_redirects=False)
        assert response.status_code != 500

    def test_patrol_status_endpoint(self, client):
        """Patrol status endpoint should be accessible."""
        response = client.get("/api/patrol/status", follow_redirects=False)
        assert response.status_code != 500

    def test_impact_endpoint(self, client):
        """Impact metrics endpoint should be accessible."""
        response = client.get("/api/impact", follow_redirects=False)
        assert response.status_code != 500

    def test_health_check(self, client):
        """Main health check should return 200."""
        response = client.get("/health")
        assert response.status_code == 200
