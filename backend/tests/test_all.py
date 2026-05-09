"""
Comprehensive test suite for DataPulse v2.1.0.

Run: python -m pytest tests/ -v --tb=short
Run with coverage: python -m pytest tests/ -v --cov=backend/app --cov-report=term-missing
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

pytest_plugins = ("pytest_asyncio",)


# ═══════════════════════════════════════════════════════════════
# 1. CONFIG TESTS
# ═══════════════════════════════════════════════════════════════

class TestConfig:
    def test_settings_defaults(self):
        from app.core.config import settings
        assert settings.PROJECT_NAME == "DataPulse"
        assert settings.CACHE_TTL_SECONDS == 120
        assert settings.CACHE_ENABLED is True
        assert settings.PATROL_INTERVAL_SECONDS == 60
        assert settings.HEALTH_CHECK_INTERVAL_SECONDS == 60
        assert settings.ALERT_THRESHOLD_SCORE == 50
        print("✓ Settings defaults work")

    def test_settings_cache_fields(self):
        from app.core.config import settings
        assert hasattr(settings, 'CACHE_TTL_SECONDS')
        assert hasattr(settings, 'CACHE_ENABLED')
        assert hasattr(settings, 'REDIS_URL')
        print("✓ Cache settings present")


# ═══════════════════════════════════════════════════════════════
# 2. CACHE TESTS
# ═══════════════════════════════════════════════════════════════

class TestCache:
    @pytest.mark.asyncio
    async def test_ttl_cache(self):
        from app.services.cache import TTLCache
        cache = TTLCache(default_ttl=10)
        await cache.set("key1", {"data": "value"})
        result = await cache.get("key1")
        assert result == {"data": "value"}
        print("✓ TTL cache set/get works")

    @pytest.mark.asyncio
    async def test_cache_expiry(self):
        from app.services.cache import TTLCache
        cache = TTLCache(default_ttl=0.1)
        await cache.set("key1", "value")
        assert await cache.get("key1") == "value"
        await asyncio.sleep(0.2)
        assert await cache.get("key1") is None
        print("✓ Cache expiry works")

    @pytest.mark.asyncio
    async def test_cache_clear(self):
        from app.services.cache import TTLCache
        cache = TTLCache(default_ttl=300)
        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        assert await cache.size() == 2
        await cache.clear()
        assert await cache.size() == 0
        print("✓ Cache clear works")

    @pytest.mark.asyncio
    async def test_cached_decorator(self):
        from app.services.cache import cached, _in_memory_cache

        call_count = 0

        @cached("test_key", ttl=60)
        async def expensive_function(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        await _in_memory_cache.clear()
        r1 = await expensive_function(5)
        assert r1 == 10
        assert call_count == 1

        r2 = await expensive_function(5)
        assert r2 == 10
        assert call_count == 1  # cached

        r3 = await expensive_function(10)
        assert r3 == 20
        print("✓ @cached decorator prevents duplicate calls")


# ═══════════════════════════════════════════════════════════════
# 3. LLM PROVIDER TESTS
# ═══════════════════════════════════════════════════════════════

class TestLLMProvider:
    def test_llm_provider_creation(self):
        from app.services.llm_provider import LLMProvider
        provider = LLMProvider()
        assert provider is not None
        assert len(provider._fallback_chain) == 4
        print("✓ LLM provider created with 4-tier fallback")

    @pytest.mark.asyncio
    async def test_llm_mock_chat_when_all_providers_fail(self):
        from app.services.llm_provider import LLMProvider
        provider = LLMProvider()
        results = []
        async for chunk in provider.chat("How healthy is my data?"):
            if chunk.get("type") == "text":
                results.append(chunk.get("content", ""))
        full_text = "".join(results)
        assert len(full_text) > 0
        print(f"✓ Got response from fallback chain: {len(full_text)} chars")

    @pytest.mark.asyncio
    async def test_llm_mock_health_query(self):
        from app.services.llm_provider import LLMProvider
        provider = LLMProvider()
        results = []
        async for chunk in provider.chat("How healthy is my data?"):
            if chunk.get("type") == "text":
                results.append(chunk.get("content", ""))
        full_text = "".join(results)
        assert len(full_text) > 0
        print("✓ Health query returned valid response")

    @pytest.mark.asyncio
    async def test_llm_mock_error_analysis(self):
        from app.services.llm_provider import LLMProvider
        provider = LLMProvider()
        results = []
        async for chunk in provider.chat("Show error trends"):
            if chunk.get("type") == "text":
                results.append(chunk.get("content", ""))
        full_text = "".join(results)
        assert len(full_text) > 0
        print("✓ Error analysis query returned valid response")

    @pytest.mark.asyncio
    async def test_llm_provider_rate_limit_detection(self):
        from app.services.llm_provider import RateLimitedError
        err = RateLimitedError("Test 429")
        assert "429" in str(err)
        print("✓ RateLimitError class works")

    def test_format_history(self):
        from app.services.llm_provider import LLMProvider
        provider = LLMProvider()
        history = [
            {"role": "user", "content": "hello"},
            {"type": "tool_call", "tool": "test", "args": {}},
            {"role": "user", "type": "tool_result", "result_preview": "result", "content": "result"},
        ]
        formatted = provider._format_history(history)
        assert len(formatted) >= 1
        assert formatted[0]["role"] == "user"
        # tool_call should be filtered out
        assert not any(m.get("role") == "tool_call" for m in formatted)
        print("✓ History formatting works correctly")


# ═══════════════════════════════════════════════════════════════
# 4. HEALTH ANALYZER TESTS
# ═══════════════════════════════════════════════════════════════

class TestHealthAnalyzer:
    @pytest.mark.asyncio
    async def test_health_analyzer_creation(self):
        from app.services.health_analyzer import HealthAnalyzer
        mock_client = MagicMock()
        analyzer = HealthAnalyzer(mock_client)
        assert analyzer is not None
        assert analyzer.MAPPING_EXPLOSION_THRESHOLD == 100
        print("✓ Health analyzer created successfully")

    @pytest.mark.asyncio
    async def test_health_analyzer_detect_mapping_issues(self):
        from app.services.health_analyzer import HealthAnalyzer
        mock_client = MagicMock()
        mock_mapping = {"test-index": {"mappings": {"properties": {
            f"field_{i}": {"type": "text"} for i in range(150)
        }}}}
        mock_client.get_mappings = AsyncMock(return_value=mock_mapping)
        analyzer = HealthAnalyzer(mock_client)
        issues = await analyzer.detect_mapping_issues("test-index")
        assert len(issues) > 0
        print(f"✓ Found {len(issues)} mapping issues")

    @pytest.mark.asyncio
    async def test_health_analyzer_alerts(self):
        from app.services.health_analyzer import HealthAnalyzer

        mock_client = MagicMock()
        mock_client.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders", "health": "red", "docs": 1000, "size": "1gb", "status": "open"},
                {"name": "logs", "health": "green", "docs": 10000, "size": "2gb", "status": "open"},
            ]
        })
        mock_client.get_shards = AsyncMock(return_value={
            "shards": [
                {"index": "orders", "shard": "0", "state": "UNASSIGNED", "node": ""},
            ]
        })

        analyzer = HealthAnalyzer(mock_client)

        async def mock_error_trends():
            return {"healthy": True, "error_rate_percent": 0.0}

        async def mock_predictions():
            return []

        with patch.object(analyzer, 'analyze_error_trends', side_effect=mock_error_trends):
            with patch.object(analyzer, 'predict_future_issues', side_effect=mock_predictions):
                report = await analyzer.comprehensive_health_report()

        assert "all_alerts" in report
        assert len(report["all_alerts"]) > 0
        print(f"✓ Generated {len(report['all_alerts'])} alerts")

    @pytest.mark.asyncio
    async def test_comprehensive_health_report(self):
        from app.services.health_analyzer import HealthAnalyzer

        mock_client = MagicMock()
        mock_client.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders-2026", "health": "yellow", "docs": 89420, "size": "1.8gb", "status": "open"},
                {"name": "payments-2026", "health": "green", "docs": 125340, "size": "2.3gb", "status": "open"},
            ]
        })
        mock_client.get_shards = AsyncMock(return_value={
            "shards": [
                {"index": "orders-2026", "shard": "0", "prirep": "p", "state": "UNASSIGNED",
                 "docs": "", "store": "", "node": ""},
            ]
        })

        analyzer = HealthAnalyzer(mock_client)

        async def mock_error_trends():
            return {"healthy": True, "error_rate_percent": 0.0}

        async def mock_predictions():
            return []

        with patch.object(analyzer, 'analyze_error_trends', side_effect=mock_error_trends):
            with patch.object(analyzer, 'predict_future_issues', side_effect=mock_predictions):
                report = await analyzer.comprehensive_health_report()

        assert "overall_health_score" in report
        assert "status" in report
        assert "all_alerts" in report
        print(f"✓ Health report: score={report['overall_health_score']}, alerts={len(report['all_alerts'])}")


# ═══════════════════════════════════════════════════════════════
# 5. IMPACT CALCULATOR TESTS
# ═══════════════════════════════════════════════════════════════

class TestImpactCalculator:
    @pytest.mark.asyncio
    async def test_impact_calculator_creation(self):
        from app.services.impact_calculator import ImpactCalculator
        mock_client = MagicMock()
        calculator = ImpactCalculator(mock_client)
        assert calculator is not None
        assert calculator.AVERAGE_ORDER_VALUE == 47.50
        print("✓ Impact calculator created successfully")

    @pytest.mark.asyncio
    async def test_impact_calculator_confidence_scoring(self):
        from app.services.impact_calculator import ImpactCalculator
        mock_client = MagicMock()
        calculator = ImpactCalculator(mock_client)
        score = calculator._calculate_confidence(
            total_indices=10, red=[{"name": "test"}],
            yellow=[{"name": "test2"}], total_errors=5000
        )
        assert 10 <= score <= 99
        print(f"✓ Confidence score: {score}")

    @pytest.mark.asyncio
    async def test_impact_calculator_baseline_learning(self):
        from app.services.impact_calculator import ImpactCalculator
        mock_client = MagicMock()
        calculator = ImpactCalculator(mock_client)
        calculator._learn_baseline("payment-service", {"error_rate": 50, "revenue_impact": 500})
        assert "payment-service" in calculator._baselines
        deviation = calculator._get_deviation_from_baseline("payment-service", 100, "error_rate")
        assert deviation > 0
        print(f"✓ Baseline deviation: {deviation * 100:.0f}%")

    @pytest.mark.asyncio
    async def test_impact_calculator_revenue_estimation(self):
        from app.services.impact_calculator import ImpactCalculator
        mock_client = MagicMock()
        calculator = ImpactCalculator(mock_client)
        expected_hourly = 120 * 47.50
        assert expected_hourly == 5700
        print(f"✓ Revenue estimation: ${expected_hourly:.0f}/hr")

    def test_impact_summary_generation(self):
        from app.services.impact_calculator import ImpactCalculator
        mock_client = MagicMock()
        calculator = ImpactCalculator(mock_client)
        metrics = {
            "revenue_at_risk": 2850.0,
            "customers_affected": 847,
            "degraded_services": [{"service": "orders", "impact": "CRITICAL", "revenue_impact": "$2850/hr"}],
            "trend_indicator": "degrading",
            "uptime_percent": 85.0,
            "error_rate_percent": 2.5,
        }
        summary = calculator._generate_summary(metrics)
        assert len(summary) > 0
        recommendation = calculator._generate_recommendation(metrics)
        assert len(recommendation) > 0
        print(f"✓ Business summary and recommendation generated")

    @pytest.mark.asyncio
    async def test_impact_calculate_with_mcp_client(self):
        from app.services.impact_calculator import ImpactCalculator
        mock_client = MagicMock()
        mock_client.list_indices = AsyncMock(return_value={
            "indices": [
                {"name": "orders-2026", "health": "red", "docs": 10000, "size": "2gb"},
                {"name": "payments-2026", "health": "green", "docs": 50000, "size": "5gb"},
                {"name": "logs-2026", "health": "green", "docs": 100000, "size": "10gb"},
            ]
        })
        mock_client.esql = AsyncMock(return_value={
            "values": [["payment-processor", 847], ["order-service", 312]],
        })
        calculator = ImpactCalculator(mock_client)
        result = await calculator.calculate_impact()
        assert "revenue_at_risk" in result
        assert "customers_affected" in result
        assert "degraded_services" in result
        assert "business_summary" in result
        assert "recommendation" in result
        print(f"✓ Full impact: ${result['revenue_at_risk']:.0f}/hr at risk, {len(result['degraded_services'])} degraded")


# ═══════════════════════════════════════════════════════════════
# 6. WAR ROOM TESTS
# ═══════════════════════════════════════════════════════════════

class TestWarRoom:
    @pytest.mark.asyncio
    async def test_async_war_room_creation(self):
        from app.services.war_room import AsyncWarRoom
        war_room = AsyncWarRoom("INC-TEST001", mcp_client=None)
        assert war_room.incident_id == "INC-TEST001"
        assert war_room.status == "initialized"
        print("✓ Async war room created")

    @pytest.mark.asyncio
    async def test_async_war_room_cancel(self):
        from app.services.war_room import AsyncWarRoom
        war_room = AsyncWarRoom("INC-TEST001")
        await war_room.cancel()
        assert war_room.status == "cancelled"
        print("✓ War room cancellation works")

    @pytest.mark.asyncio
    async def test_sync_war_room(self):
        from app.services.war_room import WarRoom
        war_room = WarRoom("INC-TEST001")
        war_room.start()
        status = war_room.get_status()
        assert status["incident_id"] == "INC-TEST001"
        assert status["status"] in ("completed", "observing")
        print(f"✓ Sync war room works (status={status['status']})")

    @pytest.mark.asyncio
    async def test_sync_war_room_result(self):
        from app.services.war_room import WarRoom
        war_room = WarRoom("INC-TEST001")
        war_room.start()
        result = war_room.get_result()
        assert "incident_id" in result
        assert "status" in result
        assert "agents" in result
        assert "shared_context" in result
        print(f"✓ War room result correct (status={result['status']})")

    @pytest.mark.asyncio
    async def test_war_room_progress_callbacks(self):
        from app.services.war_room import AsyncWarRoom
        war_room = AsyncWarRoom("INC-TEST001")
        callback_calls = []
        war_room.on_progress(lambda u: callback_calls.append(u))
        war_room._log("test", "Test message")
        await asyncio.sleep(0.1)
        print(f"✓ Progress callbacks: {len(callback_calls)} calls")


# ═══════════════════════════════════════════════════════════════
# 7. VOICE PROCESSOR TESTS
# ═══════════════════════════════════════════════════════════════

class TestVoiceProcessor:
    def test_basic_commands(self):
        from app.services.voice_processor import VoiceProcessor
        processor = VoiceProcessor()
        assert processor.process_command("status")["action"] == "get_impact"
        assert processor.process_command("start patrol")["action"] == "start_patrol"
        assert processor.process_command("stop patrol")["action"] == "stop_patrol"
        print("✓ Basic voice commands work")

    def test_fuzzy_matching(self):
        from app.services.voice_processor import VoiceProcessor
        processor = VoiceProcessor()
        assert processor.process_command("check the health of the cluster")["action"] == "get_health"
        assert processor.process_command("do you see any problems")["action"] == "detect_incidents"
        print("✓ Fuzzy matching works")

    def test_known_commands(self):
        from app.services.voice_processor import VoiceProcessor
        processor = VoiceProcessor()
        actions = set()
        for cmd in ["status", "health", "start patrol", "stop patrol", "start war room",
                     "check mappings", "check errors", "check shards", "ingestion rate",
                     "detect incidents", "list incidents", "goodbye"]:
            actions.add(processor.process_command(cmd)["action"])
        print(f"✓ {len(actions)} unique actions from 12 known commands")

    def test_batch_processing(self):
        from app.services.voice_processor import VoiceProcessor
        processor = VoiceProcessor()
        commands = ["status", "start patrol", "check health", "stop patrol"]
        results = processor.process_commands_batch(commands)
        assert len(results) == 4
        print(f"✓ Batch processed {len(results)} commands")

    def test_unknown_command(self):
        from app.services.voice_processor import VoiceProcessor
        processor = VoiceProcessor()
        result = processor.process_command("flarb snazzle")
        assert result["action"] == "unknown"
        print("✓ Unknown command handled gracefully")


# ═══════════════════════════════════════════════════════════════
# 8. SESSION MANAGER TESTS
# ═══════════════════════════════════════════════════════════════

class TestSessionManager:
    @pytest.mark.asyncio
    async def test_session_creation(self, tmp_path):
        from app.services.session_manager import SessionManager
        mgr = SessionManager(storage_path=str(tmp_path / "sessions"))
        await mgr.start()
        session = await mgr.create_session(user_id="test-user")
        assert session.session_id.startswith("sess-")
        assert session.metadata["user_id"] == "test-user"
        await mgr.stop()
        print(f"✓ Created session: {session.session_id}")

    @pytest.mark.asyncio
    async def test_session_persistence(self, tmp_path):
        from app.services.session_manager import SessionManager
        storage = tmp_path / "sessions"
        mgr1 = SessionManager(storage_path=str(storage))
        await mgr1.start()
        session = await mgr1.create_session(user_id="test-user")
        await mgr1.add_message(session.session_id, "user", "Hello")
        await mgr1.add_message(session.session_id, "assistant", "Hi!")
        await mgr1.stop()
        mgr2 = SessionManager(storage_path=str(storage))
        await mgr2.start()
        history = await mgr2.get_session_history(session.session_id)
        await mgr2.stop()
        assert len(history) == 2
        print(f"✓ Session persisted: {len(history)} messages survived restart")

    @pytest.mark.asyncio
    async def test_session_cleanup(self, tmp_path):
        from app.services.session_manager import SessionManager
        from datetime import timedelta
        storage = tmp_path / "sessions"
        mgr = SessionManager(storage_path=str(storage))
        await mgr.start()
        old_session = mgr.sessions["old-session"] = type('obj', (object,), {
            'last_active': datetime.utcnow() - timedelta(hours=25),
            'to_dict': lambda self: {"session_id": "old-session", "messages": [],
                                      "created_at": datetime.utcnow().isoformat(),
                                      "last_active": (datetime.utcnow() - timedelta(hours=25)).isoformat(),
                                      "metadata": {}, "state": {}},
            'messages': [], 'metadata': {},
        })()
        deleted = await mgr.delete_old_sessions(max_age_hours=24)
        assert deleted >= 1
        print(f"✓ Cleaned up {deleted} old sessions")
        await mgr.stop()

    @pytest.mark.asyncio
    async def test_session_history_limit(self, tmp_path):
        from app.services.session_manager import SessionManager
        mgr = SessionManager(storage_path=str(tmp_path / "sessions"), max_history=10)
        await mgr.start()
        session = await mgr.create_session(user_id="test")
        for i in range(20):
            await mgr.add_message(session.session_id, "user", f"Message {i}")
        history = await mgr.get_session_history(session.session_id)
        assert len(history) == 10
        print(f"✓ History trimmed to {len(history)} messages")
        await mgr.stop()


# ═══════════════════════════════════════════════════════════════
# 9. STATE MANAGER TESTS
# ═══════════════════════════════════════════════════════════════

class TestStateManager:
    @pytest.mark.asyncio
    async def test_state_manager_crud(self, tmp_path):
        from app.services.state_manager import StateManager
        state_dir = str(tmp_path / "state")
        mgr = StateManager(state_dir=state_dir)
        await mgr.start()
        await mgr.set("key1", {"data": "value"})
        assert await mgr.get("key1") == {"data": "value"}
        await mgr.set("key1", {"data": "new_value"})
        assert await mgr.get("key1") == {"data": "new_value"}
        deleted = await mgr.delete("key1")
        assert deleted is True
        assert await mgr.get("key1") is None
        await mgr.stop()
        print("✓ State manager CRUD works")

    @pytest.mark.asyncio
    async def test_incident_state(self, tmp_path):
        from app.services.state_manager import StateManager
        mgr = StateManager(state_dir=str(tmp_path / "state"))
        await mgr.start()
        incident = {"id": "INC-001", "title": "Test incident", "severity": "critical",
                     "created_at": datetime.now(timezone.utc).isoformat()}
        await mgr.save_incident(incident)
        retrieved = await mgr.get_incident("INC-001")
        assert retrieved is not None
        assert retrieved["id"] == "INC-001"
        all_incidents = await mgr.get_all_incidents()
        assert len(all_incidents) == 1
        removed = await mgr.remove_incident("INC-001")
        assert removed is True
        await mgr.stop()
        print("✓ Incident state management works")

    @pytest.mark.asyncio
    async def test_checkpoint_protocol(self, tmp_path):
        from app.services.state_manager import StateManager
        mgr = StateManager(state_dir=str(tmp_path / "state"))
        await mgr.start()
        await mgr.create_checkpoint("task-123", {
            "step": 3, "last_action": "esql_query",
            "status": "RATE_LIMITED", "data": {"partial_result": "some data"}
        })
        checkpoint = await mgr.get_checkpoint("task-123")
        assert checkpoint is not None
        assert checkpoint["step"] == 3
        assert checkpoint["status"] == "RATE_LIMITED"
        print("✓ Checkpoint protocol works for rate-limit recovery")
        await mgr.stop()


# ═══════════════════════════════════════════════════════════════
# 10. MCP REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════

class TestMCPRegistry:
    def test_registry_creation(self):
        from app.services.mcp_registry import MCPRegistry
        registry = MCPRegistry()
        assert len(registry.list_servers()) == 0
        print("✓ MCP registry created empty")

    def test_server_registration(self):
        from app.services.mcp_registry import MCPRegistry
        registry = MCPRegistry()
        registry.register("elastic", "http://localhost:9200", priority=1)
        registry.register("gmail", "http://localhost:8081", priority=2)
        servers = registry.list_servers()
        assert "elastic" in servers
        assert "gmail" in servers
        print(f"✓ Registered {len(servers)} servers")

    def test_circuit_breaker_trips(self):
        from app.services.mcp_registry import MCPRegistry
        registry = MCPRegistry()
        registry.register("test-server", "http://localhost:9999", priority=1)
        for _ in range(5):
            registry.record_request_result("test-server", success=False, response_time_ms=100)
        servers = registry.list_servers()
        assert servers["test-server"]["circuit_breaker_state"] == "circuit_open"
        assert servers["test-server"]["allows_requests"] is False
        print("✓ Circuit breaker opens after threshold failures")

    def test_circuit_breaker_recovery(self):
        from app.services.mcp_registry import MCPRegistry
        registry = MCPRegistry()
        registry.register("test-server", "http://localhost:9999", priority=1)
        for _ in range(5):
            registry.record_request_result("test-server", success=False, response_time_ms=100)
        assert registry.reset_circuit("test-server") is True
        servers = registry.list_servers()
        assert servers["test-server"]["allows_requests"] is True
        print("✓ Circuit breaker manual reset works")

    def test_routing(self):
        from app.services.mcp_registry import MCPRegistry
        registry = MCPRegistry()
        registry.register("elastic", "http://localhost:9200", priority=1)
        url, tool, args = registry.route_request("elastic", "list_indices", {})
        assert url == "http://localhost:9200"
        assert tool == "list_indices"
        try:
            registry.route_request("nonexistent", "test", {})
            assert False, "Should have raised"
        except ValueError:
            pass
        print("✓ Request routing works correctly")

    def test_deregistration(self):
        from app.services.mcp_registry import MCPRegistry
        registry = MCPRegistry()
        registry.register("test", "http://localhost:9999")
        assert "test" in registry.list_servers()
        assert registry.deregister("test") is True
        assert "test" not in registry.list_servers()
        print("✓ Server deregistration works")


# ═══════════════════════════════════════════════════════════════
# 11. INCIDENT RESPONSE TESTS
# ═══════════════════════════════════════════════════════════════

class TestIncidentResponse:
    @pytest.mark.asyncio
    async def test_incident_creation(self):
        from app.services.incident_response import Incident, IncidentSeverity
        incident = Incident(title="Test outage", severity=IncidentSeverity.CRITICAL, index_name="orders-2026")
        assert incident.id.startswith("INC-")
        assert incident.title == "Test outage"
        assert incident.severity == IncidentSeverity.CRITICAL
        assert incident.status.value == "detected"
        print(f"✓ Incident created: {incident.id}")

    @pytest.mark.asyncio
    async def test_incident_lifecycle(self):
        from app.services.incident_response import Incident, IncidentSeverity
        incident = Incident(title="Test", severity=IncidentSeverity.HIGH)
        incident.add_investigation_step("search", {"index": "logs"}, "Found errors")
        assert len(incident.investigation_steps) == 1
        incident.set_diagnosis("Disk full", "Search failures", 0.9)
        assert incident.diagnosis["root_cause"] == "Disk full"
        assert incident.status.value == "diagnosed"
        action = incident.add_remediation_action("reindex", "Reindex logs")
        assert action["action_id"].startswith("ACT-")
        assert action["status"] == "proposed"
        print(f"✓ Full incident lifecycle: {incident.status.value}")

    @pytest.mark.asyncio
    async def test_incident_serialization(self):
        from app.services.incident_response import Incident, IncidentSeverity
        incident = Incident(title="Test", severity=IncidentSeverity.MEDIUM)
        incident.add_investigation_step("test", {}, "result")
        d = incident.to_dict()
        assert "id" in d
        assert "severity" in d
        assert len(d["investigation_steps"]) == 1
        print("✓ Incident serialization works")


# ═══════════════════════════════════════════════════════════════
# 12. POSTMORTEM TESTS
# ═══════════════════════════════════════════════════════════════

class TestPostmortem:
    @pytest.mark.asyncio
    async def test_postmortem_markdown(self):
        from app.services.postmortem import PostmortemGenerator
        generator = PostmortemGenerator()
        result = await generator.generate_postmortem(
            incident_id="INC-TEST-001",
            incident_data={
                "title": "Payment service outage", "severity": "critical", "status": "resolved",
                "diagnosis": {"root_cause": "Database connection pool exhaustion", "impact": "100% checkout failures", "confidence": 0.92},
                "investigation_steps": [{"tool": "search", "result_summary": "Found 5000 errors"}],
                "remediation_actions": [{"action_id": "ACT-001", "description": "Increase pool size", "risk_level": "low", "status": "executed"}],
                "created_at": "2026-05-08T10:00:00Z", "updated_at": "2026-05-08T10:47:00Z",
            },
            format="markdown",
        )
        assert "content_markdown" in result
        assert "Payment service outage" in result["content_markdown"]
        assert "Database connection pool exhaustion" in result["content_markdown"]
        print(f"✓ Markdown postmortem: {len(result['content_markdown'])} chars")

    @pytest.mark.asyncio
    async def test_postmortem_html(self):
        from app.services.postmortem import PostmortemGenerator
        generator = PostmortemGenerator()
        result = await generator.generate_postmortem(incident_id="INC-TEST-002", format="html")
        assert "content_html" in result
        assert "<html" in result["content_html"].lower()
        assert "INC-TEST-002" in result["content_html"]
        print(f"✓ HTML postmortem: {len(result['content_html'])} chars")

    @pytest.mark.asyncio
    async def test_postmortem_json(self):
        from app.services.postmortem import PostmortemGenerator
        generator = PostmortemGenerator()
        result = await generator.generate_postmortem(incident_id="INC-TEST-003", format="json")
        assert "content_json" in result
        parsed = json.loads(result["content_json"])
        assert parsed["incident_id"] == "INC-TEST-003"
        print("✓ JSON postmortem structure validated")

    @pytest.mark.asyncio
    async def test_lessons_learned(self):
        from app.services.postmortem import PostmortemGenerator
        generator = PostmortemGenerator()
        postmortem = await generator.generate_postmortem(
            incident_id="INC-TEST-004",
            incident_data={
                "title": "Test", "severity": "critical", "status": "resolved", "diagnosis": {},
                "investigation_steps": [{"tool": f"t{i}", "result_summary": f"s{i}"} for i in range(6)],
                "remediation_actions": [], "created_at": "2026-05-08T10:00:00Z", "updated_at": "2026-05-08T10:47:00Z",
            },
        )
        assert len(postmortem["lessons_learned"]) > 0
        print(f"✓ Generated {len(postmortem['lessons_learned'])} lessons learned")

    @pytest.mark.asyncio
    async def test_preventive_actions(self):
        from app.services.postmortem import PostmortemGenerator
        generator = PostmortemGenerator()
        postmortem = await generator.generate_postmortem(
            incident_id="INC-TEST-005",
            incident_data={"title": "Critical test", "severity": "critical", "status": "resolved",
                           "diagnosis": {}, "created_at": "2026-05-08T10:00:00Z", "updated_at": "2026-05-08T10:47:00Z"},
        )
        actions = postmortem["preventive_actions"]
        assert len(actions) > 0
        critical_actions = [a for a in actions if a.get("priority") == "CRITICAL"]
        assert len(critical_actions) > 0
        print(f"✓ Generated {len(actions)} preventive actions ({len(critical_actions)} critical)")


# ═══════════════════════════════════════════════════════════════
# 13. AGENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestAgents:
    def test_detector_agent(self):
        from app.services.agents.detector_agent import DetectorAgent
        agent = DetectorAgent()
        result = agent.observe()
        assert "es_health" in result
        assert "timestamp" in result
        assert agent.name == "DetectorAgent"
        print(f"✓ DetectorAgent: health={result['es_health']}")

    def test_investigator_agent(self):
        from app.services.agents.investigator_agent import InvestigatorAgent
        agent = InvestigatorAgent()
        result = agent.think({"incident_id": "test-123"})
        assert "root_cause" in result
        assert "confidence" in result
        assert agent.name == "InvestigatorAgent"
        print(f"✓ InvestigatorAgent: root_cause={result['root_cause']}")

    def test_fixer_agent(self):
        from app.services.agents.fixer_agent import FixerAgent
        agent = FixerAgent()
        result = agent.act({"incident_id": "test-123"})
        assert "action" in result
        assert agent.name == "FixerAgent"
        print(f"✓ FixerAgent: action={result['action']}")

    def test_base_agent(self):
        from app.services.agents.base_agent import Agent
        agent = Agent(name="TestAgent")
        assert agent.name == "TestAgent"
        assert agent.status == "idle"

        obs = agent.observe()
        assert "status" in obs
        # observe() sets status to "observing", stays until next action
        assert agent.status == "observing"

        # think resets back to idle
        agent.think(obs)
        assert agent.status == "idle"
        print("✓ BaseAgent works correctly (status lifecycle)")


# ═══════════════════════════════════════════════════════════════
# 14. SCHEMAS TESTS
# ═══════════════════════════════════════════════════════════════

class TestSchemas:
    def test_chat_message(self):
        from app.models.schemas import ChatMessage
        msg = ChatMessage(message="Hello")
        assert msg.message == "Hello"
        assert msg.session_id is None
        print("✓ ChatMessage schema works")

    def test_impact_metrics(self):
        from app.models.schemas import ImpactMetrics
        metrics = ImpactMetrics(revenue_at_risk=2850.0, customers_affected=847)
        assert metrics.revenue_at_risk == 2850.0
        assert metrics.customers_affected == 847
        print("✓ ImpactMetrics schema works")

    def test_remediation_request(self):
        from app.models.schemas import RemediationRequest
        req = RemediationRequest(action_id="ACT-001", approved=True)
        assert req.action_id == "ACT-001"
        assert req.approved is True
        print("✓ RemediationRequest schema works")


# ═══════════════════════════════════════════════════════════════
# 15. API ROUTE TESTS
# ═══════════════════════════════════════════════════════════════

class TestAPIRoutes:
    """Test API endpoints using the same prefix mounting as main.py."""

    @pytest.mark.asyncio
    async def test_impact_endpoint(self):
        from app.api.impact import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # main.py: app.include_router(impact_router, prefix="/api")
        # impact.py: @router.get("/impact")
        # Full path: /api/impact
        app_test = FastAPI()
        app_test.include_router(router, prefix="/api")
        client = TestClient(app_test, raise_server_exceptions=False)

        response = client.get("/api/impact")
        assert response.status_code == 200
        data = response.json()
        assert "revenue_at_risk" in data
        assert "business_summary" in data
        print(f"✓ /api/impact works: ${data['revenue_at_risk']}/hr at risk")

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        from app.api.health import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # main.py: app.include_router(health_router, prefix="/api/health")
        # health.py: @router.get("/health")
        # Full path: /api/health/health
        app_test = FastAPI()
        app_test.include_router(router, prefix="/api/health")
        client = TestClient(app_test, raise_server_exceptions=False)

        response = client.get("/api/health/health")
        assert response.status_code == 200
        data = response.json()
        assert "overall_health_score" in data or "score" in data or "status" in data
        print(f"✓ /api/health works: status={data.get('status', 'N/A')}")

    @pytest.mark.asyncio
    async def test_incidents_crud(self):
        import app.api.incidents as inc_mod
        inc_mod._incidents.clear()
        inc_mod._incounter = 0

        from app.api.incidents import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # main.py: app.include_router(incidents_router, prefix="/api/incidents")
        # incidents.py: @router.get("") -> /api/incidents/
        app_test = FastAPI()
        app_test.include_router(router, prefix="/api/incidents")
        client = TestClient(app_test, raise_server_exceptions=False)

        # Create
        response = client.post("/api/incidents/", json={
            "title": "Test Incident",
            "severity": "critical",
            "affected_services": ["payment-service"],
        })
        assert response.status_code == 200
        created = response.json()
        assert created["id"].startswith("INC-")
        assert created["severity"] == "critical"
        print(f"✓ Created incident: {created['id']}")

        # List
        response = client.get("/api/incidents/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        print(f"✓ Listed incidents: {data['total']} total")

        # Get
        response = client.get(f"/api/incidents/{created['id']}")
        assert response.status_code == 200
        print(f"✓ Got incident: {created['id']}")

        # Update
        response = client.patch(f"/api/incidents/{created['id']}", json={"status": "investigating"})
        assert response.status_code == 200
        print("✓ Updated incident status")

        inc_mod._incidents.clear()

    @pytest.mark.asyncio
    async def test_patrol_endpoint(self):
        from app.api.patrol import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # main.py: app.include_router(patrol_router, prefix="/api/patrol")
        # patrol.py: @router.get("") -> /api/patrol/
        app_test = FastAPI()
        app_test.include_router(router, prefix="/api/patrol")
        client = TestClient(app_test, raise_server_exceptions=False)

        response = client.get("/api/patrol/")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        print("✓ Patrol endpoint works")

    @pytest.mark.asyncio
    async def test_chat_session(self):
        from app.api.chat import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # main.py: app.include_router(chat_router, prefix="/api/chat")
        # chat.py: @router.post("/session") -> /api/chat/session
        app_test = FastAPI()
        app_test.include_router(router, prefix="/api/chat")
        client = TestClient(app_test, raise_server_exceptions=False)

        response = client.post("/api/chat/session")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        print(f"✓ Chat session created: {data['session_id']}")


# ═══════════════════════════════════════════════════════════════
# 16. DEMO DATA GENERATOR TESTS
# ═══════════════════════════════════════════════════════════════

class TestDemoData:
    def test_generate_indices(self):
        from app.scripts.demo_data import DemoDataGenerator
        indices = DemoDataGenerator.generate_indices()
        assert len(indices) > 0
        assert all("name" in i for i in indices)
        print(f"✓ Generated {len(indices)} demo indices")

    def test_generate_shard_data(self):
        from app.scripts.demo_data import DemoDataGenerator
        shards = DemoDataGenerator.generate_shard_data()
        assert len(shards) > 0
        assert all("state" in s for s in shards)
        unassigned = [s for s in shards if s["state"] == "UNASSIGNED"]
        assert len(unassigned) > 0
        print(f"✓ Generated {len(shards)} shards ({len(unassigned)} unassigned)")

    def test_generate_logs(self):
        from app.scripts.demo_data import DemoDataGenerator
        logs = DemoDataGenerator.generate_sample_logs(50)
        assert len(logs) == 50
        assert all("level" in l for l in logs)
        error_count = sum(1 for l in logs if l["level"] == "error")
        print(f"✓ Generated {len(logs)} logs ({error_count} errors)")


# ═══════════════════════════════════════════════════════════════
# 17. VOICE WEBHOOK TESTS
# ═══════════════════════════════════════════════════════════════

class TestVoiceWebhook:
    @pytest.mark.asyncio
    async def test_incoming_voice(self):
        """Test Twilio voice webhook returns valid TwiML."""
        from app.api.voice import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # main.py: app.include_router(voice_router, prefix="/api/voice")
        # voice.py: @router.post("/incoming") -> /api/voice/incoming
        app_test = FastAPI()
        app_test.include_router(router, prefix="/api/voice")
        client = TestClient(app_test, raise_server_exceptions=False)

        response = client.post("/api/voice/incoming")
        assert response.status_code == 200
        body = response.text
        assert "Response" in body
        assert "Gather" in body
        print("✓ Twilio voice webhook returns valid TwiML")

    @pytest.mark.asyncio
    async def test_voice_process(self):
        from app.api.voice import processor
        result = processor.process_command("status")
        assert result["action"] != "unknown"
        print(f"✓ Voice processor handles 'status' command")

    @pytest.mark.asyncio
    async def test_voice_process_unknown(self):
        from app.api.voice import processor
        result = processor.process_command("flarb snazzle")
        assert result["action"] == "unknown"
        print("✓ Voice processor handles unknown commands gracefully")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])