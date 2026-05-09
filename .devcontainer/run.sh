#!/bin/bash
set -e
cd /workspaces/datapulse

export PYTHONPATH=/workspaces/datapulse/backend:/workspaces/datapulse/backend/app
export ES_URL=http://localhost:9201

LOG=/tmp/codespace-boot.log
echo "=== Booting DataPulse at $(date) ===" > $LOG

# Start mock ES
echo "Starting Mock ES..." >> $LOG
nohup python3 backend/scripts/mock_es_server.py --port 9201 >> $LOG 2>&1 &
echo "ES PID: $!" >> $LOG

sleep 2

# Verify ES
if curl -s http://localhost:9201/ | grep -q "datapulse-demo"; then
    echo "Mock ES: OK" >> $LOG
else
    echo "Mock ES: FAILED" >> $LOG
fi

# Start backend API
echo "Starting Backend API..." >> $LOG
nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 >> $LOG 2>&1 &
echo "API PID: $!" >> $LOG

sleep 2

# Verify API
if curl -s http://localhost:8001/api/health | grep -q "OK\|status"; then
    echo "Backend API: OK" >> $LOG
else
    echo "Backend API: FAILED" >> $LOG
fi

# Start frontend
echo "Starting Frontend..." >> $LOG
nohup npx next dev --hostname 0.0.0.0 --port 3000 >> $LOG 2>&1 &
echo "FE PID: $!" >> $LOG

sleep 2

echo "=== Boot complete ===" >> $LOG
echo "Frontend: http://localhost:3000" >> $LOG
echo "API: http://localhost:8001" >> $LOG
echo "ES: http://localhost:9201" >> $LOG

cat $LOG

# Run tests and keep running
echo "=== Running tests ===" >> $LOG
cd /workspaces/datapulse/backend
python3 -m pytest tests/ -v --ignore=tests/test_calendar_mcp.py --ignore=tests/test_gmail_mcp.py --ignore=tests/test_chat_webhook.py --tb=short 2>&1 | tail -15 >> $LOG

# Keep container alive - tail the log forever
tail -f /dev/null