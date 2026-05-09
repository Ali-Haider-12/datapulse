#!/bin/bash
set -e

echo "🚀 Starting DataPulse..."

# 1. Start Mock Elasticsearch
cd /app/backend
python scripts/mock_es_server.py --port ${ES_PORT:-9201} &
ES_PID=$!
echo "✅ Mock ES on port ${ES_PORT:-9201}"

# Wait for ES to be ready
sleep 2

# 2. Start Backend API
ES_URL=http://localhost:${ES_PORT:-9201} \
MCP_SERVER_URL=http://localhost:8080/mcp \
uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8001} &
BE_PID=$!
echo "✅ Backend API on port ${BACKEND_PORT:-8001}"

# 3. Start Frontend
cd /app/frontend/standalone
PORT=${FRONTEND_PORT:-3000} node server.js &
FE_PID=$!
echo "✅ Frontend on port ${FRONTEND_PORT:-3000}"

echo ""
echo "═══════════════════════════════════"
echo "  🎉 DataPulse is live!"
echo "═══════════════════════════════════"

# Keep alive — shutdown cleanly on SIGTERM
trap "kill $ES_PID $BE_PID $FE_PID 2>/dev/null; exit 0" SIGTERM SIGINT
wait
