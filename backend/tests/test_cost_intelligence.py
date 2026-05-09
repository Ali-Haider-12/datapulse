"""Tests for Observability Cost Intelligence service."""

import pytest
from app.services.cost_intelligence import (
    CostIntelligenceService, IndexCostProfile, ClusterCostSummary,
    CostAlert, CostBudget, CostOptimization, CostSeverity,
    STORAGE_COST_PER_GB_MONTH, COMPUTE_COST_PER_SHARD_MONTH
)


@pytest.fixture
def service():
    return CostIntelligenceService(budget_monthly_usd=500.0)


@pytest.fixture
def service_with_data(service):
    service.seed_demo_data()
    return service


class TestAddIndexProfile:
    def test_add_profile_calculates_cost(self, service):
        profile = IndexCostProfile("test-index", 10.0, 10.0, 20.0, 1000000, 10, 5, 5)
        service.add_index_profile(profile)
        assert profile.monthly_storage_cost_usd > 0
        assert profile.monthly_storage_cost_usd == round(20.0 * STORAGE_COST_PER_GB_MONTH, 2)

    def test_add_profile_calculates_waste(self, service):
        profile = IndexCostProfile("idle-index", 5.0, 5.0, 10.0, 0, 10, 5, 5)
        service.add_index_profile(profile)
        assert profile.waste_score >= 25  # Zero docs + idle

    def test_add_profile_generates_recommendations(self, service):
        profile = IndexCostProfile("small-idle", 0.5, 0.5, 1.0, 100, 10, 5, 5)
        service.add_index_profile(profile)
        assert len(profile.recommendations) >= 1

    def test_waste_score_bounded(self, service):
        for size, docs, shards in [(0.01, 0, 20), (100.0, 10000000, 10), (50.0, 5000, 100)]:
            profile = IndexCostProfile(f"test-{size}", size, size, size*2, docs, shards, shards//2, shards//2)
            service.add_index_profile(profile)
            assert 0 <= profile.waste_score <= 100


class TestClusterSummary:
    def test_summary_with_demo_data(self, service_with_data):
        summary = service_with_data.get_cluster_summary()
        assert summary.total_indices == 8
        assert summary.total_size_gb > 0
        assert summary.total_monthly_cost_usd > 0
        assert summary.total_docs > 0
        assert summary.idle_indices >= 1

    def test_empty_cluster(self, service):
        summary = service.get_cluster_summary()
        assert summary.total_indices == 0
        assert summary.total_monthly_cost_usd == 0

    def test_top_cost_indices(self, service_with_data):
        summary = service_with_data.get_cluster_summary()
        assert len(summary.top_cost_indices) <= 5
        # Sorted by cost descending
        costs = [i.monthly_storage_cost_usd for i in summary.top_cost_indices]
        assert costs == sorted(costs, reverse=True)

    def test_cost_breakdown(self, service_with_data):
        summary = service_with_data.get_cluster_summary()
        assert "storage_usd" in summary.cost_breakdown
        assert "compute_shards_usd" in summary.cost_breakdown
        assert "idle_waste_usd" in summary.cost_breakdown

    def test_savings_opportunities(self, service_with_data):
        summary = service_with_data.get_cluster_summary()
        assert summary.savings_opportunities_usd >= 0

    def test_recommendations(self, service_with_data):
        summary = service_with_data.get_cluster_summary()
        # Demo data has idle indices, should generate recommendations
        assert len(summary.recommendations) >= 1


class TestBudget:
    def test_budget_healthy(self, service_with_data):
        budget = service_with_data.check_budget(current_day=1, days_in_month=30)
        assert budget.budget_status in ("healthy", "warning", "critical", "exceeded")

    def test_budget_exceeded(self, service):
        service._budget.monthly_budget_usd = 0.01  # Tiny budget
        # Add expensive index
        profile = IndexCostProfile("expensive", 500.0, 500.0, 1000.0, 10000000, 40, 20, 20)
        service.add_index_profile(profile)
        budget = service.check_budget(current_day=15, days_in_month=30)
        assert budget.budget_status in ("critical", "exceeded")

    def test_budget_forecast(self, service_with_data):
        budget = service_with_data.check_budget(current_day=15, days_in_month=30)
        assert budget.forecast_end_of_month_usd > 0
        assert budget.daily_burn_rate_usd > 0

    def test_budget_alerts_generated(self, service):
        service._budget.monthly_budget_usd = 0.01
        profile = IndexCostProfile("expensive", 500.0, 500.0, 1000.0, 10000000, 40, 20, 20)
        service.add_index_profile(profile)
        service.check_budget(current_day=15, days_in_month=30)
        alerts = service.get_alerts()
        assert len(alerts) >= 1


class TestOptimizations:
    def test_optimizations_with_demo_data(self, service_with_data):
        opts = service_with_data.get_optimizations()
        assert len(opts) >= 1

    def test_optimizations_sorted_by_savings(self, service_with_data):
        opts = service_with_data.get_optimizations()
        if len(opts) >= 2:
            assert opts[0].estimated_savings_usd_per_month >= opts[1].estimated_savings_usd_per_month

    def test_optimization_fields(self, service_with_data):
        opts = service_with_data.get_optimizations()
        for opt in opts:
            assert opt.optimization_id.startswith("OPT-")
            assert opt.optimization_type in ("reduce_replicas", "merge_shards", "delete_idle", "force_merge", "ilm_policy")
            assert opt.risk in ("low", "medium", "high")
            assert opt.effort in ("easy", "moderate", "complex")

    def test_idle_index_optimization(self, service):
        profile = IndexCostProfile("idle-test", 10.0, 0.0, 10.0, 1000000, 5, 5, 0)
        service.add_index_profile(profile)
        opts = service.get_optimizations()
        idle_opts = [o for o in opts if o.optimization_type == "delete_idle"]
        assert len(idle_opts) >= 1

    def test_over_sharded_optimization(self, service):
        profile = IndexCostProfile("sharded-test", 5.0, 0.0, 5.0, 100000, 20, 20, 0)
        service.add_index_profile(profile)
        opts = service.get_optimizations()
        shard_opts = [o for o in opts if o.optimization_type == "merge_shards"]
        assert len(shard_opts) >= 1


class TestDemoData:
    def test_seed_loads_8_indices(self, service):
        service.seed_demo_data()
        assert len(service._indices) == 8
