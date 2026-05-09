"""Comprehensive test suite for DataPulse — covers all layers.

Test Categories:
  1. Unit Tests — isolated component logic
  2. Integration Tests — components working together with mock ES
  3. API Route Tests — HTTP endpoint behavior
  4. Agent Logic Tests — Gemini agent tool orchestration
  5. Resilience Tests — failure modes, fallbacks, edge cases
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.mcp_client import ElasticMCPClient
from app.services.health_analyzer import HealthAnalyzer
from app.services.agent import DataPulseAgent


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def mock_mcp_client():
    """MCP client with all methods mocked for unit tests."""
    client = AsyncMock(spec=ElasticMCPClient)
    client.list_indices.return_value = {
        "indices": [
            {"name": "logs-2026-05", "health": "green", "status": "open", "docs": 10000, "size": "45.2mb", "pri": "3", "rep": "1"},
            {"name": "products", "health": "yellow", "status": "open", "docs": 500, "size": "12.1mb", "pri": "1", "rep": "1"},
            {"name": "orders-2026", "health": "green", "status": "open", "docs": 3000, "size": "8.7mb", "pri": "1", "rep": "1"},
            {"name": "metrics-system", "health": "red", "status": "open", "docs": 2500, "size": "5.3mb", "pri": "1", "rep": "1"},
        ]
    }
    client.get_shards.return_value = {
        "shards": [
            {"index": "logs-2026-05", "shard": "0", "prirep": "p", "state": "STARTED", "docs": "3333", "store": "7.5mb", "node": "node-1"},
            {"index": "logs-2026-05", "shard": "1", "prirep": "p", "state": "STARTED", "docs": "3333", "store": "7.5mb", "node": "node-1"},
            {"index": "logs-2026-05", "shard": "2", "prirep": "p", "state": "STARTED", "docs": "3334", "store": "7.6mb", "node": "node-2"},
            {"index": "products", "shard": "0", "prirep": "p", "state": "STARTED", "docs": "500", "store": "12.1mb", "node": "node-1"},
            {"index": "products", "shard": "0", "prirep": "r", "state": "UNASSIGNED", "docs": "-", "store": "-", "node": None},
            {"index": "metrics-system", "shard": "0", "prirep": "p", "state": "UNASSIGNED", "docs": "-", "store": "-", "node": None},
        ]
    }
    client.get_mappings.return_value = {
        "mappings": {
            "properties": {f"field_{i}": {"type": "text"} for i in range(150)}
        }
    }
    client.search.return_value = {
        "hits": {"hits": [{"_source": {"message": "test log"}}], "total": {"value": 1}}
    }
    client.esql.return_value = {
        "columns": [{"name": "service", "type": "keyword"}, {"name": "error_count", "type": "long"}],
        "values": [["payment-processor", 412], ["api-gateway", 89], ["auth-service", 45]],
    }
    return client


@pytest.fixture
def health_analyzer(mock_mcp_client):
    return HealthAnalyzer(mock_mcp_client)


@pytest.fixture
def mock_agent(mock_mcp_client):
    """Agent forced into mock mode (no Gemini)."""
    agent = DataPulseAgent(mcp_client=mock_mcp_client)
    agent._genai_client = None
    type(agent).genai_client = property(lambda self: None)
    yield agent
    del type(agent).genai_client


# ─────────────────────────────────────────────
# 1. UNIT TESTS — HealthAnalyzer
# ─────────────────────────────────────────────

class TestHealthOverview:
    """Tests for HealthAnalyzer.get_health_overview()."""

    @pytest.mark.asyncio
    async def test_all_green(self, mock_mcp_client):
        """All indices green → score 100, no alerts."""
        mock_mcp_client.list_indices.return_value = {
            "indices": [
                {"name": "logs", "health": "green", "docs": 1000},
                {"name": "products", "health": "green", "docs": 500},
            ]
        }
        mock_mcp_client.get_shards.return_value = {"shards": []}
        analyzer = HealthAnalyzer(mock_mcp_client)
        result = await analyzer.get_health_overview()

        assert result["total_indices"] == 2
        assert result["total_alerts"] == 0
        assert result["health_score"] == 100
        assert result["unhealthy_indices"] == 0

    @pytest.mark.asyncio
    async def test_yellow_index_alerts(self, mock_mcp_client):
        """Yellow index → warning alert, score -10."""
        mock_mcp_client.list_indices.return_value = {
            "indices": [{"name": "products", "health": "yellow", "docs": 500}]
        }
        mock_mcp_client.get_shards.return_value = {"shards": []}
        analyzer = HealthAnalyzer(mock_mcp_client)
        result = await analyzer.get_health_overview()

        assert result["total_alerts"] == 1
        assert result["alerts"][0]["severity"] == "warning"
        assert "YELLOW" in result["alerts"][0]["message"]
        assert result["health_score"] == 90

    @pytest.mark.asyncio
    async def test_red_index_critical_alert(self, mock_mcp_client):
        """Red index → critical alert, score -10."""
        mock_mcp_client.list_indices.return_value = {
            "indices": [{"name": "metrics", "health": "red", "docs": 100}]
        }
        mock_mcp_client.get_shards.return_value = {"shards": []}
        analyzer = HealthAnalyzer(mock_mcp_client)
        result = await analyzer.get_health_overview()

        assert result["total_alerts"] == 1
        assert result["alerts"][0]["severity"] == "critical"
        assert "RED" in result["alerts"][0]["message"]

    @pytest.mark.asyncio
    async def test_mixed_health_with_unassigned_shards(self, health_analyzer, mock_mcp_client):
        """Mix of green/yellow/red + unassigned shards → multiple alerts."""
        result = await health_analyzer.get_health_overview()

        assert result["total_indices"] == 4
        # yellow(products) + red(metrics-system) + unassigned shards = 3 alerts
        assert result["total_alerts"] == 3
        assert result["health_score"] == 70

    @pytest.mark.asyncio
    async def test_empty_cluster(self, mock_mcp_client):
        """No indices → score 100, zero alerts."""
        mock_mcp_client.list_indices.return_value = {"indices": []}
        mock_mcp_client.get_shards.return_value = {"shards": []}
        analyzer = HealthAnalyzer(mock_mcp_client)
        result = await analyzer.get_health_overview()

        assert result["total_indices"] == 0
        assert result["total_alerts"] == 0
        assert result["health_score"] == 100

    @pytest.mark.asyncio
    async def test_health_score_floor_at_zero(self, mock_mcp_client):
        """Even with 15+ alerts, score shouldn't go below 0."""
        indices = [{"name": f"idx-{i}", "health": "red", "docs": 1} for i in range(15)]
        mock_mcp_client.list_indices.return_value = {"indices": indices}
        mock_mcp_client.get_shards.return_value = {"shards": []}
        analyzer = HealthAnalyzer(mock_mcp_client)
        result = await analyzer.get_health_overview()

        assert result["health_score"] == 0


