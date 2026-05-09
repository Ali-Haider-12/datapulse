# DataPulse — Real-Time Elasticsearch Monitoring & Incident Response

**AI-powered infrastructure monitoring that detects, diagnoses, and remediates issues before your users notice.**

## 🚀 TL;DR

DataPulse is a full-stack monitoring platform that watches your Elasticsearch clusters, detects anomalies, runs AI-powered diagnostics, and either auto-remediates or escalates to your team via War Rooms with concurrent agent investigation.

## The Problem

- Elasticsearch failures cascade silently — a single misbehaving query can tank your entire cluster
- Traditional monitoring tools alert you *after* users are affected
- Incident response is manual, slow, and inconsistent across teams
- Postmortems take hours to write and lessons learned are never captured

## What We Built

### Core Architecture
```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐
│   Sensors    │───▶│  MCP Client  │───▶│  Central Bus  │
│ (ES Metrics) │    │  (Elastic)   │    │   (Pub/Sub)   │
└─────────────┘    └──────────────┘    └───────┬───────┘
                                               │
                        ┌──────────────────────┤
                        ▼                      ▼
               ┌─────────────┐       ┌────────────────┐
               │ Health      │       │  War Room      │
               │ Analyzer    │       │  (Async Agents)│
               │ - Detection │       │  - Detector    │
               │ - Prediction│       │  - Investigator│
               │ - Alerting  │       │  - Fixer       │
               └──────┬──────┘       └────────────────┘
                      │
               ┌──────▼──────┐
               │  Dashboard  │
               │  (Next.js)  │
               │  + WebSocket│
               └─────────────┘
```

### 12 Integrated Features
1. **Elastic Health Monitor** — Real-time cluster/node/index health via MCP
2. **Smart Alerting** — Context-aware alerts filtered by severity, not noise
3. **WebSocket Dashboard** — Live updates without page refresh
4. **AI Chat Interface** — Natural language queries about your ES data
5. **Voice Commands** — Hands-free operation via Twilio ("Hey DataPulse, start patrol")
6. **Async War Room** — When incidents hit, 3 AI agents work concurrently:
   - Detector: Identifies anomalies across shards, mappings, error rates
   - Investigator: Root cause analysis with confidence scoring
   - Fixer: Executes remediation with approval gates
7. **Impact Calculator** — Revenue impact, customer effect, SLA tracking
8. **Incident Manager** — Full CRUD lifecycle with timelines
9. **Query Cache** — 60s TTL to prevent repeated heavy ES queries
10. **Auto-Recovery** — State persisted to disk, survives restarts
11. **Postmortem Generator** — Auto-generates HTML/Markdown postmortems with lessons learned
12. **Multi-LLM Fallback** — Gemini → OpenRouter → DeepSeek → Mock (never goes dark)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 + TypeScript + React |
| Backend | Python 3.13 + FastAPI + Pydantic |
| Database | Elasticsearch (via MCP Server) |
| AI | Gemini 2.0 + OpenRouter + local Mock |
| Real-time | WebSocket + Server-Sent Events |
| Voice | Twilio Programmable Voice |
| Caching | In-memory TTL + optional Redis |
| Testing | pytest + pytest-asyncio (71 tests) |

## Live Demo

The dashboard auto-updates as new data flows in. The "Demo Seed" button populates sample data so you can see everything in action without connecting to a real cluster.

## Architecture Decisions

- **Why MCP?** — The Model Context Protocol lets us swap Elasticsearch for any data source without changing our AI agents
- **Why War Rooms?** — Parallel agent execution cuts incident response from minutes to seconds
- **Why layered caching?** — Repeated queries cost real money on managed ES; 60s TTL saves 80%+ of redundant calls
- **Why multi-LLM?** — If one provider is down or rate-limited, we seamlessly fall back (and log every fallback for analysis)

## Hackathon Differentiators

1. **Self-healing infrastructure** — Not just monitoring, but *fixing* problems automatically
2. **Voice-first design** — The only ES monitoring tool you can operate while cooking dinner
3. **Revenue-aware alerting** — We don't just count errors; we tell you how much money you're losing
4. **Zero-config deployment** — Docker Compose up and running in 2 minutes
5. **71 automated tests** — Because we take reliability seriously

## Repository Structure

```
datapulse/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/                # Route handlers
│   │   ├── models/             # Pydantic schemas
│   │   ├── services/           # Business logic
│   │   │   ├── war_room.py     # Async multi-agent system
│   │   │   ├── health_analyzer.py
│   │   │   ├── llm_provider.py
│   │   │   ├── impact_calculator.py
│   │   │   └── postmortem.py
│   │   └── core/               # Config and lifecycle
│   └── tests/                  # 71 tests
├── frontend/                   # Next.js dashboard
│   └── src/app/components/
├── mcp-server/                 # MCP server for ES
├── docker/                     # Dockerfiles
└── scripts/                    # Demo data generators
```

## Future Improvements

- Multi-cluster support with federated health views
- Slack/PagerDuty integration for alert routing
- ML-based anomaly detection (Isolation Forest on historical metrics)
- Automated runbook execution via CI/CD hooks
- Grafana data source plugin

## Try It

```bash
git clone https://github.com/Ali-Haider-12/datapulse.git
cd datapulse
docker compose up --build
# Open http://localhost:3000
```

---

*Built with ❤️ for the Google Cloud Rapid Agent Hackathon*