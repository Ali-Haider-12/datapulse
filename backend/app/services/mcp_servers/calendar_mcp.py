"""Google Calendar MCP Server client with create_event and list_events tools."""

import httpx
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class CalendarMCPClient:
    """Client for Google Calendar MCP Server, implements create_event and list_events."""

    def __init__(self, base_url: str = "http://localhost:8082"):
        self.base_url = base_url.rstrip("/")
        self.mcp_endpoint = f"{self.base_url}/mcp"
        self._request_id = 0

    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the Calendar MCP Server via JSON-RPC 2.0."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": self._request_id,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.mcp_endpoint, json=payload)
            response.raise_for_status()
            return response.json().get("result", response.json())

    async def create_event(self, summary: str, start_time: str, end_time: str, **kwargs) -> Dict[str, Any]:
        """Create a calendar event via MCP Server."""
        return await self._call_mcp_tool(
            "create_event",
            {"summary": summary, "start_time": start_time, "end_time": end_time, **kwargs}
        )

    async def list_events(self, max_results: int = 10, **kwargs) -> Dict[str, Any]:
        """List calendar events via MCP Server."""
        return await self._call_mcp_tool(
            "list_events",
            {"max_results": max_results, **kwargs}
        )
