import pytest
from unittest.mock import AsyncMock
from app.services.health_analyzer import HealthAnalyzer
from app.services.mcp_client import ElasticMCPClient
from app.services.agent import DataPulseAgent


@pytest.mark.asyncio
async def test_health_overview_green():
    mock_client = AsyncMock(spec=ElasticMCPClient)
    mock_client.list_indices.return_value = {
        "indices": [
            {"name": "logs-2026-05", "health": "green", "docs": 1000},
            {"name": "products", "health": "green", "docs": 500},
        ]
    }
    mock_client.get_shards.return_value = {"shards": []}

    analyzer = HealthAnalyzer(mock_client)
    result = await analyzer.get_health_overview()

    assert result["total_indices"] == 2
    assert result["total_alerts"] == 0
    assert result["health_score"] == 100


@pytest.mark.asyncio
async def test_health_overview_yellow_red():
    mock_client = AsyncMock(spec=ElasticMCPClient)
    mock_client.list_indices.return_value = {
        "indices": [
            {"name": "logs-2026-05", "health": "yellow", "docs": 1000},
            {"name": "products", "health": "red", "docs": 500},
        ]
    }
    mock_client.get_shards.return_value = {"shards": [{"state": "UNASSIGNED", "index": "products", "shard": 0}]}

    analyzer = HealthAnalyzer(mock_client)
    result = await analyzer.get_health_overview()

    assert result["total_indices"] == 2
    assert result["total_alerts"] == 3  # yellow + red + unassigned
    assert result["health_score"] == 70


@pytest.mark.asyncio
async def test_mapping_issues_detection():
    mock_client = AsyncMock(spec=ElasticMCPClient)
    props = {f"field_{i}": {"type": "text"} for i in range(150)}
    mock_client.get_mappings.return_value = {"mappings": {"properties": props}}

    analyzer = HealthAnalyzer(mock_client)
    issues = await analyzer.detect_mapping_issues("test-index")

    assert len(issues) >= 1
    assert issues[0]["type"] == "mapping_explosion_risk"


@pytest.mark.asyncio
async def test_agent_mock_health_query():
    mock_client = AsyncMock(spec=ElasticMCPClient)
    mock_client.list_indices.return_value = {"indices": [{"name": "logs", "health": "green", "docs": 100}]}
    mock_client.get_shards.return_value = {"shards": []}

    agent = DataPulseAgent(mcp_client=mock_client)
    # Force mock mode — prevent lazy genai_client init
    agent._genai_client = None
    # Override the property to always return None
    type(agent).genai_client = property(lambda self: None)

    responses = []
    async for chunk in agent.chat("How healthy is my data?"):
        responses.append(chunk)

    # Restore the property
    del type(agent).genai_client

    # Should have tool_call, tool_result, tool_call, tool_result, and text
    tool_calls = [r for r in responses if r["type"] == "tool_call"]
    text_responses = [r for r in responses if r["type"] == "text"]
    assert len(tool_calls) >= 1
    assert len(text_responses) >= 1


@pytest.mark.asyncio
async def test_agent_reset():
    mock_client = AsyncMock(spec=ElasticMCPClient)
    agent = DataPulseAgent(mcp_client=mock_client)
    agent._conversation_history.append({"role": "user", "content": "test"})
    agent.reset_conversation()
    assert len(agent._conversation_history) == 0
