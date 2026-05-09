# DataPulse — Intelligent Data Health Guardian: Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a Gemini-powered AI agent on Google Cloud Agent Builder that integrates the Elastic MCP server to provide 24/7 intelligent data infrastructure monitoring, anomaly prediction, auto-diagnosis, and corrective action — all via natural language.

**Hackathon:** Google Cloud Rapid Agent Hackathon (Elastic Track)
**Deadline:** Jun 11, 2026
**Prize:** $5,000 (1st in Elastic track), $3,000 (2nd), $2,000 (3rd)

**Architecture:** DataPulse is a web application with a conversational AI agent frontend backed by Gemini 2.5 Flash on Google Cloud Agent Builder. The agent connects to Elasticsearch via the Elastic MCP server (5 tools: `list_indices`, `get_mappings`, `search`, `esql`, `get_shards`). The agent proactively monitors data health, detects anomalies using ES|QL aggregations, and can take corrective action (reindex, adjust shards, alert). A FastAPI backend orchestrates MCP server communication, and a React+Tailwind frontend provides the chat UI with live dashboard panels.

**Tech Stack:**
- **AI Engine:** Google Cloud Vertex AI Agent Builder + Gemini 2.5 Flash
- **MCP Integration:** Elastic MCP Server (Docker container, streamable-HTTP)
- **Backend:** Python 3.11 + FastAPI + google-cloud-aiplatform SDK
- **Frontend:** Next.js 14 + React + Tailwind CSS + shadcn/ui
- **Database:** SQLite (agent session state, alert history)
- **Elasticsearch:** Elastic Cloud free trial (for demo data)
- **Hosting:** Vercel (frontend) + Google Cloud Run (backend)
- **Testing:** pytest (backend), Vitest (frontend)

---

## Demo Flow (What Judges Will See)

1. **Landing page** — DataPulse dashboard with "Connect to Elasticsearch" button
2. **Connection** — User enters ES credentials or uses pre-loaded demo cluster
3. **Dashboard loads** — Shows indices overview, health scores, anomaly timeline
4. **Natural language query** — User types: "How healthy is my data infrastructure?"
5. **Agent responds** — "I found 3 indices with concerning patterns. The `logs-2026-05` index has 2 unassigned shards and a 40% increase in error rate over the last 24 hours. The `products` index mapping has 15 new fields without explicit mapping, which could cause mapping explosions."
6. **Proactive alert** — A notification appears: "⚠️ Anomaly detected: `orders` index ingestion rate dropped 60% in the last hour"
7. **Corrective action** — User: "Fix the unassigned shards" → Agent: "I've triggered shard rerouting for `logs-2026-05`. 2 shards are now initializing. Estimated recovery: 3 minutes."
8. **Analytics deep-dive** — User: "Show me error trends by service over the last week" → Agent generates ES|QL query, returns visual chart
9. **Walk away impressed** — Agent is clearly DOING things, not just chatting

---

## Task Breakdown

### P0 Tasks (Must-Have for Demo)

### Task 1: Project Infrastructure Setup

**Objective:** Initialize the project skeleton with all directories, configs, and CI.

**Files:**
- Create: `/opt/data/hackathon/datapulse/` (root)
- Create: `backend/` directory
- Create: `frontend/` directory
- Create: `README.md`
- Create: `.gitignore`
- Create: `backend/requirements.txt`
- Create: `backend/pyproject.toml`
- Create: `docker-compose.yml` (Elastic MCP server + demo ES)

**Step 1: Create project structure**

```bash
cd /opt/data/hackathon/datapulse
mkdir -p backend/app/{api,core,models,services} backend/tests frontend/src/{app,components,lib} .github/workflows
```

**Step 2: Initialize git**

```bash
git init
```

**Step 3: Write .gitignore**

```
__pycache__/
*.pyc
.env
.venv/
node_modules/
.next/
*.db
dist/
```

**Step 4: Write README.md**

```markdown
# DataPulse — Intelligent Data Health Guardian

🏆 **Google Cloud Rapid Agent Hackathon** (Elastic Track)

An AI agent powered by Gemini + Google Cloud Agent Builder that monitors your Elasticsearch data infrastructure 24/7, predicts anomalies, auto-diagnoses issues, and takes corrective action — all via natural language.

## Quick Start
```bash
# Backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev

# Elastic MCP Server
docker-compose up -d
```

## Tech Stack
- Google Cloud Vertex AI Agent Builder + Gemini
- Elastic MCP Server
- FastAPI + Next.js + Tailwind
```

**Step 5: Write docker-compose.yml**

```yaml
version: '3.8'
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data

  kibana:
    image: docker.elastic.co/kibana/kibana:8.15.0
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    depends_on:
      - elasticsearch

  elastic-mcp:
    image: docker.elastic.co/mcp/elasticsearch:latest
    environment:
      - ES_URL=http://elasticsearch:9200
      - ES_USERNAME=elastic
      - ES_PASSWORD=changeme
    ports:
      - "8080:8080"
    command: http
    depends_on:
      - elasticsearch

volumes:
  es_data:
```

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: initialize project structure with docker-compose"
```

---

### Task 2: Backend Core — FastAPI Application Shell

**Objective:** Set up the FastAPI application with CORS, health check, and project structure.

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/requirements.txt`
- Test: `backend/tests/test_main.py`

