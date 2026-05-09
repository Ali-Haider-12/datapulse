"""
AI-Powered Health Analyzer — Enhanced with predictive alerting, trend analysis,
and Gemini-powered anomaly detection.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from app.services.mcp_client import ElasticMCPClient
from app.services.llm_provider import LLMProvider
from app.services.cache import cached

logger = logging.getLogger(__name__)


class HealthAnalyzer:
    """Analyzes Elasticsearch data health with AI-powered insights and predictive alerting."""

    # Thresholds
    MAPPING_EXPLOSION_THRESHOLD = 100
    DYNAMIC_FIELD_THRESHOLD = 50
    INGESTION_DROP_THRESHOLD = 0.5  # 50% drop triggers alert
    ERROR_RATE_THRESHOLD = 1.0  # 1% error rate is concerning
    TREND_WINDOW_HOURS = 24

    def __init__(self, mcp_client: ElasticMCPClient, llm_provider: LLMProvider = None):
        self.mcp_client = mcp_client
        self.llm_provider = llm_provider
        self._trend_history: List[Dict] = []

    async def get_health_overview(self) -> Dict[str, Any]:
        """Get comprehensive health overview with AI-powered insights."""
        indices = await self.mcp_client.list_indices()
        shards = await self.mcp_client.get_shards()

        alerts = []
        unhealthy_indices = []

        for idx in indices.get("indices", []):
            health = idx.get("health", "unknown")
            if health == "red":
                alerts.append({
                    "severity": "critical",
                    "index": idx.get("name"),
                    "message": f"Index {idx.get('name')} is RED — some shards are unassigned",
                    "recommendation": "Check cluster health with `_cluster/health?pretty` and review node availability",
                })
                unhealthy_indices.append(idx)
            elif health == "yellow":
                alerts.append({
                    "severity": "warning",
                    "index": idx.get("name"),
                    "message": f"Index {idx.get('name')} is YELLOW — replica shards not allocated",
                    "recommendation": "Consider adding nodes or reducing replica count if single-node cluster",
                })

        # Check for unassigned shards
        unassigned = [s for s in shards.get("shards", []) if s.get("state") == "UNASSIGNED"]
        if unassigned:
            indices_affected = list(set(s.get("index", "?") for s in unassigned))
            alerts.append({
                "severity": "critical",
                "message": f"Found {len(unassigned)} unassigned shard(s)",
                "indices": indices_affected,
                "recommendation": "Check disk space, node availability, and cluster routing allocation settings",
            })

        # Get advanced AI analysis if available
        ai_analysis = await self._get_ai_health_analysis(indices, shards, alerts)

        return {
            "total_indices": len(indices.get("indices", [])),
            "unhealthy_indices": len(unhealthy_indices),
            "total_alerts": len(alerts),
            "health_score": max(0, 100 - len(alerts) * 10),
            "alerts": alerts,
            "ai_analysis": ai_analysis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _get_ai_health_analysis(
        self, indices: Dict, shards: Dict, alerts: List[Dict]
    ) -> Dict[str, Any]:
        """Use LLM to provide intelligent health analysis if available."""
        if not self.llm_provider:
            return {"status": "unavailable", "message": "No LLM provider configured"}

        try:
            # Build a summary prompt
            status_summary = {
                "total_indices": len(indices.get("indices", [])),
                "unassigned_shards": len([s for s in shards.get("shards", []) if s.get("state") == "UNASSIGNED"]),
                "yellow_indices": len([i for i in indices.get("indices", []) if i.get("health") == "yellow"]),
                "red_indices": len([i for i in indices.get("indices", []) if i.get("health") == "red"]),
                "total_docs": sum(i.get("docs", 0) for i in indices.get("indices", [])),
            }

            prompt = f"""You are DataPulse, an expert Elasticsearch operations engineer. Analyze this cluster health summary and provide:

1. Overall health assessment (1-2 sentences)
2. Top 3 priorities for the operations team
3. Any patterns or risks you notice
4. One proactive recommendation

Cluster Status:
- Total indices: {status_summary['total_indices']}
- Red indices: {status_summary['red_indices']}
- Yellow indices: {status_summary['yellow_indices']}
- Unassigned shards: {status_summary['unassigned_shards']}
- Total documents: {status_summary['total_docs']:,}

{'Active alerts: ' + str(len(alerts)) if alerts else 'No active alerts'}

