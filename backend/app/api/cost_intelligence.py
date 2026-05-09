"""API router for Cost Intelligence service."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.cost_intelligence import CostIntelligenceService, IndexCostProfile, CostBudget

router = APIRouter()
service = CostIntelligenceService(budget_monthly_usd=500.0)
service.seed_demo_data()


class IndexProfileRequest(BaseModel):
    index_name: str
    primary_size_gb: float
    replica_size_gb: float
    total_size_gb: float
    docs_count: int
    shards: int
    primary_shards: int
    replica_shards: int
    indexing_rate_per_min: float = 0.0
    search_rate_per_min: float = 0.0


class BudgetRequest(BaseModel):
    monthly_budget_usd: float = 500.0
    current_day: int = 15
    days_in_month: int = 30


@router.get("/cost/summary")
async def get_cost_summary():
    """Get cluster cost summary with optimization recommendations."""
    return service.get_cluster_summary()


@router.post("/cost/index")
async def add_index_profile(req: IndexProfileRequest):
    """Add an index cost profile."""
    profile = IndexCostProfile(
        index_name=req.index_name,
        primary_size_gb=req.primary_size_gb,
        replica_size_gb=req.replica_size_gb,
        total_size_gb=req.total_size_gb,
        docs_count=req.docs_count,
        shards=req.shards,
        primary_shards=req.primary_shards,
        replica_shards=req.replica_shards,
        indexing_rate_per_min=req.indexing_rate_per_min,
        search_rate_per_min=req.search_rate_per_min,
    )
    service.add_index_profile(profile)
    return {"status": "ok", "index": req.index_name, "waste_score": profile.waste_score}


@router.get("/cost/optimizations")
async def get_optimizations():
    """Get cost optimization opportunities."""
    return service.get_optimizations()


@router.get("/cost/alerts")
async def get_cost_alerts():
    """Get cost alerts."""
    return service.get_alerts()


@router.post("/cost/budget")
async def check_budget(req: BudgetRequest):
    """Check budget status and forecast."""
    service._budget.monthly_budget_usd = req.monthly_budget_usd
    return service.check_budget(current_day=req.current_day, days_in_month=req.days_in_month)


@router.post("/cost/seed")
async def seed_demo():
    """Seed demo cost data."""
    service.seed_demo_data()
    return {"status": "ok", "indices": len(service._indices)}
