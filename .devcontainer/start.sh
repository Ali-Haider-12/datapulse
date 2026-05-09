#!/bin/bash
cd /workspaces/datapulse

# Activate venv
if [ -f "backend/.venv/bin/activate" ]; then
    source backend/.venv/bin/activate
fi

export PYTHONPATH=/workspaces/datapulse/backend:/workspaces/datapulse/backend/app
export ES_URL=http://localhost:9201

echo "=== Starting services ==="

# Mock ES
python3 backend/scripts/mock_es_server.py --port 9201 &
echo "ES started"

sleep 3

# Backend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &
echo "API started"

sleep 2

# Frontend
cd /workspaces/datapulse/frontend
npx next dev --hostname 0.0.0.0 --port 3000 &
echo "Frontend started"

echo "=== All services running ==="
wait