**Step 1: Write requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
google-cloud-aiplatform==1.150.0
httpx==0.27.0
pydantic==2.9.0
pydantic-settings==2.5.0
python-dotenv==1.0.1
sqlalchemy==2.0.35
aiosqlite==0.20.0
websockets==12.0
mcp==1.9.0
```

**Step 2: Write config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "DataPulse"
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    ES_URL: str = "http://localhost:9200"
    ES_API_KEY: str = ""
    ES_USERNAME: str = "elastic"
    ES_PASSWORD: str = "changeme"
    MCP_SERVER_URL: str = "http://localhost:8080/mcp"
    DATABASE_URL: str = "sqlite+aiosqlite:///./datapulse.db"

    class Config:
        env_file = ".env"

settings = Settings()
```

**Step 3: Write main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.PROJECT_NAME}

@app.get("/")
async def root():
    return {"message": "DataPulse API is running", "docs": "/docs"}
```

**Step 4: Write test**

```python
# backend/tests/test_main.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_root():
    response = client.get("/")
    assert response.status_code == 200
```

**Step 5: Run tests**

```bash
cd /opt/data/hackathon/datapulse/backend && pip install -r requirements.txt && pytest tests/test_main.py -v
```

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: add FastAPI application shell with config and health check"
```

---

### Task 3: Elastic MCP Client Service

**Objective:** Build a service that communicates with the Elastic MCP server using the streamable-HTTP protocol. This is the critical integration point.

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/mcp_client.py`
- Test: `backend/tests/test_mcp_client.py`

**Step 1: Write failing test**

```python
# backend/tests/test_mcp_client.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.mcp_client import ElasticMCPClient

@pytest.mark.asyncio
async def test_list_indices():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    with patch.object(client, '_call_tool', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"indices": [{"name": "logs-2026-05", "health": "yellow"}]}
        result = await client.list_indices()
        mock_call.assert_called_once_with("list_indices", {})
        assert "indices" in result

@pytest.mark.asyncio
async def test_search():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    with patch.object(client, '_call_tool', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"hits": {"total": 5, "hits": []}}
        result = await client.search(index="logs-*", body={"query": {"match_all": {}}})
        mock_call.assert_called_once()
        assert "hits" in result

@pytest.mark.asyncio
async def test_esql_query():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    with patch.object(client, '_call_tool', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"columns": ["timestamp", "count"], "values": []}
        result = await client.esql("FROM logs-* | STATS count = COUNT(*) BY timestamp")
        mock_call.assert_called_once_with("esql", {"query": "FROM logs-* | STATS count = COUNT(*) BY timestamp"})
        assert "columns" in result

@pytest.mark.asyncio
async def test_get_shards():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    with patch.object(client, '_call_tool', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"shards": []}
        result = await client.get_shards(index="logs-*")
        assert "shards" in result

@pytest.mark.asyncio
async def test_get_mappings():
    client = ElasticMCPClient(base_url="http://localhost:8080")
    with patch.object(client, '_call_tool', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"mappings": {"properties": {}}}
        result = await client.get_mappings(index="logs-*")
        assert "mappings" in result
```

**Step 2: Run tests to verify failure**

```bash
cd /opt/data/hackathon/datapulse/backend && pytest tests/test_mcp_client.py -v
```

**Step 3: Write implementation**

```python
# backend/app/services/mcp_client.py
import httpx
import json
import asyncio
from typing import Any, Dict, Optional

