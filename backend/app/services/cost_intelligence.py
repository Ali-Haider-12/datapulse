"""Observability Cost Intelligence

Addresses HN pain point: "observability costs more than the thing being observed"
Tracks ES storage costs, indexing/query rates, and suggests optimizations.

Key insight from research: Companies spend 20-40% of infra budget on observability.
DataPulse helps identify cost waste in Elasticsearch deployments.
"""

from __future__ import annotations
import time
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


class CostSeverity(str, Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


@dataclass
class IndexCostProfile:
    index_name: str
    primary_size_gb: float
    replica_size_gb: float
    total_size_gb: float
    docs_count: int
    shards: int
    primary_shards: int
    replica_shards: int
    monthly_storage_cost_usd: float = 0.0
    indexing_rate_per_min: float = 0.0
    search_rate_per_min: float = 0.0
    cost_per_doc_cents: float = 0.0
    waste_score: float = 0.0  # 0-100, higher = more wasteful
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ClusterCostSummary:
    total_indices: int
    total_size_gb: float
    total_monthly_cost_usd: float
    total_docs: int
    total_shards: int
    over_sharded_indices: int
    oversized_indices: int
    idle_indices: int
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    top_cost_indices: list[IndexCostProfile] = field(default_factory=list)
    savings_opportunities_usd: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CostAlert:
    alert_id: str
    alert_type: str  # budget_exceeded, waste_detected, spike, anomaly
    severity: CostSeverity
    index_name: Optional[str]
    message: str
    current_value: float
    threshold_value: float
    savings_potential_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class CostBudget:
    monthly_budget_usd: float
    current_spend_usd: float
    forecast_end_of_month_usd: float
    days_remaining: int
    daily_burn_rate_usd: float
    budget_status: str = "healthy"  # healthy, warning, critical, exceeded


@dataclass
class CostOptimization:
    optimization_id: str
    index_name: str
    optimization_type: str  # reduce_replicas, merge_shards, delete_idle, force_merge, ilm_policy
    description: str
    estimated_savings_usd_per_month: float
    risk: str = "low"  # low, medium, high
    action: str = ""
    effort: str = "easy"  # easy, moderate, complex


# Cost constants (AWS Elasticsearch pricing approximation)
STORAGE_COST_PER_GB_MONTH = 0.122  # USD per GB per month (EBS gp3)
COMPUTE_COST_PER_SHARD_MONTH = 8.50  # Rough cost per shard in compute
REPLICA_MULTIPLIER = 1.0  # Each replica doubles storage cost


class CostIntelligenceService:
    """Track and optimize Elasticsearch observability costs."""

    def __init__(self, budget_monthly_usd: float = 500.0):
        self._indices: dict[str, IndexCostProfile] = {}
        self._alerts: list[CostAlert] = []
        self._budget = CostBudget(
            monthly_budget_usd=budget_monthly_usd,
            current_spend_usd=0.0,
            forecast_end_of_month_usd=0.0,
            days_remaining=30,
            daily_burn_rate_usd=0.0,
        )
        self._alert_counter = 0
        self._optimizations: list[CostOptimization] = []
        self._cost_history: list[dict] = []

    def add_index_profile(self, profile: IndexCostProfile):
        """Add or update an index cost profile."""
        # Calculate costs
        profile.monthly_storage_cost_usd = round(
            profile.total_size_gb * STORAGE_COST_PER_GB_MONTH, 2
        )
        profile.cost_per_doc_cents = round(
            (profile.monthly_storage_cost_usd / max(profile.docs_count, 1)) * 100, 4
        )
        # Calculate waste score
        profile.waste_score = self._calculate_waste_score(profile)
        # Generate recommendations
        profile.recommendations = self._generate_index_recommendations(profile)
        self._indices[profile.index_name] = profile

    def _calculate_waste_score(self, profile: IndexCostProfile) -> float:
        """Calculate waste score (0-100) based on various signals."""
        score = 0.0

        # Over-sharded: >1 shard per 50GB is wasteful
        ideal_shards = max(1, int(profile.primary_size_gb / 50))
        if profile.primary_shards > ideal_shards * 2:
            score += min(30, (profile.primary_shards / max(ideal_shards, 1)) * 10)

        # Too many replicas for small indices
        if profile.replica_shards > 0 and profile.total_size_gb < 1.0:
            score += 15  # Small indices rarely need replicas

        # High cost per doc
        if profile.cost_per_doc_cents > 0.1:
            score += 20

        # Idle index (no searches)
        if profile.search_rate_per_min == 0 and profile.indexing_rate_per_min == 0:
            score += 25

        # Zero docs but non-zero size (deleted docs not merged)
        if profile.docs_count == 0 and profile.total_size_gb > 0.01:
            score += 30

        return min(100.0, round(score, 1))

    def _generate_index_recommendations(self, profile: IndexCostProfile) -> list[str]:
        """Generate cost optimization recommendations for an index."""
        recs = []

        # Over-sharded
        ideal_shards = max(1, int(profile.primary_size_gb / 50))
        if profile.primary_shards > ideal_shards * 2:
            savings = round((profile.primary_shards - ideal_shards) * COMPUTE_COST_PER_SHARD_MONTH, 2)
            recs.append(f"Reduce primary shards from {profile.primary_shards} to {ideal_shards} (save ~${savings}/mo)")

        # Unnecessary replicas for small indices
        if profile.replica_shards > 0 and profile.total_size_gb < 1.0 and profile.search_rate_per_min < 10:
            savings = round(profile.replica_size_gb * STORAGE_COST_PER_GB_MONTH, 2)
            recs.append(f"Remove replicas for small idle index (save ~${savings}/mo)")

        # Idle index
        if profile.search_rate_per_min == 0 and profile.indexing_rate_per_min == 0:
            recs.append("Index is idle — consider deleting or archiving to cold storage")

        # High cost per doc (possible mapping explosion)
        if profile.cost_per_doc_cents > 0.1:
            recs.append("High cost per document — check for mapping explosion or oversized fields")

        # Force merge for read-only indices
        if profile.indexing_rate_per_min == 0 and profile.search_rate_per_min > 0:
            recs.append("Read-only index — run force merge to reduce segment count and storage")

        return recs

    def get_cluster_summary(self) -> ClusterCostSummary:
        """Get overall cluster cost summary with optimization recommendations."""
        indices = list(self._indices.values())
        if not indices:
            return ClusterCostSummary(
                total_indices=0, total_size_gb=0, total_monthly_cost_usd=0,
                total_docs=0, total_shards=0, over_sharded_indices=0,
                oversized_indices=0, idle_indices=0,
            )

        total_size = sum(i.total_size_gb for i in indices)
        total_cost = sum(i.monthly_storage_cost_usd for i in indices)
        total_docs = sum(i.docs_count for i in indices)
        total_shards = sum(i.shards for i in indices)

        over_sharded = [i for i in indices if i.waste_score >= 30 and i.primary_shards > max(1, int(i.primary_size_gb / 50)) * 2]
        oversized = [i for i in indices if i.total_size_gb > 100]
        idle = [i for i in indices if i.search_rate_per_min == 0 and i.indexing_rate_per_min == 0]

        # Top cost indices
        top_cost = sorted(indices, key=lambda i: i.monthly_storage_cost_usd, reverse=True)[:5]

        # Calculate savings
        all_optimizations = self.get_optimizations()
        total_savings = sum(o.estimated_savings_usd_per_month for o in all_optimizations)

        # Cost breakdown
        breakdown = {
            "storage_usd": round(total_cost, 2),
            "compute_shards_usd": round(total_shards * COMPUTE_COST_PER_SHARD_MONTH, 2),
            "idle_waste_usd": round(sum(i.monthly_storage_cost_usd for i in idle), 2),
        }

        # Generate cluster-wide recommendations
        cluster_recs = []
        if idle:
            cluster_recs.append(f"Delete or archive {len(idle)} idle indices to save ~${breakdown['idle_waste_usd']}/mo")
        if over_sharded:
            cluster_recs.append(f"Reduce shard count on {len(over_sharded)} over-sharded indices")
        if total_cost > self._budget.monthly_budget_usd * 0.8:
            cluster_recs.append(f"Approaching budget limit ({total_cost:.0f}/{self._budget.monthly_budget_usd:.0f} USD)")
        if not any(i.replica_shards == 0 for i in indices):
            cluster_recs.append("Consider reducing replicas on non-critical indices")

        return ClusterCostSummary(
            total_indices=len(indices),
            total_size_gb=round(total_size, 2),
            total_monthly_cost_usd=round(total_cost, 2),
            total_docs=total_docs,
            total_shards=total_shards,
            over_sharded_indices=len(over_sharded),
            oversized_indices=len(oversized),
            idle_indices=len(idle),
            cost_breakdown=breakdown,
            top_cost_indices=top_cost,
            savings_opportunities_usd=round(total_savings, 2),
            recommendations=cluster_recs,
        )

    def check_budget(self, current_day: int = 15, days_in_month: int = 30) -> CostBudget:
        """Check budget status and forecast end-of-month spend."""
        summary = self.get_cluster_summary()
        current_spend = summary.total_monthly_cost_usd

        if current_day > 0:
            daily_burn = current_spend / current_day
            forecast = daily_burn * days_in_month
        else:
            daily_burn = current_spend / 1
            forecast = current_spend

        days_remaining = days_in_month - current_day
        budget = self._budget.monthly_budget_usd

        if forecast > budget * 1.2:
            status = "exceeded"
        elif forecast > budget * 1.0:
            status = "critical"
        elif forecast > budget * 0.8:
            status = "warning"
        else:
            status = "healthy"

        self._budget = CostBudget(
            monthly_budget_usd=budget,
            current_spend_usd=round(current_spend, 2),
            forecast_end_of_month_usd=round(forecast, 2),
            days_remaining=days_remaining,
            daily_burn_rate_usd=round(daily_burn, 2),
            budget_status=status,
        )

        # Generate budget alerts
        if status in ("critical", "exceeded"):
            self._alert_counter += 1
            self._alerts.append(CostAlert(
                alert_id=f"CA-{self._alert_counter:04d}",
                alert_type="budget_exceeded" if status == "exceeded" else "budget_warning",
                severity=CostSeverity.critical if status == "exceeded" else CostSeverity.high,
                index_name=None,
                message=f"Budget {status}: forecast ${forecast:.0f} vs budget ${budget:.0f}",
                current_value=forecast,
                threshold_value=budget,
                savings_potential_usd=round(forecast - budget, 2),
            ))

        return self._budget

    def get_optimizations(self) -> list[CostOptimization]:
        """Get all cost optimization opportunities."""
        optimizations = []
        opt_counter = 0

        for profile in self._indices.values():
            # Over-sharded
            ideal_shards = max(1, int(profile.primary_size_gb / 50))
            if profile.primary_shards > ideal_shards * 2:
                opt_counter += 1
                savings = round((profile.primary_shards - ideal_shards) * COMPUTE_COST_PER_SHARD_MONTH, 2)
                optimizations.append(CostOptimization(
                    optimization_id=f"OPT-{opt_counter:04d}",
                    index_name=profile.index_name,
                    optimization_type="merge_shards",
                    description=f"Reduce shards from {profile.primary_shards} to {ideal_shards}",
                    estimated_savings_usd_per_month=savings,
                    risk="medium",
                    action=f"Reindex {profile.index_name} with {ideal_shards} primary shards",
                    effort="moderate",
                ))

            # Unnecessary replicas
            if profile.replica_shards > 0 and profile.total_size_gb < 1.0 and profile.search_rate_per_min < 10:
                opt_counter += 1
                savings = round(profile.replica_size_gb * STORAGE_COST_PER_GB_MONTH, 2)
                optimizations.append(CostOptimization(
                    optimization_id=f"OPT-{opt_counter:04d}",
                    index_name=profile.index_name,
                    optimization_type="reduce_replicas",
                    description=f"Remove replicas from small idle index",
                    estimated_savings_usd_per_month=savings,
                    risk="low",
                    action=f'PUT {profile.index_name}/_settings {{"index.number_of_replicas": 0}}',
                    effort="easy",
                ))

            # Idle index
            if profile.search_rate_per_min == 0 and profile.indexing_rate_per_min == 0:
                opt_counter += 1
                savings = round(profile.monthly_storage_cost_usd, 2)
                optimizations.append(CostOptimization(
                    optimization_id=f"OPT-{opt_counter:04d}",
                    index_name=profile.index_name,
                    optimization_type="delete_idle",
                    description=f"Delete idle index (no reads/writes for 30+ days)",
                    estimated_savings_usd_per_month=savings,
                    risk="low",
                    action=f"DELETE {profile.index_name}",
                    effort="easy",
                ))

        # Sort by savings potential
        optimizations.sort(key=lambda o: o.estimated_savings_usd_per_month, reverse=True)
        self._optimizations = optimizations
        return optimizations

    def get_alerts(self) -> list[CostAlert]:
        """Get all cost alerts."""
        return sorted(self._alerts, key=lambda a: a.timestamp, reverse=True)

    def seed_demo_data(self):
        """Load demo cost data for hackathon presentation."""
        demo_indices = [
            IndexCostProfile("logs-production-2026", 150.0, 150.0, 300.0, 5000000000, 120, 60, 60, indexing_rate_per_min=50000, search_rate_per_min=200),
            IndexCostProfile("orders-2026", 45.0, 45.0, 90.0, 200000000, 20, 10, 10, indexing_rate_per_min=5000, search_rate_per_min=1500),
            IndexCostProfile("metrics-apm-2026", 200.0, 200.0, 400.0, 10000000000, 200, 100, 100, indexing_rate_per_min=100000, search_rate_per_min=500),
            IndexCostProfile("user-events-dev", 5.0, 5.0, 10.0, 1000000, 10, 5, 5, indexing_rate_per_min=0, search_rate_per_min=0),
            IndexCostProfile("audit-logs-2025", 80.0, 80.0, 160.0, 3000000000, 40, 20, 20, indexing_rate_per_min=0, search_rate_per_min=5),
            IndexCostProfile("traces-temp", 2.0, 2.0, 4.0, 500000, 20, 10, 10, indexing_rate_per_min=0, search_rate_per_min=0),
            IndexCostProfile("payments-2026", 8.0, 8.0, 16.0, 50000000, 6, 3, 3, indexing_rate_per_min=2000, search_rate_per_min=800),
            IndexCostProfile("session-data-old", 30.0, 0.0, 30.0, 100000000, 5, 5, 0, indexing_rate_per_min=0, search_rate_per_min=0),
        ]
        for idx in demo_indices:
            self.add_index_profile(idx)
