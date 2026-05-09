"""Tests for Cross-Incident Memory Layer"""

import pytest
import os
import tempfile
from app.services.incident_memory import (
    IncidentMemoryService, MemoryIncident, SimilarIncident,
    IncidentPattern, ResolutionStats
)


@pytest.fixture
def service():
    """Create a memory service with a temp directory for isolation."""
    tmpdir = tempfile.mkdtemp()
    svc = IncidentMemoryService(memory_dir=tmpdir)
    return svc


@pytest.fixture
def service_with_data(service):
    """Memory service pre-loaded with demo incidents."""
    service.seed_demo_data()
    return service


class TestStoreIncident:
    def test_store_returns_memory_id(self, service):
        mid = service.store_incident({
            "title": "Test Incident",
            "severity": "high",
            "index_name": "orders-2026",
            "root_cause": "shard_allocation_failure",
            "impact": "High impact",
            "remediation": "Reroute shards",
            "resolution_time_min": 15.0,
            "outcome": "resolved",
        })
        assert mid.startswith("MEM-")

    def test_store_increments_counter(self, service):
        mid1 = service.store_incident({"title": "First", "severity": "low", "root_cause": "test"})
        mid2 = service.store_incident({"title": "Second", "severity": "low", "root_cause": "test"})
        # Counter should increment
        num1 = int(mid1.split("-")[1])
        num2 = int(mid2.split("-")[1])
        assert num2 > num1

    def test_store_persists_to_disk(self, service):
        service.store_incident({"title": "Persisted", "severity": "high", "root_cause": "test"})
        assert os.path.exists(service._file)
        with open(service._file) as f:
            import json
            data = json.load(f)
        assert len(data["incidents"]) == 1

    def test_store_with_tags(self, service):
        mid = service.store_incident({
            "title": "Tagged Incident",
            "severity": "medium",
            "root_cause": "test",
            "tags": ["shard", "critical-index"],
        })
        incidents = service.get_recent()
        assert len(incidents) == 1
        assert "shard" in incidents[0].tags


class TestSearchSimilar:
    def test_exact_index_match(self, service_with_data):
        results = service_with_data.search_similar({
            "index_name": "orders-2026",
            "root_cause": "shard_allocation_failure",
        })
        assert len(results) >= 1
        assert results[0].similarity_score >= 0.5
        assert any("Same index" in r for result in results for r in result.match_reasons)

    def test_root_cause_match(self, service_with_data):
        results = service_with_data.search_similar({
            "root_cause": "replica_allocation_issue",
        })
        assert len(results) >= 1

    def test_no_match_returns_empty(self, service_with_data):
        results = service_with_data.search_similar({
            "index_name": "nonexistent-index-xyz",
            "root_cause": "completely_unknown_issue",
        })
        # Should return low or no matches
        high_matches = [r for r in results if r.similarity_score > 0.3]
        assert len(high_matches) == 0

    def test_similarity_score_bounded(self, service_with_data):
        results = service_with_data.search_similar({
            "index_name": "orders-2026",
            "root_cause": "shard_allocation_failure",
            "severity": "critical",
        })
        for r in results:
            assert 0 <= r.similarity_score <= 1.0

    def test_results_sorted_by_similarity(self, service_with_data):
        results = service_with_data.search_similar({
            "root_cause": "shard_allocation_failure",
        })
        if len(results) >= 2:
            assert results[0].similarity_score >= results[1].similarity_score


class TestPatterns:
    def test_patterns_detected(self, service_with_data):
        patterns = service_with_data.get_patterns()
        assert len(patterns) >= 1

    def test_patterns_sorted_by_frequency(self, service_with_data):
        patterns = service_with_data.get_patterns()
        if len(patterns) >= 2:
            assert patterns[0].frequency >= patterns[1].frequency

    def test_pattern_has_description(self, service_with_data):
        patterns = service_with_data.get_patterns()
        for p in patterns:
            assert p.description != ""
            assert p.pattern_id.startswith("PAT-")

    def test_empty_memory_no_patterns(self, service):
        patterns = service.get_patterns()
        assert len(patterns) == 0


class TestResolutionStats:
    def test_stats_with_data(self, service_with_data):
        stats = service_with_data.get_resolution_stats()
        assert stats.total_incidents > 0
        assert stats.avg_resolution_time > 0
        assert stats.resolution_rate > 0

    def test_stats_empty(self, service):
        stats = service.get_resolution_stats()
        assert stats.total_incidents == 0
        assert stats.resolution_rate == 0

    def test_top_root_causes(self, service_with_data):
        stats = service_with_data.get_resolution_stats()
        assert len(stats.top_root_causes) >= 1

    def test_mttr_by_severity(self, service_with_data):
        stats = service_with_data.get_resolution_stats()
        assert len(stats.mttr_by_severity) >= 1


class TestDemoData:
    def test_seed_creates_incidents(self, service):
        service.seed_demo_data()
        assert len(service._incidents) == 5
        recent = service.get_recent()
        assert len(recent) == 5

    def test_demo_data_searchable(self, service):
        service.seed_demo_data()
        results = service.search_similar({"index_name": "orders-2026"})
        assert len(results) >= 1