class ElasticMCPClient:
    """Client for communicating with the Elastic MCP Server via streamable-HTTP protocol."""

    def __init__(self, base_url: str = "http://localhost:8080", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.mcp_endpoint = f"{self.base_url}/mcp"
        self.api_key = api_key
        self._request_id = 0

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server using JSON-RPC 2.0."""
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

            # Handle SSE response
            content_type = response.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                return self._parse_sse_response(response.text)
            return response.json().get("result", response.json())

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
```

**Step 4: Run tests to verify pass**

```bash
cd /opt/data/hackathon/datapulse/backend && pytest tests/test_mcp_client.py -v
```

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: add Elastic MCP client service with all 5 tools"
```

---

### Task 4: Gemini Agent Service (Google Cloud Agent Builder Integration)

**Objective:** Build the AI agent service using Google Cloud Vertex AI + Gemini that orchestrates MCP tool calls based on user queries.

**Files:**
- Create: `backend/app/services/agent.py`
- Create: `backend/app/services/agent_tools.py`
- Create: `backend/app/services/health_analyzer.py`
- Test: `backend/tests/test_agent.py`

**Step 1: Write agent_tools.py (tool definitions for the agent)**

```python
# backend/app/services/agent_tools.py
"""Tool definitions that the Gemini agent can call via function declarations."""

TOOL_DEFINITIONS = [
    {
        "name": "list_indices",
        "description": "List all Elasticsearch indices with their health status, document count, and size. Use this to get an overview of the data infrastructure.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_mappings",
        "description": "Get the field mappings/schema for a specific Elasticsearch index. Use this to understand the structure of data in an index and detect mapping issues like mapping explosions.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "string", "description": "The name of the Elasticsearch index to get mappings for"}
            },
            "required": ["index"],
        },
    },
    {
        "name": "search",
        "description": "Search Elasticsearch indices using query DSL. Use this to find specific documents, error patterns, or investigate data anomalies.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "string", "description": "The index name or pattern (e.g., 'logs-*')"},
                "body": {"type": "object", "description": "The Elasticsearch query DSL body"}
            },
            "required": ["index", "body"],
        },
    },
    {
        "name": "esql",
        "description": "Execute an ES|QL (Elasticsearch Query Language) query for analytics, aggregations, and time-series analysis. ES|QL is powerful for health analysis, anomaly detection, and trend calculations.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The ES|QL query string (e.g., 'FROM logs-* | STATS error_count = COUNT(*) WHERE level = \"error\" BY timestamp')"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_shards",
        "description": "Get shard information for Elasticsearch indices including allocation status, unassigned shards, and shard health. Use this to diagnose cluster health issues.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "string", "description": "Optional index name to filter shard info"}
            },
            "required": [],
        },
    },
]

SYSTEM_INSTRUCTION = """You are DataPulse, an intelligent data health guardian. Your job is to monitor, diagnose, and help fix Elasticsearch data infrastructure issues.

Your personality:
- Proactive: Don't just answer questions — anticipate problems and alert the user
- Analytical: Use data from Elasticsearch to back up your insights
- Action-oriented: When you find issues, suggest specific corrective actions
- Clear: Explain technical concepts in plain language

When the user asks about their data health:
1. First, use list_indices to get an overview
2. Check shard health with get_shards for any concerning indices
3. Use esql to analyze trends, error rates, and anomalies
4. Use get_mappings to check for mapping issues
5. Synthesize findings into a clear health report with specific recommendations

For corrective actions, explain what you would do and ask for confirmation before making changes.

Always provide specific numbers and data points — never be vague. Say "40% increase in error rate" not "errors went up."
"""
```

**Step 2: Write agent.py**

```python
# backend/app/services/agent.py
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
from google.cloud import aiplatform
from google.genai import Client as GenAIClient
from google.genai.types import GenerateContentConfig, Part, Content, FunctionDeclaration, Tool

from app.core.config import settings
from app.services.mcp_client import ElasticMCPClient
from app.services.agent_tools import TOOL_DEFINITIONS, SYSTEM_INSTRUCTION

logger = logging.getLogger(__name__)


class DataPulseAgent:
    """Gemini-powered agent that orchestrates Elastic MCP tool calls."""

    def __init__(self, mcp_client: ElasticMCPClient):
        self.mcp_client = mcp_client
        self._genai_client = None
        self._conversation_history: List[Content] = []

    @property
    def genai_client(self):
        if self._genai_client is None:
            self._genai_client = GenAIClient(
                vertexai=True,
                project=settings.GOOGLE_CLOUD_PROJECT,
                location=settings.GOOGLE_CLOUD_LOCATION,
            )
        return self._genai_client

    def _build_tools(self) -> List[Tool]:
        """Convert tool definitions to Gemini function declarations."""
        declarations = []
        for td in TOOL_DEFINITIONS:
            declarations.append(
                FunctionDeclaration(
                    name=td["name"],
                    description=td["description"],
                    parameters=td["parameters"],
                )
            )
        return [Tool(function_declarations=declarations)]

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
        """Process a user message through the agent, yielding streaming responses."""
        # Add user message to history
        self._conversation_history.append(
            Content(role="user", parts=[Part(text=message)])
        )

        config = GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=self._build_tools(),
            temperature=0.2,
            max_output_tokens=4096,
        )

        # Agent loop: generate → check for tool calls → execute → continue
        max_iterations = 10
        for _ in range(max_iterations):
            response = await self._generate(config)

            # Check for function calls
            if response.function_calls:
                for fc in response.function_calls:
                    tool_result = await self._execute_tool(fc.name, fc.args or {})

                    # Add function call and result to history
                    self._conversation_history.append(
                        Content(
                            role="model",
                            parts=[Part(function_call=fc)],
                        )
                    )
                    self._conversation_history.append(
                        Content(
                            role="function",
                            parts=[
                                Part(
                                    function_response={
                                        "name": fc.name,
                                        "response": tool_result,
                                    }
                                )
                            ],
                        )
                    )

                    yield {
                        "type": "tool_call",
                        "tool": fc.name,
                        "args": fc.args,
                        "result_preview": str(tool_result)[:200],
                    }
            else:
                # Final text response
                text = response.text or ""
                self._conversation_history.append(
                    Content(role="model", parts=[Part(text=text)])
                )
                yield {"type": "text", "content": text}
                break

    async def _generate(self, config: GenerateContentConfig):
        """Generate a response from Gemini."""
        response = self.genai_client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=self._conversation_history,
            config=config,
        )
        return response.candidates[0].content if response.candidates else None

    def reset_conversation(self):
        """Clear conversation history."""
        self._conversation_history = []
```

**Step 3: Write health_analyzer.py**

```python
# backend/app/services/health_analyzer.py
"""Proactive health analysis engine that runs background checks on ES data."""

from typing import Any, Dict, List, Optional
from app.services.mcp_client import ElasticMCPClient

class HealthAnalyzer:
    """Analyzes Elasticsearch data health and generates alerts."""

    def __init__(self, mcp_client: ElasticMCPClient):
        self.mcp_client = mcp_client

    async def get_health_overview(self) -> Dict[str, Any]:
        """Get a comprehensive health overview of all indices."""
        indices = await self.mcp_client.list_indices()
        shards = await self.mcp_client.get_shards()

        alerts = []
        unhealthy_indices = []
        total_docs = 0
        total_size = 0

        for idx in indices.get("indices", []):
            health = idx.get("health", "unknown")
            if health == "red":
                alerts.append({
                    "severity": "critical",
                    "index": idx.get("name"),
                    "message": f"Index {idx.get('name')} is RED — some shards are unassigned",
                })
                unhealthy_indices.append(idx)
            elif health == "yellow":
                alerts.append({
                    "severity": "warning",
                    "index": idx.get("name"),
                    "message": f"Index {idx.get('name')} is YELLOW — replica shards not allocated",
                })

        # Check for unassigned shards
        unassigned = [s for s in shards.get("shards", []) if s.get("state") == "UNASSIGNED"]
        if unassigned:
            alerts.append({
                "severity": "critical",
                "message": f"Found {len(unassigned)} unassigned shard(s)",
                "shards": [s.get("index") for s in unassigned],
            })

        return {
            "total_indices": len(indices.get("indices", [])),
            "unhealthy_indices": len(unhealthy_indices),
            "total_alerts": len(alerts),
            "alerts": alerts,
            "health_score": max(0, 100 - len(alerts) * 10),
        }

    async def detect_mapping_issues(self, index: str) -> List[Dict[str, Any]]:
        """Detect potential mapping explosion issues."""
        mappings = await self.mcp_client.get_mappings(index)
        issues = []

        props = mappings.get("mappings", {}).get("properties", {})
        field_count = len(props)
        dynamic_fields = [k for k, v in props.items() if v.get("dynamic") is not False]

        if field_count > 100:
            issues.append({
                "type": "mapping_explosion_risk",
                "severity": "warning",
                "message": f"Index {index} has {field_count} fields — risk of mapping explosion",
                "recommendation": "Consider setting dynamic=false or dynamic=strict on this index",
            })

        if len(dynamic_fields) > 50:
            issues.append({
                "type": "dynamic_mapping",
                "severity": "info",
                "message": f"{len(dynamic_fields)} fields with dynamic mapping in {index}",
                "recommendation": "Review dynamic fields and set explicit types",
            })

        return issues

    async def analyze_ingestion_anomalies(self, index_pattern: str = "logs-*") -> List[Dict[str, Any]]:
        """Use ES|QL to detect ingestion rate anomalies."""
        query = f"""
        FROM {index_pattern}
        | EVAL hour = DATE_TRUNC(1 hour, @timestamp)
        | STATS doc_count = COUNT(*) BY hour
        | SORT hour DESC
        | LIMIT 48
        """
        try:
            result = await self.mcp_client.esql(query)
            values = result.get("values", [])
            if len(values) >= 2:
                latest = values[0][-1] if values[0] else 0
                previous = values[1][-1] if values[1] else 0
                if previous > 0 and latest / previous < 0.5:
                    return [{
                        "type": "ingestion_drop",
                        "severity": "critical",
                        "message": f"Ingestion rate dropped {int((1 - latest/previous) * 100)}% in the last hour",
                        "current_rate": latest,
                        "previous_rate": previous,
                    }]
            return []
        except Exception:
            return []
```

**Step 4: Write basic tests**

```python
# backend/tests/test_agent.py
import pytest
from unittest.mock import AsyncMock, patch
from app.services.health_analyzer import HealthAnalyzer
from app.services.mcp_client import ElasticMCPClient

@pytest.mark.asyncio
async def test_health_overview():
    mock_client = AsyncMock(spec=ElasticMCPClient)
    mock_client.list_indices.return_value = {
        "indices": [
            {"name": "logs-2026-05", "health": "yellow", "docs": 1000},
            {"name": "products", "health": "green", "docs": 500},
        ]
    }
    mock_client.get_shards.return_value = {"shards": []}

    analyzer = HealthAnalyzer(mock_client)
    result = await analyzer.get_health_overview()

    assert result["total_indices"] == 2
    assert result["total_alerts"] == 1  # yellow index
    assert result["health_score"] == 90

@pytest.mark.asyncio
async def test_mapping_issues_detection():
    mock_client = AsyncMock(spec=ElasticMCPClient)
    # Create a mapping with 150 fields
    props = {f"field_{i}": {"type": "text"} for i in range(150)}
    mock_client.get_mappings.return_value = {"mappings": {"properties": props}}

    analyzer = HealthAnalyzer(mock_client)
    issues = await analyzer.detect_mapping_issues("test-index")

    assert len(issues) >= 1
    assert issues[0]["type"] == "mapping_explosion_risk"
```

**Step 5: Run tests**

```bash
cd /opt/data/hackathon/datapulse/backend && pytest tests/test_agent.py -v
```

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: add Gemini agent service with Elastic MCP tool orchestration"
```

---

### Task 5: API Routes — Chat, Health, Alerts

**Objective:** Create FastAPI routes for the agent chat interface, health dashboard, and alert system.

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/chat.py`
- Create: `backend/app/api/health.py`
- Create: `backend/app/api/alerts.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/schemas.py`
- Test: `backend/tests/test_api.py`

**Step 1: Write schemas**

```python
# backend/app/models/schemas.py
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    type: str  # "text", "tool_call", "error"
    content: Optional[str] = None
    tool: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    result_preview: Optional[str] = None

class HealthOverview(BaseModel):
    total_indices: int
    unhealthy_indices: int
    total_alerts: int
    alerts: List[Dict[str, Any]]
    health_score: int

class Alert(BaseModel):
    severity: str
    index: Optional[str] = None
    message: str
    recommendation: Optional[str] = None

class ESConnectionConfig(BaseModel):
    url: str
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
```

**Step 2: Write chat.py**

```python
# backend/app/api/chat.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.mcp_client import ElasticMCPClient
from app.services.agent import DataPulseAgent
from app.core.config import settings
import json

router = APIRouter()


@router.post("/chat")
async def chat_endpoint(msg: ChatMessage):
    """REST endpoint for agent chat (non-streaming)."""
    from app.models.schemas import ChatMessage, ChatResponse

    mcp_client = ElasticMCPClient(
        base_url=settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0],
        api_key=settings.ES_API_KEY or None,
    )
    agent = DataPulseAgent(mcp_client=mcp_client)

    responses = []
    async for chunk in agent.chat(msg.message):
        responses.append(chunk)

    # Return the final text response
    text_responses = [r for r in responses if r["type"] == "text"]
    return {
        "responses": responses,
        "final_response": text_responses[-1]["content"] if text_responses else "No response generated.",
    }


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming agent chat."""
    await websocket.accept()

    mcp_client = ElasticMCPClient(
        base_url=settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0],
    )
    agent = DataPulseAgent(mcp_client=mcp_client)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data).get("message", "")

            async for chunk in agent.chat(message):
                await websocket.send_text(json.dumps(chunk))

            await websocket.send_text(json.dumps({"type": "done"}))
    except WebSocketDisconnect:
        pass