Respond in a professional, concise tone with actionable insights."""

            response_text = ""
            async for chunk in self.llm_provider.chat(prompt):
                if chunk.get("type") == "text":
                    response_text += chunk.get("content", "")

            return {
                "status": "available",
                "analysis": response_text.strip() if response_text else "LLM returned empty response",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.warning(f"AI health analysis failed: {e}")
            return {"status": "error", "message": str(e)}

    async def detect_mapping_issues(self, index: str) -> List[Dict[str, Any]]:
        """Detect potential mapping explosion issues."""
        try:
            mappings = await self.mcp_client.get_mappings(index)
        except Exception as e:
            logger.error(f"Failed to get mappings for {index}: {e}")
            return [{"type": "error", "message": f"Could not retrieve mappings: {e}"}]

        issues = []
        mappings_data = mappings.get(index, mappings)
        props = mappings_data.get("mappings", {}).get("properties", {})
        field_count = len(props)
        dynamic_fields = [k for k, v in props.items() if v.get("dynamic") is not False]

        if field_count > self.MAPPING_EXPLOSION_THRESHOLD:
            issues.append({
                "type": "mapping_explosion_risk",
                "severity": "warning",
                "message": f"Index {index} has {field_count} fields — risk of mapping explosion",
                "recommendation": "Consider setting dynamic=false or dynamic=strict on this index",
            })

        if len(dynamic_fields) > self.DYNAMIC_FIELD_THRESHOLD:
            issues.append({
                "type": "dynamic_mapping",
                "severity": "info",
                "message": f"{len(dynamic_fields)} fields with dynamic mapping in {index}",
                "recommendation": "Review dynamic fields and set explicit types",
            })

        # Deep nesting check
        def check_nesting(props_dict, path="", depth=0):
            deep_fields = []
            for key, val in props_dict.items():
                current_path = f"{path}.{key}" if path else key
                if val.get("type") == "nested":
                    deep_fields.append(current_path)
                if "properties" in val and depth < 5:
                    deep_fields.extend(check_nesting(val["properties"], current_path, depth + 1))
            return deep_fields

        nested_fields = check_nesting(props)
        if len(nested_fields) > 10:
            issues.append({
                "type": "deep_nesting",
                "severity": "info",
                "message": f"Index {index} has {len(nested_fields)} nested fields",
                "recommendation": "Deep nesting can impact query performance. Consider flattening where possible.",
            })

        return issues

    async def analyze_ingestion_anomalies(self, index_pattern: str = "logs-*") -> List[Dict[str, Any]]:
        """Use ES|QL to detect ingestion rate anomalies with trend analysis."""
        query = f"FROM {index_pattern} | EVAL hour = DATE_TRUNC(1 hour, @timestamp) | STATS doc_count = COUNT(*) BY hour | SORT hour DESC | LIMIT 48"
        try:
            result = await self.mcp_client.esql(query)
            values = result.get("values", [])
            if len(values) >= 2:
                latest = values[0][-1] if values[0] else 0
                previous = values[1][-1] if values[1] else 0
                if isinstance(latest, (int, float)) and isinstance(previous, (int, float)) and previous > 0:
                    drop_ratio = latest / previous
                    if drop_ratio < self.INGESTION_DROP_THRESHOLD:
                        return [{
                            "type": "ingestion_drop",
                            "severity": "critical",
                            "message": f"Ingestion rate dropped {int((1 - drop_ratio) * 100)}% in the last hour",
                            "current_rate": latest,
                            "previous_rate": previous,
                            "drop_ratio": round(drop_ratio, 3),
                        }]
            return []
        except Exception:
            return []

    async def analyze_error_trends(self, index_pattern: str = "logs-*") -> Dict[str, Any]:
        """Analyze error trends over time with hourly breakdown."""
        try:
            # Get hourly error counts for last 24 hours
            query = f"FROM {index_pattern} | EVAL hour = DATE_TRUNC(1 hour, @timestamp) | STATS error_count = COUNT(*) WHERE level = 'error' BY hour | SORT hour ASC | LIMIT 24"
            result = await self.mcp_client.esql(query)
            hourly_errors = result.get("values", [])

            # Get top error services
            service_query = f"FROM {index_pattern} | STATS error_count = COUNT(*) WHERE level = 'error' BY service | SORT error_count DESC | LIMIT 5"
            service_result = await self.mcp_client.esql(service_query)
            top_services = service_result.get("values", [])

            # Get total request count
            total_query = f"FROM {index_pattern} | STATS total = COUNT(*), errors = COUNT(*) WHERE level = 'error'"
            total_result = await self.mcp_client.esql(total_query)
            total_vals = total_result.get("values", [])
            total_requests = total_vals[0][0] if total_vals and len(total_vals[0]) > 0 else 1
            total_errors = total_vals[0][1] if total_vals and len(total_vals[0]) > 1 else 0

            error_rate = round(total_errors / max(total_requests, 1) * 100, 3)

            # Trend: compare last 6 hours vs previous 6 hours
            trend_data = []
            if len(hourly_errors) >= 12:
                recent_6h = sum(h[-1] or 0 for h in hourly_errors[:6] if isinstance(h[-1], (int, float)))
                prev_6h = sum(h[-1] or 0 for h in hourly_errors[6:12] if isinstance(h[-1], (int, float)))
                trend_pct = round(((recent_6h - prev_6h) / max(prev_6h, 1)) * 100, 1)
                trend_data = {
                    "recent_6h_errors": recent_6h,
                    "previous_6h_errors": prev_6h,
                    "trend_percentage": trend_pct,
                    "trend_direction": "increasing" if trend_pct > 0 else "decreasing",
                }

            return {
                "hourly_errors": [
                    {"hour": h[0] if h else "unknown", "count": h[-1] if h and len(h) > 1 else 0}
                    for h in hourly_errors
                ],
                "top_error_services": [
                    {"service": row[0], "errors": row[1]}
                    for row in top_services
                    if isinstance(row[0], str)
                ],
                "total_requests": total_requests,
                "total_errors": total_errors,
                "error_rate_percent": error_rate,
                "trend": trend_data,
                "healthy": error_rate < self.ERROR_RATE_THRESHOLD,
            }
        except Exception as e:
            logger.error(f"Error trend analysis failed: {e}")
            return {"error": str(e), "healthy": False}

    async def predict_future_issues(self, index_pattern: str = "logs-*") -> List[Dict[str, Any]]:
        """
        Predict potential future issues based on current trends.
        Uses simple heuristic analysis — could be enhanced with ML.
        """
        predictions = []

        # Check for gradually increasing error rates
        try:
            query = f"FROM {index_pattern} | EVAL hour = DATE_TRUNC(1 hour, @timestamp) | STATS error_count = COUNT(*) WHERE level = 'error' BY hour | SORT hour ASC | LIMIT 24"
            result = await self.mcp_client.esql(query)
            hourly = [h[-1] or 0 for h in result.get("values", []) if isinstance(h[-1], (int, float))]

            if len(hourly) >= 6:
                # Simple linear trend detection
                recent_avg = sum(hourly[:3]) / 3
                older_avg = sum(hourly[3:6]) / 3
                if older_avg > 0 and recent_avg / older_avg > 1.5:
                    predictions.append({
                        "type": "error_rate_escalation",
                        "severity": "warning",
                        "message": "Error rates are increasing steadily — potential service degradation if trend continues",
                        "prediction_horizon": "next 2-4 hours",
                        "confidence": "medium",
                    })

                # Check for gradual disk/memory pressure (indexing rate increase)
                index_query = f"FROM {index_pattern} | EVAL hour = DATE_TRUNC(1 hour, @timestamp) | STATS doc_count = COUNT(*) BY hour | SORT hour ASC | LIMIT 12"
                index_result = await self.mcp_client.esql(index_query)
                index_hourly = [h[-1] or 0 for h in index_result.get("values", []) if isinstance(h[-1], (int, float))]
                if len(index_hourly) >= 3:
                    recent_idx = sum(index_hourly[:3]) / 3
                    older_idx = sum(index_hourly[3:6]) / 3 if len(index_hourly) >= 6 else recent_idx
                    if older_idx > 0 and recent_idx / older_idx > 2.0:
                        predictions.append({
                            "type": "ingestion_surge",
                            "severity": "info",
                            "message": "Ingestion rate significantly increased — monitor for resource exhaustion",
                            "prediction_horizon": "next 6-12 hours",
                            "confidence": "medium",
                        })
        except Exception:
            pass

        return predictions

    async def comprehensive_health_report(self) -> Dict[str, Any]:
        """Generate a comprehensive health report combining all analyses."""
        overview = await self.get_health_overview()
        error_trends = await self.analyze_error_trends()
        predictions = await self.predict_future_issues()

        # Combine all alerts
        all_alerts = overview.get("alerts", [])
        if not error_trends.get("healthy", True):
            all_alerts.append({
                "severity": "warning" if error_trends.get("error_rate_percent", 0) < 5 else "critical",
                "message": f"Error rate is {error_trends.get('error_rate_percent', 0)}%",
                "source": "error_trends",
            })

        for pred in predictions:
            all_alerts.append({
                "severity": pred.get("severity", "info"),
                "message": pred.get("message", ""),
                "type": "prediction",
                "prediction_horizon": pred.get("prediction_horizon", ""),
            })

        # Overall health score
        health_score = overview.get("health_score", 100)
        if error_trends.get("error_rate_percent", 0) > 1:
            health_score = max(0, health_score - 20)
        for pred in predictions:
            if pred.get("severity") == "warning":
                health_score = max(0, health_score - 5)

        return {
            "overall_health_score": health_score,
            "status": "healthy" if health_score >= 70 else "degraded" if health_score >= 40 else "critical",
            "overview": overview,
            "error_trends": error_trends,
            "predictions": predictions,
            "all_alerts": all_alerts,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }