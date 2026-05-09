import pytest
from unittest.mock import AsyncMock
from app.services.mcp_client import ElasticMCPClient

@pytest.mark.asyncio
async def test_list_indices():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    with pytest.MonkeyPatch().context() as m:
        # Use manual mock since patch.object with new_callable has issues
        original = client._call_tool
        async def mock_call(tool_name, arguments):
            if tool_name == "list_indices":
                return {"indices": [{"name": "logs-2026-05", "health": "yellow"}]}
            return {}
        client._call_tool = mock_call
        result = await client.list_indices()
        assert "indices" in result

@pytest.mark.asyncio
async def test_search():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    async def mock_call(tool_name, arguments):
        if tool_name == "search":
            return {"hits": {"total": 5, "hits": []}}
        return {}
    client._call_tool = mock_call
    result = await client.search(index="logs-*", body={"query": {"match_all": {}}})
    assert "hits" in result

@pytest.mark.asyncio
async def test_esql_query():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    async def mock_call(tool_name, arguments):
        if tool_name == "esql":
            return {"columns": ["timestamp", "count"], "values": []}
        return {}
    client._call_tool = mock_call
    result = await client.esql("FROM logs-* | STATS count = COUNT(*) BY timestamp")
    assert "columns" in result

@pytest.mark.asyncio
async def test_get_shards():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    async def mock_call(tool_name, arguments):
        return {"shards": []}
    client._call_tool = mock_call
    result = await client.get_shards(index="logs-*")
    assert "shards" in result

@pytest.mark.asyncio
async def test_get_mappings():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    async def mock_call(tool_name, arguments):
        return {"mappings": {"properties": {}}}
    client._call_tool = mock_call
    result = await client.get_mappings(index="logs-*")
    assert "mappings" in result