```

**Step 3: Write health.py**

```python
# backend/app/api/health.py
from fastapi import APIRouter
from app.services.mcp_client import ElasticMCPClient
from app.services.health_analyzer import HealthAnalyzer
from app.core.config import settings

router = APIRouter()


@router.get("/health/overview")
async def health_overview():
    """Get comprehensive Elasticsearch health overview."""
    mcp_client = ElasticMCPClient(
        base_url=settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0],
    )
    analyzer = HealthAnalyzer(mcp_client)
    return await analyzer.get_health_overview()


@router.get("/health/mapping-issues/{index}")
async def mapping_issues(index: str):
    """Check for mapping issues in a specific index."""
    mcp_client = ElasticMCPClient(
        base_url=settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0],
    )
    analyzer = HealthAnalyzer(mcp_client)
    return {"index": index, "issues": await analyzer.detect_mapping_issues(index)}


@router.get("/health/ingestion-anomalies")
async def ingestion_anomalies(index_pattern: str = "logs-*"):
    """Detect ingestion rate anomalies."""
    mcp_client = ElasticMCPClient(
        base_url=settings.MCP_SERVER_URL.rsplit("/mcp", 1)[0],
    )
    analyzer = HealthAnalyzer(mcp_client)
    return {"anomalies": await analyzer.analyze_ingestion_anomalies(index_pattern)}
