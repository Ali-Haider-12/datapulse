#!/bin/bash
echo "=== DataPulse services starting ==="

# NOTE: services are launched by postStartCommand in subshells
# This script is kept for reference and manual debugging
cd /workspaces/datapulse

source backend/.venv/bin/activate
export PYTHONPATH=/workspaces/datapulse/backend:/workspaces/datapulse/backend/app
export ES_URL=http://localhost:9201

# Start mock ES
python3 backend/scripts/mock_es_server.py --port 9201 &
echo "Mock ES started on :9201"

sleep 3

# Start backend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
echo "Backend API started on :8001"

sleep 2

# Start frontend
cd ../frontend
npm run dev -- --hostname 0.0.0.0 --port 3000 &
echo "Frontend started on :3000"

echo "=== All services running ==="
echo "Frontend: https://glorious-goldfish-4jg5wxg64v43g5g.github.dev"
echo "API: http://localhost:8001"
echo "Mock ES: http://localhost:9201"

wait