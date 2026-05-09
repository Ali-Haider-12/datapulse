#!/bin/bash
# DataPulse Codespaces Startup Script
set -e

echo "🚀 Starting DataPulse in Codespaces..."

# Start mock Elasticsearch
cd /workspaces/datapulse/backend
source .venv/bin/activate
python scripts/mock_es_server.py --port 9201 &
ES_PID=$!
echo "✅ Mock ES started on port 9201 (PID: $ES_PID)"

# Start backend
ES_URL=http://localhost:9201 MCP_SERVER_URL=http://localhost:8080/mcp uvicorn app.main:app --host 0.0.0.0 --port 8001 &
BE_PID=$!
echo "✅ Backend API started on port 8001 (PID: $BE_PID)"

# Start frontend
cd /workspaces/datapulse/frontend
npm run dev -- --host 0.0.0.0 --port 3000 &
FE_PID=$!
echo "✅ Frontend started on port 3000 (PID: $FE_PID)"

echo ""
echo "═══════════════════════════════════════"
echo "  🎉 DataPulse is running!"
echo "═══════════════════════════════════════"
echo "  Frontend:  https://$CODESPACE_NAME-3000.app.github.dev"
echo "  Backend:   https://$CODESPACE_NAME-8001.app.github.dev"
echo "  Mock ES:   https://$CODESPACE_NAME-9201.app.github.dev"
echo ""
echo "  Connect to ES: http://localhost:9201"
echo "═══════════════════════════════════════"

# Keep script alive
wait