```

**Step 4: Write alerts.py**

```python
# backend/app/api/alerts.py
from fastapi import APIRouter

router = APIRouter()

# In-memory alert store for demo (replace with SQLite in production)
_alerts_store = []


@router.get("/alerts")
async def get_alerts():
    """Get all active alerts."""
    return {"alerts": _alerts_store}


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str):
    """Dismiss an alert."""
    _alerts_store[:] = [a for a in _alerts_store if a.get("id") != alert_id]
    return {"status": "dismissed"}
```

**Step 5: Update main.py to include routes**

```python
# backend/app/main.py (updated)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import chat, health, alerts

app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(alerts.router, prefix="/api", tags=["alerts"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.PROJECT_NAME}
```

**Step 6: Write tests**

```python
# backend/tests/test_api.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200

def test_alerts_endpoint():
    response = client.get("/api/alerts")
    assert response.status_code == 200
    assert "alerts" in response.json()
```

**Step 7: Run tests**

```bash
cd /opt/data/hackathon/datapulse/backend && pytest tests/ -v
```

**Step 8: Commit**

```bash
git add -A && git commit -m "feat: add API routes for chat, health dashboard, and alerts"
```

---

### Task 6: Demo Data Seeder

**Objective:** Create a script that populates Elasticsearch with realistic demo data (logs, metrics, errors) so the demo works without a real ES cluster.

**Files:**
- Create: `backend/scripts/seed_demo_data.py`
- Create: `backend/scripts/demo_data.json`

**Step 1: Write seed script**

```python
# backend/scripts/seed_demo_data.py
"""
Seed Elasticsearch with realistic demo data for the DataPulse demo.
Creates indices with log data, error patterns, and anomalies.
"""
import httpx
import json
import random
from datetime import datetime, timedelta
import asyncio

ES_URL = "http://localhost:9200"

SERVICES = ["api-gateway", "auth-service", "payment-processor", "user-service", "order-service", "inventory-service", "notification-service"]
LOG_LEVELS = ["info", "info", "info", "info", "warn", "warn", "error", "error", "error", "debug"]
ERROR_TYPES = ["ConnectionTimeout", "RateLimitExceeded", "DatabaseError", "AuthenticationFailed", "ValidationError", "OutOfMemory"]
HTTP_CODES = [200, 200, 200, 200, 201, 301, 400, 401, 403, 404, 500, 502, 503]

async def create_indices():
    """Create demo indices with proper mappings."""
    async with httpx.AsyncClient() as client:
        # Create logs index with explicit mapping
        logs_mapping = {
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "timestamp": {"type": "date"},
                    "level": {"type": "keyword"},
                    "service": {"type": "keyword"},
                    "message": {"type": "text"},
                    "error_type": {"type": "keyword"},
                    "http_code": {"type": "integer"},
                    "response_time_ms": {"type": "float"},
                    "host": {"type": "keyword"},
                },
            },
            "settings": {"number_of_shards": 3, "number_of_replicas": 1},
        }
        await client.put(f"{ES_URL}/logs-2026-05", json=logs_mapping)

        # Create metrics index
        metrics_mapping = {
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "timestamp": {"type": "date"},
                    "service": {"type": "keyword"},
                    "cpu_percent": {"type": "float"},
                    "memory_mb": {"type": "float"},
                    "request_count": {"type": "integer"},
                    "error_count": {"type": "integer"},
                    "avg_latency_ms": {"type": "float"},
                },
            },
            "settings": {"number_of_shards": 1, "number_of_replicas": 1},
        }
        await client.put(f"{ES_URL}/metrics-2026-05", json=metrics_mapping)

        # Create products index (with a few dynamic fields to demo mapping explosion detection)
        products_mapping = {
            "mappings": {
                "dynamic": True,
                "properties": {
                    "name": {"type": "text"},
                    "category": {"type": "keyword"},
                    "price": {"type": "float"},
                    "in_stock": {"type": "boolean"},
                },
            },
        }
        await client.put(f"{ES_URL}/products", json=products_mapping)

        # Create orders index
        orders_mapping = {
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "timestamp": {"type": "date"},
                    "customer_id": {"type": "keyword"},
                    "total": {"type": "float"},
                    "status": {"type": "keyword"},
                    "items": {"type": "integer"},
                },
            },
        }
        await client.put(f"{ES_URL}/orders", json=orders_mapping)

        print("Indices created successfully")


