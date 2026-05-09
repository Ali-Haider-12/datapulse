"""Gmail MCP Server client with send_email and list_messages tools."""

import httpx
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class GmailMCPClient:
    """Client for Gmail MCP Server, implements send_email and list_messages."""

    def __init__(self, base_url: str = "http://localhost:8081"):
        self.base_url = base_url.rstrip("/")
        self.mcp_endpoint = f"{self.base_url}/mcp"
        self._request_id = 0

    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the Gmail MCP Server via JSON-RPC 2.0."""
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

    async def send_email(self, to: str, subject: str, body: str, **kwargs) -> Dict[str, Any]:
        """Send an email via Gmail MCP Server."""
        return await self._call_mcp_tool(
            "send_email",
            {"to": to, "subject": subject, "body": body, **kwargs}
        )

    async def list_messages(self, max_results: int = 10, **kwargs) -> Dict[str, Any]:
        """List Gmail messages via MCP Server."""
        return await self._call_mcp_tool(
            "list_messages",
            {"max_results": max_results, **kwargs}
        )
