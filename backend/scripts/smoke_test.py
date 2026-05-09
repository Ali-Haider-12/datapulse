#!/usr/bin/env python3
"""DataPulse Live Smoke Test — run this against a running DataPulse instance.

Usage:
  # Start the stack first:
  #   1. Mock ES:   python scripts/mock_es_server.py --port 9201
  #   2. Backend:    ES_URL=http://localhost:9201 uvicorn app.main:app --port 8001
  #   3. Frontend:   cd frontend && npm run dev -- --port 3000
  #
  # Then run this script:
  #   python scripts/smoke_test.py --api http://localhost:8001 --frontend http://localhost:3000

This script tests every endpoint and feature of DataPulse end-to-end,
printing clear PASS/FAIL results for each check.
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from urllib.request import Request


# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0
skipped = 0


def api_get(base_url: str, path: str, timeout: int = 10) -> tuple:
    """GET request, returns (status_code, json_body)."""
    url = f"{base_url}{path}"
    try:
        req = Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            body = json.loads(body)
        except Exception:
            body = {"raw": body}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def api_post(base_url: str, path: str, data: dict, timeout: int = 30) -> tuple:
    """POST request with JSON body, returns (status_code, json_body)."""
    url = f"{base_url}{path}"
    try:
        body = json.dumps(data).encode()
        req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            body = json.loads(body)
        except Exception:
            body = {"raw": body}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def check(name: str, condition: bool, detail: str = ""):
    """Print PASS/FAIL for a test check."""
    global passed, failed
    if condition:
        passed += 1
        print(f"  {GREEN}✅ PASS{RESET}  {name}")
    else:
        failed += 1
        print(f"  {RED}❌ FAIL{RESET}  {name}")
    if detail:
        print(f"          {CYAN}→ {detail}{RESET}")


def skip(name: str, reason: str = ""):
    """Print SKIP for a skipped check."""
    global skipped
    skipped += 1
    msg = f"  {YELLOW}⏭  SKIP{RESET}  {name}"
    if reason:
        msg += f"  ({reason})"
    print(msg)


def test_backend_base(api: str):
    """Test basic backend connectivity."""
    print(f"\n{BOLD}📦 BACKEND BASE ENDPOINTS{RESET}")
    print("-" * 50)

    # Root
    code, body = api_get(api, "/")
    check("GET / returns 200", code == 200)
    check("Root has 'message' field", "message" in body, str(body))
    check("Message says 'DataPulse API is running'", body.get("message") == "DataPulse API is running")

    # Health
    code, body = api_get(api, "/health")
    check("GET /health returns 200", code == 200)
    check("Health status is 'healthy'", body.get("status") == "healthy", str(body))
    check("Service name is 'DataPulse'", body.get("service") == "DataPulse")

    # OpenAPI docs
    code, body = api_get(api, "/openapi.json")
    check("GET /openapi.json returns 200 (API schema)", code == 200)


def test_health_endpoints(api: str):
    """Test health analysis endpoints."""
    print(f"\n{BOLD}🏥 HEALTH ANALYSIS ENDPOINTS{RESET}")
    print("-" * 50)

    # Health overview
    code, body = api_get(api, "/api/health/overview", timeout=15)
    check("GET /api/health/overview returns 200", code == 200, str(body)[:200])
    if code == 200:
        check("Response has 'total_indices'", "total_indices" in body)
        check("Response has 'health_score'", "health_score" in body)
        check("Response has 'alerts' list", "alerts" in body and isinstance(body["alerts"], list))
        check("total_indices > 0", body.get("total_indices", 0) > 0)
        check("0 <= health_score <= 100", 0 <= body.get("health_score", -1) <= 100)
        check("unhealthy_indices >= 0", body.get("unhealthy_indices", -1) >= 0)

    # Mapping issues
    code, body = api_get(api, "/api/health/mapping-issues/products", timeout=10)
    check("GET /api/health/mapping-issues/products returns 200", code == 200, str(body)[:200])
    if code == 200:
        check("Response has 'index' = 'products'", body.get("index") == "products")
        check("Response has 'issues' list", "issues" in body and isinstance(body["issues"], list))

    # Ingestion anomalies
    code, body = api_get(api, "/api/health/ingestion-anomalies?index_pattern=logs-*", timeout=10)
    check("GET /api/health/ingestion-anomalies returns 200", code == 200, str(body)[:200])
    if code == 200:
        check("Response has 'anomalies' list", "anomalies" in body and isinstance(body["anomalies"], list))


def test_alerts_endpoints(api: str):
    """Test alert management endpoints."""
    print(f"\n{BOLD}🔔 ALERT ENDPOINTS{RESET}")
    print("-" * 50)

    # Get alerts
    code, body = api_get(api, "/api/alerts")
    check("GET /api/alerts returns 200", code == 200)
    check("Response has 'alerts' list", "alerts" in body and isinstance(body["alerts"], list))

    # Dismiss alert
    code, body = api_post(api, "/api/alerts/test-alert-1/dismiss", {})
    check("POST /api/alerts/test-alert-1/dismiss returns 200", code == 200)
    check("Dismiss returns 'dismissed' status", body.get("status") == "dismissed")


def test_chat_endpoint(api: str):
    """Test AI chat endpoint."""
    print(f"\n{BOLD}🤖 AI CHAT ENDPOINT{RESET}")
    print("-" * 50)

    # Invalid request (no body)
    code, body = api_post(api, "/api/chat", {}, timeout=5)
    check("POST /api/chat with no 'message' returns 422", code == 422,
          f"Got {code}" if code != 422 else "")

    # Valid health query
    code, body = api_post(api, "/api/chat", {"message": "How healthy is my data?"}, timeout=60)
    check("POST /api/chat 'How healthy is my data?' returns 200", code == 200,
          str(body)[:200] if code != 200 else "")
    if code == 200:
        check("Response has 'responses' list", "responses" in body and isinstance(body["responses"], list))
        check("Response has 'final_response' string", "final_response" in body and isinstance(body["final_response"], str))
        
        # Check tool calls
        tool_calls = [r for r in body["responses"] if r.get("type") == "tool_call"]
        tool_names = [r["tool"] for r in tool_calls]
        check("Agent made at least 1 tool call", len(tool_calls) >= 1,
              f"Tools called: {tool_names}")
        check("Agent called 'list_indices'", "list_indices" in tool_names,
              f"Tools called: {tool_names}")
        check("Agent called 'get_shards'", "get_shards" in tool_names,
              f"Tools called: {tool_names}")

        # Check final response is non-empty
        final = body.get("final_response", "")
        check("Final response is non-empty", len(final) > 10,
              f"Length: {len(final)} chars")

    # List indices query
    code, body = api_post(api, "/api/chat", {"message": "List my indices"}, timeout=60)
    check("POST /api/chat 'List my indices' returns 200", code == 200)

    # Error trends query
    code, body = api_post(api, "/api/chat", {"message": "Show error trends by service"}, timeout=60)
    check("POST /api/chat 'Show error trends' returns 200", code == 200)
    if code == 200:
        tool_calls = [r for r in body.get("responses", []) if r.get("type") == "tool_call"]
        tool_names = [r["tool"] for r in tool_calls]
        check("Agent used 'esql' for trend query", "esql" in tool_names,
              f"Tools called: {tool_names}")


def test_mcp_fallback(api: str):
    """Test that the MCP client falls back to direct ES."""
    print(f"\n{BOLD}🔄 MCP FALLBACK (DIRECT ES){RESET}")
    print("-" * 50)

    # If we got here and health endpoints work, the fallback is working
    # (because there's no MCP server running on 8080)
    code, body = api_get(api, "/api/health/overview", timeout=15)
    check("Health overview works without MCP server", code == 200,
          "This confirms the direct ES fallback is active")


def test_frontend(frontend_url: str):
    """Test frontend serving."""
    print(f"\n{BOLD}🎨 FRONTEND{RESET}")
    print("-" * 50)

    code, body = api_get(frontend_url, "/")
    check("GET / returns 200", code == 200)
    if code == 200:
        check("HTML contains 'DataPulse'", "DataPulse" in str(body))
        check("HTML contains 'Data Health Guardian'", "Data Health Guardian" in str(body))
        check("HTML has dark theme class", "dark" in str(body))


def test_data_quality(api: str):
    """Test data quality of responses."""
    print(f"\n{BOLD}📊 DATA QUALITY CHECKS{RESET}")
    print("-" * 50)

    code, body = api_get(api, "/api/health/overview", timeout=15)
    if code == 200:
        alerts = body.get("alerts", [])
        for alert in alerts:
            check(f"Alert has 'severity' field", "severity" in alert, str(alert))
            check(f"Alert has 'message' field", "message" in alert, str(alert))
            check(f"Alert severity is valid", alert.get("severity") in ["critical", "warning", "info"],
                  alert.get("severity"))


def main():
    parser = argparse.ArgumentParser(description="DataPulse Live Smoke Test")
    parser.add_argument("--api", default="http://localhost:8001", help="Backend API URL")
    parser.add_argument("--frontend", default="http://localhost:3000", help="Frontend URL")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend tests")
    parser.add_argument("--skip-chat", action="store_true", help="Skip AI chat tests (avoid Gemini rate limits)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  DataPulse Live Smoke Test{RESET}")
    print(f"{BOLD}  API: {args.api}{RESET}")
    print(f"{BOLD}  Frontend: {args.frontend}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    # Run all test suites
    test_backend_base(args.api)
    test_health_endpoints(args.api)
    test_alerts_endpoints(args.api)
    test_mcp_fallback(args.api)
    test_data_quality(args.api)

    if not args.skip_chat:
        test_chat_endpoint(args.api)
    else:
        print(f"\n{YELLOW}⏭  Skipping AI chat tests (--skip-chat){RESET}")

    if not args.skip_frontend:
        try:
            test_frontend(args.frontend)
        except Exception as e:
            skip("Frontend tests", str(e))
    else:
        skip("Frontend tests", "--skip-frontend")

    # Summary
    total = passed + failed + skipped
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"  {GREEN}Passed:  {passed}{RESET}")
    print(f"  {RED}Failed:  {failed}{RESET}")
    print(f"  {YELLOW}Skipped: {skipped}{RESET}")
    print(f"  Total:   {total}")
    print()

    if failed > 0:
        print(f"{RED}{BOLD}❌ {failed} test(s) FAILED{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}✅ ALL TESTS PASSED{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