async def seed_logs():
    """Generate 10,000 log entries over the last 7 days with realistic patterns."""
    bulk_data = []
    now = datetime.utcnow()
    base_time = now - timedelta(days=7)

    for i in range(10000):
        ts = base_time + timedelta(minutes=random.randint(0, 7 * 24 * 60))
        level = random.choice(LOG_LEVELS)
        service = random.choice(SERVICES)
        http_code = random.choice(HTTP_CODES)

        # Simulate an anomaly: error spike in the last 2 hours for payment-processor
        if service == "payment-processor" and ts > now - timedelta(hours=2):
            if random.random() < 0.4:  # 40% error rate (vs normal ~15%)
                level = "error"
                http_code = random.choice([500, 502, 503])

        log_entry = {
            "timestamp": ts.isoformat() + "Z",
            "level": level,
            "service": service,
            "message": f"Request processed by {service}" if level != "error" else f"{random.choice(ERROR_TYPES)} in {service}",
            "error_type": random.choice(ERROR_TYPES) if level == "error" else None,
            "http_code": http_code,
            "response_time_ms": round(random.uniform(10, 2000) if level == "error" else random.uniform(5, 200), 2),
            "host": f"host-{random.randint(1, 5)}",
        }

        bulk_data.append(json.dumps({"index": {"_index": "logs-2026-05"}}))
        bulk_data.append(json.dumps(log_entry))

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ES_URL}/_bulk",
            data="\n".join(bulk_data) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
        print(f"Seeded logs: {response.status_code}")


