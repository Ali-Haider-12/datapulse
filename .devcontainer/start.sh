#!/bin/bash
set -e
cd /workspaces/datapulse

echo "=== Starting DataPulse Services ==="

# Start mock ES
python3 backend/scripts/mock_es_server.py --port 9201 &
echo "Mock ES starting on :9201"

sleep 3

# Start backend API
cd backend
source .venv/bin/activate
export ES_URL=http://localhost:9201
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
echo "Backend API starting on :8001"

sleep 2

# Start frontend
cd ../frontend
npm run dev -- --hostname 0.0.0.0 --port 3000 &
echo "Frontend starting on :3000"

echo "=== All services started ==="
wait