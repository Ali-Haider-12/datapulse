#!/bin/bash
# Run all DataPulse tests
set -e

echo "============================================"
echo "  DataPulse Test Suite Runner"
echo "============================================"
echo ""

cd /opt/data/datapulse/backend

# Check Python
echo "Checking Python environment..."
python3 -c "import sys; print(f'Python {sys.version}')"

# Install test deps if needed
echo "Installing test dependencies..."
pip install pytest pytest-asyncio httpx --quiet 2>/dev/null || true

# Run tests
echo ""
echo "Running tests..."
echo "--------------------------------------------"

python3 -m pytest tests/test_all.py -v \
    --tb=short \
    --timeout=60 \
    2>&1 | tee /tmp/test_results.log

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "--------------------------------------------"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ ALL TESTS PASSED"

    # Summary
    TOTAL=$(grep -c "PASSED\|FAILED\|ERROR" /tmp/test_results.log || true)
    PASSED=$(grep -c "PASSED" /tmp/test_results.log || echo "0")
    echo "   Total assertions: ~$TOTAL"
    echo "   Passed: $PASSED"
else
    echo "❌ SOME TESTS FAILED"
    grep -E "FAILED|ERROR" /tmp/test_results.log | head -20
fi

echo ""
echo "============================================"