async def seed_products():
    """Seed product data with some dynamic fields to demo mapping issues."""
    bulk_data = []
    categories = ["electronics", "clothing", "books", "home", "toys", "sports"]

    for i in range(500):
        product = {
            "name": f"Product {i}",
            "category": random.choice(categories),
            "price": round(random.uniform(5, 500), 2),
            "in_stock": random.random() > 0.2,
        }
        # Add random dynamic fields (simulating unstructured product data)
        if random.random() < 0.3:
            product[f"custom_attr_{random.randint(1, 80)}"] = random.choice(["value_a", "value_b", "value_c"])

        bulk_data.append(json.dumps({"index": {"_index": "products"}}))
        bulk_data.append(json.dumps(product))

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ES_URL}/_bulk",
            data="\n".join(bulk_data) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
        print(f"Seeded products: {response.status_code}")


async def seed_orders():
    """Seed order data with a recent ingestion drop (anomaly)."""
    bulk_data = []
    now = datetime.utcnow()
    base_time = now - timedelta(days=3)

    for i in range(3000):
        ts = base_time + timedelta(minutes=random.randint(0, 3 * 24 * 60))

        # Simulate ingestion drop: fewer orders in the last hour
        if ts > now - timedelta(hours=1):
            if random.random() < 0.3:  # Only 30% chance (vs normal ~100%)
                continue

        statuses = ["completed", "completed", "completed", "pending", "cancelled", "refunded"]
        order = {
            "timestamp": ts.isoformat() + "Z",
            "customer_id": f"cust-{random.randint(1, 200)}",
            "total": round(random.uniform(10, 500), 2),
            "status": random.choice(statuses),
            "items": random.randint(1, 10),
        }

        bulk_data.append(json.dumps({"index": {"_index": "orders"}}))
        bulk_data.append(json.dumps(order))

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ES_URL}/_bulk",
            data="\n".join(bulk_data) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
        print(f"Seeded orders: {response.status_code}")


async def main():
    await create_indices()
    await seed_logs()
    await seed_products()
    await seed_orders()
    print("Demo data seeded successfully!")


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Commit**

```bash
git add -A && git commit -m "feat: add demo data seeder with realistic anomalies and error patterns"
```

---

### Task 7: Frontend — Next.js Application Shell

**Objective:** Set up the Next.js frontend with Tailwind CSS, shadcn/ui, and the basic layout.

**Files:**
- Create: `frontend/` (Next.js project)
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/src/components/ChatPanel.tsx`
- Create: `frontend/src/components/HealthDashboard.tsx`

**Step 1: Initialize Next.js project**

```bash
cd /opt/data/hackathon/datapulse && npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
```

**Step 2: Install shadcn/ui**

```bash
cd frontend && npx shadcn@latest init
```

**Step 3: Install shadcn components**

```bash
npx shadcn@latest add button card input scroll-area badge alert sheet separator avatar
```

**Step 4: Write layout.tsx**

```tsx
// frontend/src/app/layout.tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "DataPulse — Intelligent Data Health Guardian",
  description: "AI-powered Elasticsearch monitoring, diagnosis, and remediation agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-gray-950 text-gray-100`}>
        {children}
      </body>
    </html>
  );
}
```

**Step 5: Write main page with the 3-panel layout**

```tsx
// frontend/src/app/page.tsx
"use client";

import { useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { ChatPanel } from "@/components/ChatPanel";
import { HealthDashboard } from "@/components/HealthDashboard";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Activity, AlertTriangle, Database, Zap } from "lucide-react";

