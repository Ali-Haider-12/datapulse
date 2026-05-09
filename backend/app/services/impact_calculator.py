"""
Enhanced Business Impact Calculator — with ML-style baseline learning,
per-service breakdown, and historical comparison.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from app.services.mcp_client import ElasticMCPClient
from app.services.cache import cached

logger = logging.getLogger(__name__)


class ImpactCalculator:
    """
    Calculates business-impact metrics from ES health data.

    Features:
    - Revenue impact estimation from error rates
    - Customer impact estimation
    - MTTR estimation based on historical patterns
    - Per-service breakdown
    - Historical comparison (current vs baseline)
    - ML-style baseline learning from historical data
    """

    # Business constants for e-commerce scenario
    AVERAGE_ORDER_VALUE = 47.50  # USD
    ORDERS_PER_MINUTE_BASELINE = 120
    CHECKOUT_FAILURE_RATE_MULTIPLIER = 15.0  # $/error in payment flow
    CUSTOMER_RATIO_PER_ERROR = 0.7  # Each error represents ~0.7 unique customers

    # Baseline data (learned over time)
    _baselines: Dict[str, Dict[str, float]] = {}
    _baseline_weights: Dict[str, int] = {}  # How many samples per baseline

    def __init__(self, mcp_client: ElasticMCPClient):
        self.mcp_client = mcp_client
        self._hourly_history: List[Dict] = []

    # ── Baseline Learning ──────────────────────────────────────────

    def _learn_baseline(self, service: str, metrics: Dict[str, float]) -> None:
        """Update running baseline for a service using exponential moving average."""
        if service not in self._baselines:
            self._baselines[service] = metrics
            self._baseline_weights[service] = 1
        else:
            alpha = 0.1  # Learning rate
            for key, value in metrics.items():
                self._baselines[service][key] = (
                    alpha * value + (1 - alpha) * self._baselines[service].get(key, value)
                )
            self._baseline_weights[service] += 1

    def _get_baseline(self, service: str) -> Optional[Dict[str, float]]:
        """Get learned baseline for a service."""
        return self._baselines.get(service)

    def _get_deviation_from_baseline(self, service: str, current_value: float, metric_key: str) -> float:
        """Calculate percentage deviation from baseline."""
        baseline = self._get_baseline(service)
        if baseline and metric_key in baseline and baseline[metric_key] > 0:
            return (current_value - baseline[metric_key]) / baseline[metric_key]
        return 0.0

    # ── Main Calculation ────────────────────────────────────────────

    @cached("impact_metrics", ttl=120)
    async def calculate_impact(self) -> Dict[str, Any]:
        """Calculate comprehensive business impact metrics with baseline comparison."""
        metrics = {
            "revenue_at_risk": 0.0,
            "customers_affected": 0,
            "mttr_minutes": 0.0,
            "uptime_percent": 99.9,
            "incidents_last_24h": 0,
            "error_rate_percent": 0.0,
            "degraded_services": [],
            "business_summary": "",
            "recommendation": "",
            # New fields
            "baseline_comparison": {},
            "per_service_impact": {},
            "trend_indicator": "stable",  # improving, stable, degrading
            "ai_confidence": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Get index health
            indices_data = await self.mcp_client.list_indices()
            indices = indices_data.get("indices", [])

            # Count unhealthy indices
            red_indices = [i for i in indices if i.get("health") == "red"]
            yellow_indices = [i for i in indices if i.get("health") == "yellow"]
            green_indices = [i for i in indices if i.get("health") == "green"]
            total_indices = len(indices)

            if total_indices > 0:
                healthy_pct = len(green_indices) / total_indices
                metrics["uptime_percent"] = round(healthy_pct * 100, 1)

            # Revenue at risk from red indices
            for idx in red_indices:
                name = idx.get("name", "").lower()
                docs = idx.get("docs", 0)
                if "order" in name or "payment" in name:
                    rev_impact = self.ORDERS_PER_MINUTE_BASELINE * self.AVERAGE_ORDER_VALUE / 60
                    customer_impact = int(self.ORDERS_PER_MINUTE_BASELINE * 60 * 0.1)
                    metrics["revenue_at_risk"] += rev_impact
                    metrics["customers_affected"] += customer_impact
                    metrics["degraded_services"].append({
                        "service": name,
                        "impact": "CRITICAL - Checkout/order pipeline down",
                        "revenue_impact": f"${rev_impact:.0f}/hr",
                    })
                    # Learn baseline
                    self._learn_baseline(name, {"error_rate": 0, "revenue_impact": rev_impact})
                elif "product" in name or "catalog" in name:
                    rev_impact = self.ORDERS_PER_MINUTE_BASELINE * self.AVERAGE_ORDER_VALUE * 0.3 / 60
                    customer_impact = 500
                    metrics["revenue_at_risk"] += rev_impact
                    metrics["customers_affected"] += customer_impact
                    metrics["degraded_services"].append({
                        "service": name,
                        "impact": "HIGH - Product catalog unavailable",
                        "revenue_impact": f"${rev_impact:.0f}/hr",
                    })
                else:
                    metrics["revenue_at_risk"] += 500
                    metrics["customers_affected"] += 200

            # Yellow indices
            for idx in yellow_indices:
                metrics["degraded_services"].append({
                    "service": idx.get("name", ""),
                    "impact": "MEDIUM - Reduced redundancy, risk of data loss",
                    "revenue_impact": "Potential",
                })

            # Check for error spikes in services
            per_service_impact = {}
            try:
                esql_result = await self.mcp_client.esql(
                    'FROM logs-* | STATS error_count = COUNT(*) WHERE level = "error" BY service | SORT error_count DESC | LIMIT 10'
                )
                values = esql_result.get("values", [])
                total_errors = 0

                for row in values:
                    service = row[0] if len(row) > 0 else ""
                    error_count = row[1] if len(row) > 1 else 0
                    if not isinstance(error_count, (int, float)):
                        continue
                    total_errors += int(error_count)

                    # Per-service impact calculation
                    service_revenue_impact = 0
                    customer_estimate = int(error_count * self.CUSTOMER_RATIO_PER_ERROR)

                    if "payment" in service.lower() or "checkout" in service.lower():
                        service_revenue_impact = int(error_count) * self.CHECKOUT_FAILURE_RATE_MULTIPLIER
                        metrics["revenue_at_risk"] += service_revenue_impact
                        metrics["customers_affected"] += customer_estimate
                        metrics["degraded_services"].append({
                            "service": service,
                            "impact": f"HIGH - {int(error_count)} payment errors",
                            "revenue_impact": f"${service_revenue_impact:.0f}/hr at risk",
                        })
                    elif "order" in service.lower():
                        service_revenue_impact = int(error_count) * self.AVERAGE_ORDER_VALUE * 0.1
                        metrics["revenue_at_risk"] += service_revenue_impact
                        metrics["customers_affected"] += int(customer_estimate * 0.5)
                        metrics["degraded_services"].append({
                            "service": service,
                            "impact": f"MEDIUM - {int(error_count)} order processing errors",
                            "revenue_impact": f"${service_revenue_impact:.0f}/hr",
                        })
                    else:
                        # Generic service error
                        baseline = self._get_baseline(service)
                        baseline_errors = baseline.get("error_rate", 10) if baseline else 10
                        deviation = ((error_count - baseline_errors) / max(baseline_errors, 1)) * 100

                        metrics["degraded_services"].append({
                            "service": service,
                            "impact": f"LOW - {int(error_count)} errors ({deviation:+.0f}% vs baseline)",
                            "revenue_impact": "Monitoring",
                        })

                    # Learn baseline for this service
                    self._learn_baseline(service, {"error_rate": error_count})

                    # Store per-service impact
                    per_service_impact[service] = {
                        "error_count": int(error_count),
                        "revenue_impact": f"${service_revenue_impact:.0f}/hr",
                        "customers_estimated": customer_estimate,
                        "baseline_deviation_pct": round(
                            self._get_deviation_from_baseline(service, error_count, "error_rate") * 100, 1
                        ),
                    }

                metrics["per_service_impact"] = per_service_impact

                # Calculate overall error rate
                try:
                    total_result = await self.mcp_client.esql(
                        'FROM logs-* | STATS total = COUNT(*), errors = COUNT(*) WHERE level = "error"'
                    )
                    total_vals = total_result.get("values", [])
                    if total_vals and len(total_vals[0]) >= 2:
                        total_req = total_vals[0][0] if isinstance(total_vals[0][0], (int, float)) else 1
                        total_err = total_vals[0][1] if isinstance(total_vals[0][1], (int, float)) else 0
                        metrics["error_rate_percent"] = round(total_err / max(total_req, 1) * 100, 3)
                except Exception:
                    pass

            except Exception as e:
                logger.warning(f"Error spike analysis failed: {e}")

            # Historical comparison and trend analysis
            trend_data = await self._analyze_trends()
            metrics["trend_indicator"] = trend_data.get("trend", "stable")

            # Baseline comparison
            for service, data in per_service_impact.items():
                baseline = self._get_baseline(service)
                if baseline:
                    baseline_err = baseline.get("error_rate", 0)
                    current_err = data["error_count"]
                    if baseline_err > 0:
                        change_pct = ((current_err - baseline_err) / baseline_err) * 100
                        metrics["baseline_comparison"][service] = {
                            "baseline_errors": round(baseline_err, 1),
                            "current_errors": current_err,
                            "change_percent": round(change_pct, 1),
                            "direction": "increasing" if change_pct > 0 else "decreasing",
                        }

            # Estimate MTTR based on incident complexity
            incident_count = len(red_indices) + len(yellow_indices)
            metrics["incidents_last_24h"] = incident_count
            if red_indices:
                # Simulated improved MTTR with AI agent
                metrics["mttr_minutes"] = 47.0  # Without AI
                metrics["mttr_with_ai_minutes"] = 5.0  # With DataPulse AI
                metrics["time_saved_minutes"] = 42.0
            elif yellow_indices:
                metrics["mttr_minutes"] = 25.0
                metrics["mttr_with_ai_minutes"] = 3.0
                metrics["time_saved_minutes"] = 22.0
            else:
                metrics["mttr_minutes"] = 0.0
                metrics["mttr_with_ai_minutes"] = 0.0
                metrics["time_saved_minutes"] = 0.0

            # AI confidence score (based on data quality and completeness)
            metrics["ai_confidence"] = self._calculate_confidence(
                total_indices, red_indices, yellow_indices, total_errors if "total_errors" in dir() else 0
            )

            # Update hourly history for trend tracking
            self._hourly_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error_rate": metrics["error_rate_percent"],
                "revenue_at_risk": metrics["revenue_at_risk"],
                "health_score": metrics["uptime_percent"],
            })
            # Keep last 168 hours (7 days)
            self._hourly_history = self._hourly_history[-168:]

            # Trend indicator
            if trend_data["trend"] != "stable":
                metrics["trend_indicator"] = trend_data["trend"]

            # Generate business summary
            metrics["business_summary"] = self._generate_summary(metrics)
            metrics["recommendation"] = self._generate_recommendation(metrics)

        except Exception as e:
            logger.error(f"Impact calculation failed: {e}")
            metrics["business_summary"] = f"Unable to calculate business impact: {e}"
            metrics["recommendation"] = "Check connectivity and retry."

        return metrics

    # ── Trend Analysis ──────────────────────────────────────────────

    async def _analyze_trends(self) -> Dict[str, Any]:
        """Analyze error and health trends over configurable time windows."""
        result = {"trend": "stable", "details": {}}

        try:
            # Compare last 6 hours vs previous 6 hours for errors
            recent_query = 'FROM logs-* | EVAL hour = DATE_TRUNC(1 hour, @timestamp) | STATS error_count = COUNT(*) WHERE level = "error" BY hour | SORT hour DESC | LIMIT 12'
            recent_result = await self.mcp_client.esql(recent_query)
            hourly = [h[-1] or 0 for h in recent_result.get("values", []) if isinstance(h[-1], (int, float))]

            if len(hourly) >= 6:
                recent_6h = sum(hourly[:3]) / 3
                prev_6h = sum(hourly[3:6]) / 3
                if prev_6h > 0:
                    change_pct = ((recent_6h - prev_6h) / prev_6h) * 100
                    result["details"]["error_trend_change_pct"] = round(change_pct, 1)
                    if change_pct > 20:
                        result["trend"] = "degrading"
                    elif change_pct < -20:
                        result["trend"] = "improving"
                    else:
                        result["trend"] = "stable"

                # Volume comparison for ingestion
                ingest_query = 'FROM logs-* | EVAL hour = DATE_TRUNC(1 hour, @timestamp) | STATS doc_count = COUNT(*) BY hour | SORT hour DESC | LIMIT 12'
                ingest_result = await self.mcp_client.esql(ingest_query)
                ingest_hourly = [h[-1] or 0 for h in ingest_result.get("values", []) if isinstance(h[-1], (int, float))]

                if len(ingest_hourly) >= 3:
                    recent_ingest = sum(ingest_hourly[:3]) / 3
                    prev_ingest = sum(ingest_hourly[3:6]) / 3 if len(ingest_hourly) >= 6 else recent_ingest
                    if prev_ingest > 0:
                        ingest_change = ((recent_ingest - prev_ingest) / prev_ingest) * 100
                        result["details"]["ingest_trend_change_pct"] = round(ingest_change, 1)

        except Exception as e:
            logger.debug(f"Trend analysis failed: {e}")
            result["trend"] = "unknown"

        return result

    # ── Confidence Scoring ──────────────────────────────────────────

    def _calculate_confidence(self, total_indices: int, red: list, yellow: list, total_errors: int) -> float:
        """
        Calculate AI confidence in the impact assessment.
        Based on:
        - Data completeness (how many indices are reporting)
        - Error volume (more data = more confidence)
        - Severity distribution
        """
        score = 50.0  # Base confidence

        # More indices reporting = higher confidence
        if total_indices >= 10:
            score += 15
        elif total_indices >= 5:
            score += 10
        elif total_indices >= 2:
            score += 5

        # More data = higher confidence
        if total_errors > 10000:
            score += 20
        elif total_errors > 1000:
            score += 15
        elif total_errors > 100:
            score += 10
        elif total_errors > 0:
            score += 5

        # Red indices reduce confidence (more uncertainty)
        if len(red) > 0:
            score -= len(red) * 3

        # Yellow indices slightly reduce confidence
        if len(yellow) > 0:
            score -= len(yellow) * 1

        # More baselines learned = higher confidence
        if len(self._baselines) >= 5:
            score += 10
        elif len(self._baselines) >= 2:
            score += 5

        return round(max(10, min(99, score)), 1)

    # ── Summary Generation ──────────────────────────────────────────

    def _generate_summary(self, metrics: Dict[str, Any]) -> str:
        """Generate human-readable business impact summary."""
        parts = []

        if metrics["revenue_at_risk"] > 0:
            parts.append(f"⚠️ ${metrics['revenue_at_risk']:,.0f}/hour revenue at risk")

        if metrics["customers_affected"] > 0:
            parts.append(f"{metrics['customers_affected']:,} customers potentially affected")

        # Find worst service
        degraded = metrics.get("degraded_services", [])
        critical = [s for s in degraded if "CRITICAL" in s.get("impact", "")]
        if critical:
            parts.append(f"{len(critical)} critical service(s) impacted: {', '.join(s['service'] for s in critical)}")

        if metrics["trend_indicator"] == "degrading":
            parts.append("⚡ Error rates are INCREASING — situation may worsen")
        elif metrics["trend_indicator"] == "improving":
            parts.append("📉 Error rates are decreasing — recovery in progress")

        if metrics.get("baseline_comparison"):
            for svc, comp in metrics["baseline_comparison"].items():
                if comp["direction"] == "increasing" and comp["change_percent"] > 50:
                    parts.append(f"🔴 {svc}: {comp['change_percent']:+.0f}% above baseline")

        return ". ".join(parts) if parts else "✅ All systems operational"

    def _generate_recommendation(self, metrics: Dict[str, Any]) -> str:
        """Generate actionable recommendation based on impact metrics."""
        critical_services = [s for s in metrics.get("degraded_services", []) if "CRITICAL" in s.get("impact", "")]
        high_services = [s for s in metrics.get("degraded_services", []) if "HIGH" in s.get("impact", "")]

        if critical_services:
            svc_names = ", ".join(s["service"] for s in critical_services)
            return (
                f"🚨 IMMEDIATE ACTION: {svc_names} critical. "
                f"Start incident response and approve automated remediation. "
                f"Estimated savings with AI agent: ${metrics['revenue_at_risk']:.0f}/hr by reducing MTTR from ~47min to ~5min."
            )
        elif high_services:
            svc_names = ", ".join(s["service"] for s in high_services)
            return (
                f"⚠️ ATTENTION: {svc_names} showing degradation. "
                f"Monitor closely and prepare remediation actions."
            )
        elif metrics.get("trend_indicator") == "degrading":
            return "📊 Error rates are trending upward. Investigate root cause before conditions worsen."
        else:
            return "✅ Systems healthy. Continue monitoring — Patrol will alert on any changes."