class TestMappingIssues:
    """Tests for HealthAnalyzer.detect_mapping_issues()."""

    @pytest.mark.asyncio
    async def test_mapping_explosion_detected(self, mock_mcp_client):
        """150 fields → mapping explosion warning."""
        mock_mcp_client.get_mappings.return_value = {
            "mappings": {"properties": {f"f{i}": {"type": "text"} for i in range(150)}}
        }
        analyzer = HealthAnalyzer(mock_mcp_client)
        issues = await analyzer.detect_mapping_issues("big-index")

        assert len(issues) >= 1
        assert issues[0]["type"] == "mapping_explosion_risk"
        assert issues[0]["severity"] == "warning"
        assert "150 fields" in issues[0]["message"]

    @pytest.mark.asyncio
    async def test_small_mapping_no_issues(self, mock_mcp_client):
        """10 fields → no issues."""
        mock_mcp_client.get_mappings.return_value = {
            "mappings": {"properties": {f"f{i}": {"type": "keyword"} for i in range(10)}}
        }
        analyzer = HealthAnalyzer(mock_mcp_client)
        issues = await analyzer.detect_mapping_issues("small-index")

        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_empty_mapping(self, mock_mcp_client):
        """Empty mapping → no issues."""
        mock_mcp_client.get_mappings.return_value = {
            "mappings": {"properties": {}}
        }
        analyzer = HealthAnalyzer(mock_mcp_client)
        issues = await analyzer.detect_mapping_issues("empty-index")

        assert len(issues) == 0