export default function Home() {
  const [healthScore, setHealthScore] = useState<number | null>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [connected, setConnected] = useState(false);

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <Sidebar connected={connected} onConnect={setConnected} healthScore={healthScore} />

      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {/* Top bar with alerts */}
        {alerts.length > 0 && (
          <div className="p-2 bg-gray-900 border-b border-gray-800 overflow-x-auto flex gap-2">
            {alerts.slice(0, 5).map((alert, i) => (
              <Alert
                key={i}
                variant={alert.severity === "critical" ? "destructive" : "default"}
                className="py-1 px-3 flex items-center gap-2 w-auto"
              >
                <AlertTriangle className="h-3 w-3" />
                <AlertDescription className="text-xs">{alert.message}</AlertDescription>
              </Alert>
            ))}
          </div>
        )}

        {/* Two-panel layout: Dashboard + Chat */}
        <div className="flex-1 flex">
          {/* Health Dashboard */}
          <div className="w-1/2 border-r border-gray-800 overflow-y-auto">
            <HealthDashboard
              onHealthUpdate={setHealthScore}
              onAlerts={setAlerts}
              connected={connected}
            />
          </div>

          {/* Chat Panel */}
          <div className="w-1/2 flex flex-col">
            <ChatPanel connected={connected} />
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 6: Write ChatPanel, Sidebar, and HealthDashboard components**

*(These will be detailed in the implementation phase — the plan defines the interface contract)*

**Step 7: Commit**

```bash
git add -A && git commit -m "feat: add Next.js frontend shell with 3-panel layout"
```

---

### Task 8: Frontend — Chat Interface with WebSocket Streaming

**Objective:** Build the real-time chat interface that streams agent responses and shows tool calls live.

**Files:**
- Create: `frontend/src/components/ChatPanel.tsx`
- Create: `frontend/src/lib/chat-websocket.ts`
- Create: `frontend/src/components/ToolCallCard.tsx`

**Key Implementation:**

The ChatPanel must:
1. Connect to `ws://localhost:8000/api/ws/chat` WebSocket
2. Display streaming text responses as they arrive
3. Show tool call cards in real-time (with spinner → result transition)
4. Support markdown rendering in agent responses
5. Show conversation history with user/agent message bubbles

**Step 1–5:** Implement ChatPanel, WebSocket client, and ToolCallCard (detailed code in implementation phase)

**Step 6: Commit**

```bash
git add -A && git commit -m "feat: add streaming chat interface with WebSocket and tool call visualization"
```

---

### Task 9: Frontend — Health Dashboard with Live Metrics

**Objective:** Build the health dashboard that shows ES index health, alerts timeline, and anomaly visualizations.

**Files:**
- Create: `frontend/src/components/HealthDashboard.tsx`
- Create: `frontend/src/components/IndexHealthCard.tsx`
- Create: `frontend/src/components/AnomalyTimeline.tsx`
- Create: `frontend/src/lib/api.ts`

**Key Features:**
- Auto-refreshing health overview (polls `/api/health/overview` every 30s)
- Index health cards (green/yellow/red badges)
- Health score gauge (0-100)
- Anomaly timeline chart (using recharts)
- Mapping issues panel

**Commit:**

```bash
git add -A && git commit -m "feat: add health dashboard with live metrics and anomaly visualization"
```

---

### Task 10: Integration — End-to-End Demo Wiring

**Objective:** Wire everything together so the full demo flow works.

**Files:**
- Modify: `backend/app/main.py` (add startup event to seed demo data)
- Modify: `frontend/src/lib/api.ts` (configure API base URL)
- Create: `backend/app/core/startup.py`
- Create: `.env.example`

**Step 1: Write .env.example**

```env
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash
ES_URL=http://localhost:9200
ES_API_KEY=
ES_USERNAME=elastic
ES_PASSWORD=changeme
MCP_SERVER_URL=http://localhost:8080/mcp
```

**Step 2: Wire startup to seed data**

**Step 3: Test the full demo flow locally**

```bash
# Terminal 1: Start ES + MCP
cd /opt/data/hackathon/datapulse && docker-compose up -d

# Terminal 2: Seed data
cd backend && python scripts/seed_demo_data.py

# Terminal 3: Start backend
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 4: Start frontend
cd frontend && npm run dev
```

**Step 4: Commit**

```bash
git add -A && git commit -m "feat: wire full end-to-end demo with startup seeding"
```

---

### P1 Tasks (Nice-to-Have)

### Task 11: Proactive Monitoring Background Job
**Priority:** P1
**Description:** Add a background task that periodically runs health checks and pushes alerts to the frontend via WebSocket. Uses APScheduler.

### Task 12: Connection Configuration UI
**Priority:** P1
**Description:** Add a form in the sidebar for users to enter their own ES credentials or switch to the demo cluster.

### Task 13: Dark/Light Theme Toggle
**Priority:** P1
**Description:** Add theme switching with next-themes.

---

### P2 Tasks (If Time Permits)

### Task 14: Corrective Action Execution
**Priority:** P2
**Description:** Actually execute corrective actions (reroute shards, update index settings) via ES REST API (not just MCP tools).

### Task 15: Deployment to Google Cloud Run
**Priority:** P2
**Description:** Deploy backend to Cloud Run, frontend to Vercel, with production ES on Elastic Cloud.

### Task 16: Demo Video Script and Recording
**Priority:** P0 (elevated for submission)
**Description:** Write a 3-minute demo script following the Demo Flow above. Record with OBS or similar.

---

## Priority Summary

| Task | Priority | Description | Est. Time |
|------|----------|-------------|-----------|
| 1 | P0 | Project infrastructure setup | 15 min |
| 2 | P0 | FastAPI application shell | 20 min |
| 3 | P0 | Elastic MCP client service | 30 min |
| 4 | P0 | Gemini agent service | 45 min |
| 5 | P0 | API routes (chat, health, alerts) | 30 min |
| 6 | P0 | Demo data seeder | 30 min |
| 7 | P0 | Frontend Next.js shell | 30 min |
| 8 | P0 | Chat interface with WebSocket | 45 min |
| 9 | P0 | Health dashboard | 45 min |
| 10 | P0 | End-to-end demo wiring | 30 min |
| 11 | P1 | Proactive monitoring job | 20 min |
| 12 | P1 | Connection config UI | 15 min |
| 13 | P1 | Dark/light theme | 10 min |
| 14 | P2 | Corrective action execution | 30 min |
| 15 | P2 | Cloud deployment | 45 min |
| 16 | P0 | Demo video script | 30 min |

**Total P0 estimate:** ~5 hours
**Total P0+P1:** ~6 hours
**Total all:** ~8 hours
