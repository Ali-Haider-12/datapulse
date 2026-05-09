#!/bin/bash
# DataPulse Codespaces Full Start — v2.1.0
set -e

echo "🧹 Cleaning old processes..."
pkill -f uvicorn 2>/dev/null || true
pkill -f mock_es 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
sleep 2

cd /workspaces/datapulse

# Setup venv if needed
if [ ! -d "backend/.venv" ]; then
    echo "📦 Creating Python venv..."
    python3 -m venv backend/.venv
fi
source backend/.venv/bin/activate
pip install -q fastapi uvicorn httpx pydantic-settings pydantic pytest pytest-asyncio mcp google-genai 2>&1 | tail -3

echo "⚙️ Starting Backend API (port 8001)..."
cd /workspaces/datapulse/backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/backend.log 2>&1 &
BE_PID=$!
sleep 8
if curl -s http://localhost:8001/ > /dev/null 2>&1; then
    echo "   ✅ Backend running (PID $BE_PID)"
else
    echo "   ⚠️  Backend starting up - checking logs..."
    tail -15 /tmp/backend.log
fi

echo "🎨 Starting Frontend (port 3000)..."
cd /workspaces/datapulse/frontend
npm run dev -- --hostname 0.0.0.0 --port 3000 > /tmp/frontend.log 2>&1 &
FE_PID=$!
sleep 10
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "304" ]; then
    echo "   ✅ Frontend running (PID $FE_PID)"
else
    echo "   ⏳ Frontend still building (HTTP $HTTP_CODE)..."
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  🎉 DataPulse v2.1.0 Services!"
echo "═══════════════════════════════════════════"
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:3000"
echo "  Logs:     tail -f /tmp/backend.log"
echo "═══════════════════════════════════════════"

wait