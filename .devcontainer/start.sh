#!/bin/bash
set -eo pipefail
cd /workspaces/datapulse

echo "=== Starting DataPulse Services ==="

# Start mock ES in background
python3 backend/scripts/mock_es_server.py --port 9201 > /tmp/es.log 2>&1 &
echo "Mock ES started on :9201 (pid: $!)"

# Wait for ES to be ready
for i in {1..15}; do
    if curl -s http://localhost:9201/ > /dev/null 2>&1; then
        echo "Mock ES is ready"
        break
    fi
    echo "Waiting for Mock ES... ($i/15)"
    sleep 1
done

# Start backend
cd backend
source .venv/bin/activate
export ES_URL=http://localhost:9201
uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/api.log 2>&1 &
echo "Backend API started on :8001 (pid: $!)"

# Wait for API
for i in {1..15}; do
    if curl -s http://localhost:8001/api/health > /dev/null 2>&1; then
        echo "Backend API is ready"
        break
    fi
    echo "Waiting for Backend API... ($i/15)"
    sleep 1
done

# Start frontend
cd ../frontend
npm run dev -- --hostname 0.0.0.0 --port 3000 > /tmp/frontend.log 2>&1 &
echo "Frontend started on :3000 (pid: $!)"

echo "=== All services started ==="

# Keep script alive
wait