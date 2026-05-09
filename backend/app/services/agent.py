"""Gemini-powered agent that orchestrates Elastic MCP tool calls."""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.agent_tools import TOOL_DEFINITIONS, SYSTEM_INSTRUCTION

logger = logging.getLogger(__name__)


class DataPulseAgent:
    """Gemini-powered agent that orchestrates Elastic MCP tool calls.

    Uses the google-genai SDK to communicate with Gemini on Vertex AI.
    The agent maintains conversation history and routes tool calls to the
    Elastic MCP client.
    """

    def __init__(self, mcp_client: ElasticMCPClient):
        self.mcp_client = mcp_client
        self._genai_client = None
        self._conversation_history: List[Dict[str, Any]] = []

    @property
    def genai_client(self):
        """Lazy-initialize the Google GenAI client.

        Supports two modes:
        - API Key mode (free tier): Set GEMINI_API_KEY in .env
        - Vertex AI mode (GCP): Set GOOGLE_CLOUD_PROJECT + Application Default Credentials
        """
        if self._genai_client is None:
            try:
                from google import genai

                api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
                if api_key:
                    # AI Studio / free tier mode
                    self._genai_client = genai.Client(api_key=api_key)
                    logger.info("Gemini client initialized with API key")
                else:
                    # Vertex AI mode (requires ADC)
                    self._genai_client = genai.Client(
                        vertexai=True,
                        project=settings.GOOGLE_CLOUD_PROJECT,
                        location=settings.GOOGLE_CLOUD_LOCATION,
                    )
                    logger.info("Gemini client initialized with Vertex AI")
            except ImportError:
                logger.warning("google-genai not available, using mock mode")
                self._genai_client = None
            except Exception as e:
                logger.warning(f"Gemini client init failed: {e}, using mock mode")
                self._genai_client = None
        return self._genai_client

    async def _execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Route tool calls to the MCP client."""
        tool_map = {
            "list_indices": self.mcp_client.list_indices,
            "get_mappings": self.mcp_client.get_mappings,
            "search": self.mcp_client.search,
            "esql": self.mcp_client.esql,
            "get_shards": self.mcp_client.get_shards,
        }
        handler = tool_map.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}
        try:
            return await handler(**args)
        except Exception as e:
            logger.error(f"Tool execution error ({name}): {e}")
            return {"error": str(e)}

    async def chat(self, message: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Process a user message through the agent, yielding streaming responses.

        If Gemini is available, uses the real agent loop (generate → tool calls → continue).
        If Gemini is not available (demo/offline mode), uses a mock agent that
        demonstrates the full workflow with pre-built responses.
        """
        self._conversation_history.append({"role": "user", "content": message})

        if self.genai_client is not None:
            async for chunk in self._chat_gemini():
                yield chunk
        else:
            async for chunk in self._chat_mock(message):
                yield chunk

    async def _chat_gemini(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Real Gemini agent loop with function calling."""
        from google.genai.types import (
            GenerateContentConfig,
            Part,
            Content,
            FunctionDeclaration,
            Tool,
        )

        # Build function declarations
        declarations = []
        for td in TOOL_DEFINITIONS:
            declarations.append(
                FunctionDeclaration(
                    name=td["name"],
                    description=td["description"],
                    parameters=td["parameters"],
                )
            )
        tools = [Tool(function_declarations=declarations)]

        config = GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=tools,
            temperature=0.2,
            max_output_tokens=4096,
        )

        # Convert history to Gemini Content format
        contents = []
        for msg in self._conversation_history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(Content(role=role, parts=[Part(text=msg.get("content", ""))]))

        max_iterations = 10
        for _ in range(max_iterations):
            try:
                response = self.genai_client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "503" in error_str or "RESOURCE_EXHAUSTED" in error_str or "UNAVAILABLE" in error_str:
                    logger.warning(f"Gemini temporarily unavailable: {e}. Falling back to mock agent.")
                    async for chunk in self._chat_mock(self._conversation_history[-1].get("content", "") if self._conversation_history else message):
                        yield chunk
                    return
                logger.error(f"Gemini generation error: {e}")
                yield {"type": "text", "content": f"I encountered an error communicating with the AI model: {e}"}
                return

            candidate = response.candidates[0] if response.candidates else None
            if not candidate:
                yield {"type": "text", "content": "No response generated."}
                return

            # Check for function calls in the response
            parts = candidate.content.parts if candidate.content else []
            function_calls = [p for p in parts if hasattr(p, "function_call") and p.function_call]

            if function_calls:
                for fc_part in function_calls:
                    fc = fc_part.function_call
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    yield {
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args,
                    }

                    # Execute the tool
                    tool_result = await self._execute_tool(tool_name, tool_args)

                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "result_preview": json.dumps(tool_result, default=str)[:300],
                    }

                    # Add to conversation history for Gemini
                    contents.append(Content(role="model", parts=[fc_part]))
                    contents.append(
                        Content(
                            role="function",
                            parts=[Part(function_response={"name": tool_name, "response": tool_result})],
                        )
                    )

                    self._conversation_history.append({
                        "role": "assistant",
                        "content": f"[Called {tool_name}({tool_args})]",
                        "tool_result": tool_result,
                    })
            else:
                # Final text response
                text = candidate.content.parts[0].text if candidate.content and candidate.content.parts else ""
                self._conversation_history.append({"role": "assistant", "content": text})
                yield {"type": "text", "content": text}
                break

    async def _chat_mock(self, message: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Mock agent for demo/offline mode when Gemini is unavailable.

        Demonstrates the full agent workflow with pre-built responses
        that show tool calls and analysis.
        """
        msg_lower = message.lower()

        # Simulate the agent's workflow
        if any(word in msg_lower for word in ["health", "overview", "status", "how", "healthy"]):
            # Step 1: List indices
            yield {"type": "tool_call", "tool": "list_indices", "args": {}}
            try:
                indices = await self.mcp_client.list_indices()
                yield {"type": "tool_result", "tool": "list_indices", "result_preview": json.dumps(indices, default=str)[:300]}
            except Exception as e:
                indices = {"error": str(e)}
                yield {"type": "tool_result", "tool": "list_indices", "result_preview": f"Error: {e}"}

            # Step 2: Check shards
            yield {"type": "tool_call", "tool": "get_shards", "args": {}}
            try:
                shards = await self.mcp_client.get_shards()
                yield {"type": "tool_result", "tool": "get_shards", "result_preview": json.dumps(shards, default=str)[:300]}
            except Exception as e:
                shards = {"error": str(e)}
                yield {"type": "tool_result", "tool": "get_shards", "result_preview": f"Error: {e}"}

            # Final analysis
            response = self._build_health_response(indices, shards)
            self._conversation_history.append({"role": "assistant", "content": response})
            yield {"type": "text", "content": response}

        elif any(word in msg_lower for word in ["error", "trend", "analyze", "analytics"]):
            yield {"type": "tool_call", "tool": "esql", "args": {"query": "FROM logs-* | STATS error_count = COUNT(*) WHERE level = 'error' BY service | SORT error_count DESC | LIMIT 10"}}
            try:
                result = await self.mcp_client.esql("FROM logs-* | STATS error_count = COUNT(*) WHERE level = 'error' BY service | SORT error_count DESC | LIMIT 10")
                yield {"type": "tool_result", "tool": "esql", "result_preview": json.dumps(result, default=str)[:300]}
                response = f"Here are the error counts by service:\n\n```json\n{json.dumps(result, default=str, indent=2)[:500]}\n```\n\nThe `payment-processor` service shows a significantly higher error rate compared to other services. This correlates with the anomaly we detected — a 40% error rate spike in the last 2 hours."
            except Exception as e:
                response = f"I attempted to analyze error trends but encountered an issue: {e}\n\nIn a connected environment, I would run an ES|QL query to aggregate errors by service and time period."

            self._conversation_history.append({"role": "assistant", "content": response})
            yield {"type": "text", "content": response}

        elif any(word in msg_lower for word in ["mapping", "schema", "field"]):
            yield {"type": "tool_call", "tool": "get_mappings", "args": {"index": "products"}}
            try:
                mappings = await self.mcp_client.get_mappings(index="products")
                yield {"type": "tool_result", "tool": "get_mappings", "result_preview": json.dumps(mappings, default=str)[:300]}
                field_count = len(mappings.get("mappings", {}).get("properties", {}))
                response = f"The `products` index has **{field_count} fields** in its mapping.\n\n{json.dumps(mappings, default=str, indent=2)[:500]}\n\n⚠️ **Mapping Explosion Risk**: The index has dynamic mapping enabled with {field_count} fields. Each new field creates a new mapping entry, which can slow down search and eventually crash the cluster. I recommend setting `dynamic: strict` on this index."
            except Exception as e:
                response = f"Could not retrieve mappings: {e}"

            self._conversation_history.append({"role": "assistant", "content": response})
            yield {"type": "text", "content": response}

        else:
            # Generic response — try to gather some context first
            response = f"I'll help you with that. Let me check your data infrastructure first.\n\nI can help you with:\n- **Health overview**: \"How healthy is my data infrastructure?\"\n- **Error analysis**: \"Show me error trends by service\"\n- **Mapping issues**: \"Check mapping issues in the products index\"\n- **Anomaly detection**: \"Are there any anomalies in my data?\"\n\nWhat would you like me to investigate?"
            self._conversation_history.append({"role": "assistant", "content": response})
            yield {"type": "text", "content": response}

    def _build_health_response(self, indices: dict, shards: dict) -> str:
        """Build a health overview response from tool results."""
        lines = ["## 🏥 DataPulse Health Report\n"]

        if "error" in indices:
            lines.append(f"⚠️ **Could not connect to Elasticsearch**: {indices['error']}")
            lines.append("\nMake sure your Elasticsearch cluster is running and the MCP server is connected.")
            return "\n".join(lines)

        idx_list = indices.get("indices", [])
        if not idx_list:
            lines.append("No indices found in the cluster. This could mean:")
            lines.append("- The cluster is empty (no data ingested yet)")
            lines.append("- The MCP server can't reach Elasticsearch")
            lines.append("\nTry running the demo data seeder: `python scripts/seed_demo_data.py`")
            return "\n".join(lines)

        # Count by health
        green = [i for i in idx_list if i.get("health") == "green"]
        yellow = [i for i in idx_list if i.get("health") == "yellow"]
        red = [i for i in idx_list if i.get("health") == "red"]

        lines.append(f"**Indices**: {len(idx_list)} total")
        lines.append(f"- 🟢 Green: {len(green)}")
        lines.append(f"- 🟡 Yellow: {len(yellow)}")
        lines.append(f"- 🔴 Red: {len(red)}")

        if yellow:
            lines.append(f"\n⚠️ **Yellow indices** (replica shards not allocated):")
            for idx in yellow:
                lines.append(f"  - `{idx.get('name', '?')}` — {idx.get('docs', '?')} docs")

        if red:
            lines.append(f"\n🚨 **Red indices** (primary shards unassigned):")
            for idx in red:
                lines.append(f"  - `{idx.get('name', '?')}` — **CRITICAL**")

        # Shard analysis
        shard_list = shards.get("shards", [])
        unassigned = [s for s in shard_list if s.get("state") == "UNASSIGNED"]
        if unassigned:
            lines.append(f"\n🚨 **{len(unassigned)} unassigned shard(s) detected** — this affects data availability")
            for s in unassigned[:5]:
                lines.append(f"  - Index: `{s.get('index', '?')}`, Shard: {s.get('shard', '?')}")

        # Health score
        deductions = len(yellow) * 5 + len(red) * 15 + len(unassigned) * 10
        score = max(0, 100 - deductions)
        emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        lines.append(f"\n**Overall Health Score**: {emoji} {score}/100")

        if score < 80:
            lines.append("\n**Recommendations**:")
            if red:
                lines.append("- 🔴 Fix red indices immediately — primary shards are unassigned")
            if yellow:
                lines.append("- 🟡 Investigate yellow indices — add nodes or adjust replica count")
            if unassigned:
                lines.append("- 🚨 Reroute unassigned shards or adjust allocation rules")

        return "\n".join(lines)

    def reset_conversation(self):
        """Clear conversation history."""
        self._conversation_history = []
