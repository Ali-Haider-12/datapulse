#!/bin/bash
set -eo pipefail
cd /workspaces/datapulse

echo "=== DataPulse Startup ==="

# Create venv symlink if not present
if [ ! -d "backend/.venv" ]; then
    ln -s /home/codespace/.python/current backend/.venv 2>/dev/null || true
fi

# Activate venv
if [ -f "backend/.venv/bin/activate" ]; then
    source backend/.venv/bin/activate
else
    source /opt/conda/etc/profile.d/conda.sh 2>/dev/null || true
fi

export PYTHONPATH=/workspaces/datapulse/backend:/workspaces/datapulse/backend/app:$PYTHONPATH
export ES_URL=http://localhost:9201

echo "PYTHONPATH=$PYTHONPATH"
echo "ES_URL=$ES_URL"

# Start mock ES
echo "Starting Mock ES on :9201..."
python3 backend/scripts/mock_es_server.py --port 9201 > /tmp/es.log 2>&1 &
ES_PID=$!
echo "Mock ES pid: $ES_PID"

# Wait for ES
for i in {1..15}; do
    if curl -s http://localhost:9201/ > /dev/null 2>&1; then
        echo "Mock ES ready"
        break
    fi
    sleep 1
done

# Start backend API
echo "Starting Backend API on :8001..."
cd /workspaces/datapulse/backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/api.log 2>&1 &
API_PID=$!
echo "API pid: $API_PID"

# Wait for API
for i in {1..15}; do
    if curl -s http://localhost:8001/api/health > /dev/null 2>&1; then
        echo "Backend API ready"
        break
    fi
    sleep 1
done

# Start frontend
echo "Starting Frontend on :3000..."
cd /workspaces/datapulse/frontend
npm run dev -- --hostname 0.0.0.0 --port 3000 > /tmp/frontend.log 2>&1 &
FE_PID=$!
echo "Frontend pid: $FE_PID"

echo "=== All services started ==="
echo "Frontend: https://stunning-bassoon-4jg5wxg649937ppr.github.dev"
echo "Backend:  http://localhost:8001"
echo "Mock ES:  http://localhost:9201"
echo ""
echo "Logs:"
echo "  tail -f /tmp/es.log"
echo "  tail -f /tmp/api.log"
echo "  tail -f /tmp/frontend.log"

# Keep script running
wait