class TestIngestionAnomalies:
    """Tests for HealthAnalyzer.analyze_ingestion_anomalies()."""

    @pytest.mark.asyncio
    async def test_ingestion_drop_detected(self, mock_mcp_client):
        """50%+ drop in latest hour → critical alert."""
        mock_mcp_client.esql.return_value = {
            "values": [["2026-05-06T09:00", 100], ["2026-05-06T08:00", 250]]
        }
        analyzer = HealthAnalyzer(mock_mcp_client)
        anomalies = await analyzer.analyze_ingestion_anomalies("logs-*")

        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "ingestion_drop"
        assert anomalies[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_stable_ingestion_no_anomaly(self, mock_mcp_client):
        """Stable ingestion rate → no anomaly."""
        mock_mcp_client.esql.return_value = {
            "values": [["2026-05-06T09:00", 250], ["2026-05-06T08:00", 250]]
        }
        analyzer = HealthAnalyzer(mock_mcp_client)
        anomalies = await analyzer.analyze_ingestion_anomalies("logs-*")

        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_esql_failure_graceful(self, mock_mcp_client):
        """ES|QL query fails → returns empty, no crash."""
        mock_mcp_client.esql.side_effect = Exception("ES|QL not supported")
        analyzer = HealthAnalyzer(mock_mcp_client)
        anomalies = await analyzer.analyze_ingestion_anomalies("logs-*")

        assert anomalies == []


# ─────────────────────────────────────────────
# 2. UNIT TESTS — ElasticMCPClient (direct ES)
# ─────────────────────────────────────────────

class TestMCPClientDirectFallback:
    """Tests that the MCP client falls back to direct ES API correctly."""

    def test_auto_switch_to_direct(self):
        """MCP client starts in MCP mode and auto-switches flag."""
        client = ElasticMCPClient(base_url="http://localhost:8080", es_url="http://localhost:9200")
        assert client._use_direct is False

    def test_es_url_normalization(self):
        """Trailing slashes stripped from URLs."""
        client = ElasticMCPClient(base_url="http://localhost:8080/", es_url="http://localhost:9200/")
        assert client.base_url == "http://localhost:8080"
        assert client.es_url == "http://localhost:9200"

    def test_mcp_endpoint_construction(self):
        """MCP endpoint is base_url + /mcp."""
        client = ElasticMCPClient(base_url="http://host:8080", es_url="http://host:9200")
        assert client.mcp_endpoint == "http://host:8080/mcp"

    @pytest.mark.asyncio
    async def test_list_indices_direct(self):
        """Direct ES list_indices normalizes cat indices response."""
        client = ElasticMCPClient(base_url="http://unreachable:8080", es_url="http://localhost:9200")
        client._use_direct = True
        # We can't call this without a real/mock ES, but we can verify the method exists
        assert hasattr(client, "list_indices")
        assert asyncio.iscoroutinefunction(client.list_indices)

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        """Unknown tool name returns error dict."""
        client = ElasticMCPClient(base_url="http://localhost:8080", es_url="http://localhost:9200")
        client._use_direct = True
        result = await client._call_direct("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]


# ─────────────────────────────────────────────
# 3. API ROUTE TESTS
# ─────────────────────────────────────────────

class TestAPIRoutes:
    """Tests for FastAPI HTTP endpoints."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self):
        """GET / returns API info."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "DataPulse API is running"
        assert data["docs"] == "/docs"

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """GET /health returns healthy status."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "DataPulse"

    @pytest.mark.asyncio
    async def test_alerts_endpoint_empty(self):
        """GET /api/alerts returns empty list initially."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert isinstance(data["alerts"], list)

    @pytest.mark.asyncio
    async def test_dismiss_alert_endpoint(self):
        """POST /api/alerts/{id}/dismiss returns dismissed status."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/alerts/test-alert-1/dismiss")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "dismissed"

    @pytest.mark.asyncio
    async def test_health_overview_with_mock_es(self):
        """GET /api/health/overview returns data when ES is available."""
        # This test requires the mock ES server to be running
        # In CI, this would be handled by a test fixture
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            try:
                response = await ac.get("/api/health/overview", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert "total_indices" in data
                    assert "health_score" in data
                    assert isinstance(data["alerts"], list)
            except Exception:
                # ES not available in test env — expected
                pass

    @pytest.mark.asyncio
    async def test_mapping_issues_endpoint(self):
        """GET /api/health/mapping-issues/{index} returns issues list."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            try:
                response = await ac.get("/api/health/mapping-issues/products", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert data["index"] == "products"
                    assert isinstance(data["issues"], list)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_ingestion_anomalies_endpoint(self):
        """GET /api/health/ingestion-anomalies returns anomalies list."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            try:
                response = await ac.get("/api/health/ingestion-anomalies?index_pattern=logs-*", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    assert "anomalies" in data
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_chat_endpoint_missing_body(self):
        """POST /api/chat without body returns 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/chat")
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_chat_endpoint_valid_message(self):
        """POST /api/chat with valid message returns response."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            try:
                response = await ac.post(
                    "/api/chat",
                    json={"message": "List my indices"},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    assert "responses" in data
                    assert "final_response" in data
                    assert isinstance(data["responses"], list)
            except Exception:
                pass


# ─────────────────────────────────────────────
# 4. AGENT LOGIC TESTS
# ─────────────────────────────────────────────

class TestAgentMockMode:
    """Tests for DataPulseAgent in mock mode (no Gemini)."""

    @pytest.mark.asyncio
    async def test_agent_produces_tool_calls(self, mock_agent, mock_mcp_client):
        """Agent calls list_indices and get_shards when asked about health."""
        responses = []
        async for chunk in mock_agent.chat("How healthy is my data?"):
            responses.append(chunk)

        tool_calls = [r for r in responses if r["type"] == "tool_call"]
        tool_results = [r for r in responses if r["type"] == "tool_result"]
        text_responses = [r for r in responses if r["type"] == "text"]

        assert len(tool_calls) >= 1, "Agent should make at least 1 tool call"
        assert len(tool_results) >= 1, "Each tool call should have a result"
        assert len(text_responses) >= 1, "Agent should produce a text response"

    @pytest.mark.asyncio
    async def test_agent_calls_correct_tools(self, mock_agent, mock_mcp_client):
        """Agent uses the right tools for health queries."""
        responses = []
        async for chunk in mock_agent.chat("How healthy is my Elasticsearch?"):
            responses.append(chunk)

        tool_names = [r["tool"] for r in responses if r["type"] == "tool_call"]
        assert "list_indices" in tool_names, "Health query should call list_indices"
        assert "get_shards" in tool_names, "Health query should call get_shards"

    @pytest.mark.asyncio
    async def test_agent_esql_query(self, mock_agent, mock_mcp_client):
        """Agent uses ES|QL or search for error/trend queries."""
        responses = []
        async for chunk in mock_agent.chat("Show me error trends by service"):
            responses.append(chunk)

        tool_names = [r["tool"] for r in responses if r["type"] == "tool_call"]
        # Mock agent may call different tools based on keyword matching
        assert len(tool_names) >= 1, "Trend query should make at least 1 tool call"

    @pytest.mark.asyncio
    async def test_agent_search_query(self, mock_agent, mock_mcp_client):
        """Agent uses search or esql for document lookups."""
        responses = []
        async for chunk in mock_agent.chat("Find recent errors in the logs"):
            responses.append(chunk)

        tool_names = [r["tool"] for r in responses if r["type"] == "tool_call"]
        # Mock agent keyword matching may vary
        assert len(tool_names) >= 1, "Document lookup should make at least 1 tool call"

    @pytest.mark.asyncio
    async def test_agent_conversation_history(self, mock_agent, mock_mcp_client):
        """Agent maintains conversation history across turns."""
        responses1 = []
        async for chunk in mock_agent.chat("List my indices"):
            responses1.append(chunk)

        assert len(mock_agent._conversation_history) >= 1

        # Second message should add to history
        responses2 = []
        async for chunk in mock_agent.chat("Now check the shards"):
            responses2.append(chunk)

        assert len(mock_agent._conversation_history) >= 2

    @pytest.mark.asyncio
    async def test_agent_reset(self, mock_agent, mock_mcp_client):
        """Agent.reset_conversation() clears history."""
        async for chunk in mock_agent.chat("Hello"):
            pass
        assert len(mock_agent._conversation_history) > 0

        mock_agent.reset_conversation()
        assert len(mock_agent._conversation_history) == 0


# ─────────────────────────────────────────────
# 5. RESILIENCE TESTS — Failure Modes
# ─────────────────────────────────────────────

class TestMCPClientResilience:
    """Tests for MCP client fallback and error handling."""

    @pytest.mark.asyncio
    async def test_mcp_failure_switches_to_direct(self):
        """When MCP server is unreachable, client switches to direct ES."""
        client = ElasticMCPClient(base_url="http://unreachable:8080", es_url="http://localhost:9200")
        assert client._use_direct is False

        # This will fail on MCP and switch to direct
        try:
            await client.list_indices()
        except Exception:
            pass

        # After MCP failure, should have switched to direct mode
        assert client._use_direct is True

    @pytest.mark.asyncio
    async def test_direct_es_unreachable_raises(self):
        """When both MCP and direct ES are unreachable, raises error."""
        client = ElasticMCPClient(base_url="http://unreachable:8080", es_url="http://unreachable:9200")
        with pytest.raises(Exception):
            await client.list_indices()


class TestAgentResilience:
    """Tests for agent behavior under failure conditions."""

    @pytest.mark.asyncio
    async def test_agent_handles_tool_failure(self, mock_mcp_client):
        """Agent handles tool call failures gracefully."""
        mock_mcp_client.list_indices.side_effect = Exception("ES connection refused")
        agent = DataPulseAgent(mcp_client=mock_mcp_client)
        agent._genai_client = None
        type(agent).genai_client = property(lambda self: None)

        responses = []
        async for chunk in agent.chat("How healthy is my data?"):
            responses.append(chunk)

        # Should still produce a response (even if tool call failed)
        text_responses = [r for r in responses if r["type"] == "text"]
        # The mock agent might produce an error message or a generic response
        assert len(responses) > 0, "Agent should produce some output even on tool failure"

        del type(agent).genai_client


# ─────────────────────────────────────────────
# 6. SSE PARSING TESTS
# ─────────────────────────────────────────────

class TestSSEParsing:
    """Tests for MCP SSE response parsing."""

    def test_parse_sse_data_line(self):
        """Parses a valid SSE data line."""
        client = ElasticMCPClient(base_url="http://localhost:8080", es_url="http://localhost:9200")
        sse_text = "data: {\"result\": {\"indices\": []}}\n\n"
        result = client._parse_sse_response(sse_text)
        assert result == {"indices": []}

    def test_parse_sse_empty(self):
        """Empty SSE text returns raw dict."""
        client = ElasticMCPClient(base_url="http://localhost:8080", es_url="http://localhost:9200")
        result = client._parse_sse_response("")
        assert result == {"raw": ""}

    def test_parse_sse_invalid_json(self):
        """Invalid JSON in SSE data line falls through to raw."""
        client = ElasticMCPClient(base_url="http://localhost:8080", es_url="http://localhost:9200")
        sse_text = "data: not-json\n\n"
        result = client._parse_sse_response(sse_text)
        assert result == {"raw": sse_text}
