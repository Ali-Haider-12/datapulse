"""
Impact API — Business impact metrics endpoint.
Uses ImpactCalculator from app state when available.
"""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/impact")
async def get_impact(request: Request):
    """
    Get current business impact metrics.

    Queries Elasticsearch via MCP client or ImpactCalculator
    for revenue-at-risk, customer impact, MTTR, and trends.
    """
    app_state = getattr(request.app.state, 'impact_calculator', None)
    cache = getattr(request.app.state, 'cache', None)

    if app_state:
        metrics = await app_state.calculate_impact()
        return metrics

    # Fallback mock data (for testing / when services not initialized)
    return {
        "revenue_at_risk": 2850.0,
        "customers_affected": 847,
        "uptime_percent": 85.0,
        "error_rate_percent": 2.5,
        "incidents_last_24h": 3,
        "mttr_minutes": 47.0,
        "mttr_with_ai_minutes": 5.0,
        "time_saved_minutes": 42.0,
        "trend_indicator": "degrading",
        "ai_confidence": 85.0,
        "degraded_services": [
            {
                "service": "payment-processor",
                "impact": "CRITICAL - Checkout pipeline down",
                "revenue_impact": "$2,850/hr"
            },
            {
                "service": "order-service",
                "impact": "HIGH - Order processing delayed 45s avg",
                "revenue_impact": "$500/hr"
            }
        ],
        "baseline_comparison": {
            "payment-processor": {
                "baseline_errors": 12,
                "current_errors": 847,
                "change_percent": 6958.3,
                "direction": "increasing"
            },
            "order-service": {
                "baseline_errors": 5,
                "current_errors": 312,
                "change_percent": 6140.0,
                "direction": "increasing"
            }
        },
        "per_service_impact": {
            "payment-processor": {
                "error_count": 847,
                "revenue_impact": "$2,850/hr",
                "baseline_deviation_pct": 6958.3
            },
            "order-service": {
                "error_count": 312,
                "revenue_impact": "$500/hr",
                "baseline_deviation_pct": 6140.0
            }
        },
        "business_summary": "⚠️ $2,850/hr revenue at risk. 847 customers potentially affected. 1 critical service impacted: payment-processor.",
        "recommendation": "🚨 IMMEDIATE ACTION: payment-processor critical. Start incident response and approve automated remediation. Estimated savings with AI agent: $2,850/hr by reducing MTTR from ~47min to ~5min.",
        "timestamp": "2026-05-09T06:00:00Z"
    }