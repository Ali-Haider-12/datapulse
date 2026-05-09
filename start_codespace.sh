#!/bin/bash
# DataPulse Codespaces Full Start — run after codespace wakes up
echo "🧹 Cleaning old processes..."
pkill -f uvicorn 2>/dev/null
pkill -f mock_es 2>/dev/null
pkill -f "next dev" 2>/dev/null
sleep 2

echo "🔴 Starting Mock Elasticsearch (port 9201)..."
cd /workspaces/datapulse/backend
source .venv/bin/activate
python3 scripts/mock_es_server.py --port 9201 > /tmp/es.log 2>&1 &
ES_PID=$!
sleep 3
if curl -s http://localhost:9201/_cluster/health > /dev/null 2>&1; then
    echo "   ✅ Mock ES running (PID $ES_PID)"
else
    echo "   ❌ Mock ES failed — check /tmp/es.log"
    cat /tmp/es.log | tail -5
fi

echo "⚙️ Starting Backend API (port 8001)..."
export ES_URL=http://localhost:9201
uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/backend.log 2>&1 &
BE_PID=$!
sleep 6
if curl -s http://localhost:8001/ > /dev/null 2>&1; then
    echo "   ✅ Backend running (PID $BE_PID)"
else
    echo "   ❌ Backend failed — check /tmp/backend.log"
    tail -10 /tmp/backend.log
fi

echo "🎨 Starting Frontend (port 3000)..."
cd /workspaces/datapulse/frontend
npm run dev -- --hostname 0.0.0.0 --port 3000 > /tmp/frontend.log 2>&1 &
FE_PID=$!
sleep 8
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q "200"; then
    echo "   ✅ Frontend running (PID $FE_PID)"
else
    echo "   ⏳ Frontend still starting..."
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  🎉 DataPulse Services Started!"
echo "═══════════════════════════════════════════"
echo "  Mock ES:  http://localhost:9201"
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:3000"
echo "═══════════════════════════════════════════"

# Keep script running so processes aren't orphaned
wait
