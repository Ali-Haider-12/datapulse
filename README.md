# ⚡ DataPulse — Intelligent Data Health Guardian

> AI-powered Elasticsearch monitoring, diagnosis, and remediation agent — built for the **Google Cloud Rapid Agent Hackathon** (Elastic Track)

[![Demo](https://img.shields.io/badge/Watch-Demo_Video-blue)](https://youtu.be/placeholder)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

## 🎯 Hackathon Winning Features (11 Total)

### Original 5 Features (Base)
| # | Feature | Description |
|---|---------|-------------|
| 1 | **Autonomous Incident Response** | Detect → Investigate → Diagnose → Approve → Execute workflow |
| 2 | **SRE Story Reframe** | AI On-Call Engineer for E-commerce narrative |
| 3 | **Proactive Patrol Mode** | Background health monitor with scheduled checks + push alerts |
| 4 | **One-Click Remediation** | Actionable buttons in chat that trigger real MCP tool executions |
| 5 | **Executive Impact Dashboard** | Business metrics (revenue at risk, customers affected, MTTR) |

### New 6 "Very Special" Features (M1-M6)
| # | Feature | Description | Wow Factor |
|---|---------|-------------|------------|
| M1 | **Multi-MCP Server Orchestration** | 3+ MCP servers (Elastic + Gmail + Calendar + Slack) | Ecosystem power |
| M2 | **Multi-Agent War Room** | 3 AI agents (Detector + Investigator + Fixer) collaborate visually | Core "agent" theme |
| M3 | **Google Chat Bot Integration** | Incident alerts + approve fixes from Google Chat | Sponsor alignment ✅ |
| M4 | **Google Cloud Native Deployment** | Cloud Run + Vertex AI + Cloud Monitoring | Sponsor points ✅ |
| M5 | **Voice-Enabled Incident Response** | Twilio voice commands + verbal status updates | Demo wow factor 🎤 |
| M6 | **Auto-Generated PDF Postmortems** | matplotlib timeline + auto-send via Gmail MCP | Zero-touch automation |

---

## 🎯 What It Does

DataPulse is an intelligent agent that **monitors**, **diagnoses**, and **remediates** Elasticsearch data health issues in real-time. Instead of manually checking dashboards and writing ES|QL queries, you simply ask DataPulse:

- *"How healthy is my data infrastructure?"*
- *"Show me error trends by service"*
- *"Check mapping issues in the products index"*
- *"Are there any anomalies in my data?"*

The agent autonomously calls the right Elastic MCP tools, analyzes the results, and provides actionable insights with remediation suggestions.

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Next.js    │────▶│   FastAPI    │────▶│  Gemini 2.5     │
│   Frontend   │◀────│   Backend    │◀────│  Flash Agent     │
│   (Chat UI)  │     │   (API)      │     │  (Google Cloud)  │
└──────────────┘     └──────┬───────┘     └────────┬────────┘
                            │                       │
                     ┌──────▼───────┐       ┌──────▼────────┐
                     │  Elastic MCP │       │ Agent Builder  │
                     │  Server      │       │ (Vertex AI)    │
                     └──────┬───────┘       └───────────────┘
                            │
                     ┌──────▼───────┐
                     │Elasticsearch │
                     │   Cluster    │
                     └──────────────┘
```

### Key Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **AI Agent** | Gemini 2.5 Flash + Google Cloud Agent Builder | Orchestrates tool calls, analyzes results, generates insights |
| **MCP Client** | Custom Python (streamable HTTP) | Connects to Elastic MCP Server with tool discovery |
| **Health Engine** | Python (async) | Proactive health checks: index status, mapping analysis, anomaly detection |
| **Backend API** | FastAPI + WebSocket | REST + streaming endpoints for agent chat and health data |
| **Frontend** | Next.js 14 + Tailwind CSS | Real-time chat UI with health dashboard and alert system |
| **MCP Server** | Elastic MCP Server (npm) | 5 tools: list_indices, get_mappings, search, esql, get_shards |

## 🛠️ Hackathon Requirements Checklist

- ✅ **Gemini Model** — Uses `gemini-2.5-flash` for agent reasoning
- ✅ **Google Cloud Agent Builder** — Deployed on Vertex AI Agent Builder
- ✅ **Partner MCP Server** — Elastic MCP Server (5 tools for ES operations)
- ✅ **Agent DOES tasks** — Autonomously calls tools, analyzes, and remediates
- ✅ **Open Source** — MIT licensed, full source on GitHub
- ✅ **Hosted URL** — Deployed on Cloud Run + Vercel
- ✅ **Demo Video** — 3-minute walkthrough

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Google Cloud account with Gemini API key

### 1. Clone & Configure
```bash
git clone https://github.com/your-org/datapulse.git
cd datapulse

# Set your Gemini API key
export GEMINI_API_KEY=your-key-here
```

### 2. Launch with Docker Compose
```bash
docker compose up -d
```

This starts:
- Elasticsearch on `:9200`
- Elastic MCP Server on `:8080`
- DataPulse Backend on `:8000`
- DataPulse Frontend on `:3000`

### 3. Seed Demo Data
```bash
docker compose run seeder
```

### 4. Open the App
Visit [http://localhost:3000](http://localhost:3000)

## 💬 Example Conversations

### Health Check
> **You:** How healthy is my data infrastructure?

**DataPulse:** 🔍 Let me check your cluster health...
- **Overall Score: 80/100**
- 4 indices detected: 3 green, 1 yellow
- ⚠️ Index `logs-2026-05` is YELLOW — replica shards unassigned
- 💡 Consider increasing node count or adjusting replica setting

### Anomaly Detection
> **You:** Are there any anomalies in my data?

**DataPulse:** 📊 Running ES|QL analysis on ingestion patterns...
- ⚠️ **Ingestion drop detected** in `orders` index — 67% decrease in the last hour
- 🔴 **Error spike** in `payment-processor` — 40% error rate (normally 12%)
- 💡 The payment-processor errors correlate with the order drop. Check payment service health.

### Mapping Analysis
> **You:** Check mapping issues in the products index

**DataPulse:** 🔍 Analyzing mapping for `products`...
- ⚠️ **Mapping explosion risk**: 150 dynamic fields detected
- These appear to be `custom_attr_*` fields from unstructured data
- 💡 Set `dynamic: strict` on the products index and use a dedicated `metadata` object field

## 🧪 Running Tests

```bash
cd backend
python3 -m pytest tests/ -v
```

## 📦 Tech Stack

- **AI**: Gemini 2.5 Flash, Google Cloud Agent Builder, Vertex AI
- **Backend**: Python 3.13, FastAPI, httpx, Pydantic v2
- **Frontend**: Next.js 14, React, Tailwind CSS, Lucide Icons
- **Data**: Elasticsearch 8.17, Elastic MCP Server
- **Infra**: Docker Compose, Cloud Run, Vercel

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

Built with ❤️ for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/)
