"""Client for Elasticsearch via the Elastic MCP Server with direct ES fallback.

Primary: communicates with the Elastic MCP Server via streamable-HTTP protocol.
Fallback: when the MCP server is unavailable, calls Elasticsearch REST API directly.
This ensures DataPulse works even without a running MCP server instance.
"""

import httpx
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ElasticMCPClient:
    """Client for Elasticsearch data — via MCP server (primary) or direct REST (fallback)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: Optional[str] = None,
        es_url: str = "http://localhost:9200",
    ):
        self.base_url = base_url.rstrip("/")
        self.mcp_endpoint = f"{self.base_url}/mcp"
        self.api_key = api_key
        self.es_url = es_url.rstrip("/")
        self._request_id = 0
        self._use_direct = False  # Auto-switches to direct if MCP fails

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server. Falls back to direct ES API on failure."""
        if self._use_direct:
            return await self._call_direct(tool_name, arguments)

        try:
            result = await self._call_mcp(tool_name, arguments)
            return result
        except Exception as e:
            logger.warning(f"MCP call failed ({tool_name}): {e}. Switching to direct ES API.")
            self._use_direct = True
            return await self._call_direct(tool_name, arguments)

    async def _call_mcp(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call the Elastic MCP Server via JSON-RPC 2.0."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
            "id": self._request_id,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.mcp_endpoint, json=payload, headers=headers)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                return self._parse_sse_response(response.text)
            return response.json().get("result", response.json())

    async def _call_direct(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Fallback: call Elasticsearch REST API directly."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            if tool_name == "list_indices":
                resp = await client.get(
                    f"{self.es_url}/_cat/indices?format=json",
                    headers=headers,
                )
                resp.raise_for_status()
                raw = resp.json()
                # Normalize to our expected format
                indices = []
                for idx in raw:
                    indices.append({
                        "name": idx.get("index", idx.get("name", "")),
                        "health": idx.get("health", "unknown"),
                        "status": idx.get("status", "unknown"),
                        "docs": int(idx.get("docs.count", idx.get("docs", 0))),
                        "size": idx.get("store.size", idx.get("size", "")),
                        "pri": idx.get("pri", ""),
                        "rep": idx.get("rep", ""),
                    })
                return {"indices": indices}

            elif tool_name == "get_mappings":
                index = arguments.get("index", "_all")
                resp = await client.get(
                    f"{self.es_url}/{index}/_mapping",
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()

            elif tool_name == "search":
                index = arguments.get("index", "_all")
                body = arguments.get("body", arguments.get("query", {"match_all": {}}))
                if isinstance(body, str):
                    body = json.loads(body)
                resp = await client.post(
                    f"{self.es_url}/{index}/_search",
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()

            elif tool_name == "esql":
                query = arguments.get("query", "")
                resp = await client.post(
                    f"{self.es_url}/_query?format=json",
                    content=query,
                    headers={**headers, "Content-Type": "application/vnd.elasticsearch+xl",
                             "Accept": "application/json"},
                )
                # Fallback: try the _esql endpoint
                if resp.status_code == 400:
                    resp = await client.post(
                        f"{self.es_url}/_esql",
                        json={"query": query},
                        headers=headers,
                    )
                resp.raise_for_status()
                return resp.json()

            elif tool_name == "get_shards":
                index = arguments.get("index", "_all")
                resp = await client.get(
                    f"{self.es_url}/_cat/shards/{index}?format=json",
                    headers=headers,
                )
                resp.raise_for_status()
                raw = resp.json()
                shards = []
                for s in raw:
                    shards.append({
                        "index": s.get("index", ""),
                        "shard": s.get("shard", ""),
                        "prirep": s.get("prirep", ""),
                        "state": s.get("state", ""),
                        "docs": s.get("docs", ""),
                        "store": s.get("store", ""),
                        "node": s.get("node", None),
                    })
                return {"shards": shards}

            else:
                return {"error": f"Unknown tool: {tool_name}"}

    def _parse_sse_response(self, text: str) -> Any:
        """Parse Server-Sent Events response from MCP server."""
        for line in text.split("\n"):
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    return data.get("result", data)
                except json.JSONDecodeError:
                    continue
        return {"raw": text}

    async def list_indices(self) -> Dict[str, Any]:
        """List all available Elasticsearch indices."""
        return await self._call_tool("list_indices", {})

    async def get_mappings(self, index: str) -> Dict[str, Any]:
        """Get field mappings for a specific Elasticsearch index."""
        return await self._call_tool("get_mappings", {"index": index})

    async def search(self, index: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Perform an Elasticsearch search using query DSL."""
        return await self._call_tool("search", {"index": index, "body": body})

    async def esql(self, query: str) -> Dict[str, Any]:
        """Execute an ES|QL query."""
        return await self._call_tool("esql", {"query": query})

    async def get_shards(self, index: Optional[str] = None) -> Dict[str, Any]:
        """Get shard information for all or specific indices."""
        args = {}
        if index:
            args["index"] = index
        return await self._call_tool("get_shards", args)
