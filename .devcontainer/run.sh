#!/bin/bash
set -eo pipefail
exec > >(tee /tmp/boot.log) 2>&1
echo "=== Boot DataPulse $(date) ==="

cd /workspaces/datapulse
source backend/.venv/bin/activate
export ES_URL=http://localhost:9201
export PYTHONPATH=/workspaces/datapulse/backend:/workspaces/datapulse/backend/app

# Start mock ES
echo "Starting Mock ES..."
python3 backend/scripts/mock_es_server.py --port 9201 &
sleep 2
echo "ES PID: $(pgrep -f mock_es_server)"

# Start API
echo "Starting API..."
cd /workspaces/datapulse/backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
sleep 2
echo "API PID: $(pgrep -f uvicorn)"

# Start frontend
echo "Starting Frontend..."
cd /workspaces/datapulse/frontend
npx next dev --hostname 0.0.0.0 --port 3000 &
sleep 2
echo "FE PID: $(pgrep -f next)"

echo "=== Boot done ==="
cat /tmp/boot.log

# Keep alive - wait forever
tail -f /dev/null