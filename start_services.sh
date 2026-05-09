#!/bin/bash
set -e

echo "Starting DataPulse services..."

# 1. Mock Elasticsearch
cd /workspaces/datapulse/backend
source .venv/bin/activate
python scripts/mock_es_server.py --port 9201 > /tmp/es.log 2>&1 &
echo "Mock ES started on port 9201"

# 2. Backend API
sleep 2
ES_URL=http://localhost:9201 MCP_SERVER_URL=http://localhost:8080/mcp .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/backend.log 2>&1 &
echo "Backend started on port 8001"

# 3. Frontend
sleep 2
cd /workspaces/datapulse/frontend
npm run dev -- --hostname 0.0.0.0 --port 3000 > /tmp/frontend.log 2>&1 &
echo "Frontend started on port 3000"

echo "All services starting! Waiting for health checks..."
sleep 5

# Verify
curl -s http://localhost:9201/_cat/indices > /dev/null 2>&1 && echo "✅ ES OK" || echo "❌ ES FAIL"
curl -s http://localhost:8001/health > /dev/null 2>&1 && echo "✅ Backend OK" || echo "❌ Backend FAIL"
curl -s -o /dev/null http://localhost:3000/ 2>&1 && echo "✅ Frontend OK" || echo "❌ Frontend FAIL"

echo "DONE"
