#!/bin/bash
set -e
cd /workspaces/datapulse

# Backend
if [ ! -d "backend/.venv" ]; then
  python3 -m venv backend/.venv
fi
source backend/.venv/bin/activate
pip install -q fastapi uvicorn httpx pydantic-settings pydantic 2>&1 | tail -3

pkill -f uvicorn 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
sleep 2

cd /workspaces/datapulse/backend
nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/backend.log 2>&1 &
sleep 8

cd /workspaces/datapulse/frontend
nohup npm run dev -- --hostname 0.0.0.0 --port 3000 > /tmp/frontend.log 2>&1 &
sleep 15

echo "BACKEND:"
curl -s http://localhost:8001/health
echo ""
echo "FRONTEND:"
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/
echo ""
echo "PROCS:"
ps aux | grep -E "uvicorn|next dev|node" | grep -v grep
echo "=== READY ==="
