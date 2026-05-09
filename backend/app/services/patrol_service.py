"""Proactive patrol service for DataPulse.

Runs background health checks on a configurable interval.
Detects NEW issues by comparing against previous patrol state.
Pushes alerts to the frontend via the alerts store.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from app.services.mcp_client import ElasticMCPClient
from app.services.health_analyzer import HealthAnalyzer
from app.api.alerts import add_alert

logger = logging.getLogger(__name__)


class PatrolService:
    """Background patrol that monitors ES health and surfaces new issues."""

    def __init__(self, mcp_client: ElasticMCPClient, interval_seconds: int = 60):
        self.mcp_client = mcp_client
        self.health_analyzer = HealthAnalyzer(mcp_client)
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_state: Dict[str, Any] = {
            "alerts": [],
            "health_score": 100,
            "indices": {},
            "timestamp": None,
        }
        self._patrol_history: List[Dict[str, Any]] = []
        self._on_new_alerts: Optional[Callable] = None

    def set_alert_callback(self, callback: Callable):
        """Set callback for when new alerts are discovered."""
        self._on_new_alerts = callback

    async def run_patrol(self) -> Dict[str, Any]:
        """Execute a single patrol cycle."""
        patrol_result = {
            "timestamp": datetime.utcnow().isoformat(),
            "new_alerts": [],
            "resolved_alerts": [],
            "health_score": None,
            "issues_found": 0,
        }

        try:
            # Get current health
            health = await self.health_analyzer.get_health_overview()
            current_alerts = health.get("alerts", [])
            current_score = health.get("health_score", 100)

            # Compare with last state to find NEW alerts
            last_alert_messages = {
                a.get("message", "") for a in self._last_state.get("alerts", [])
            }
            new_alerts = []
            for alert in current_alerts:
                if alert.get("message", "") not in last_alert_messages:
                    new_alerts.append(alert)
                    # Push to the alerts store so the frontend can see it
                    add_alert({
                        "severity": alert.get("severity", "info"),
                        "index": alert.get("index"),
                        "message": alert.get("message", ""),
                        "source": "patrol",
                        "timestamp": patrol_result["timestamp"],
                    })

            # Find resolved alerts
            current_alert_messages = {
                a.get("message", "") for a in current_alerts
            }
            resolved = []
            for alert in self._last_state.get("alerts", []):
                if alert.get("message", "") not in current_alert_messages:
                    resolved.append(alert)

            # Get index details for change tracking
            try:
                indices_data = await self.mcp_client.list_indices()
                current_indices = {
                    idx.get("name"): idx for idx in indices_data.get("indices", [])
                }
            except Exception:
                current_indices = {}

            # Detect health score changes
            last_score = self._last_state.get("health_score", 100)
            score_change = current_score - last_score

            # Build patrol result
            patrol_result.update({
                "new_alerts": new_alerts,
                "resolved_alerts": resolved,
                "health_score": current_score,
                "issues_found": len(new_alerts),
                "score_change": score_change,
                "total_indices": health.get("total_indices", 0),
                "unhealthy_indices": health.get("unhealthy_indices", 0),
            })

            # Also check for ingestion anomalies and mapping issues
            for idx_name in current_indices:
                try:
                    # Check mapping issues for indices with many fields
                    mapping_issues = await self.health_analyzer.detect_mapping_issues(
                        idx_name
                    )
                    for issue in mapping_issues:
                        if issue.get("message", "") not in last_alert_messages:
                            new_alert = {
                                "severity": issue.get("severity", "info"),
                                "index": idx_name,
                                "message": issue.get("message", ""),
                                "recommendation": issue.get("recommendation", ""),
                                "source": "patrol",
                                "timestamp": patrol_result["timestamp"],
                            }
                            patrol_result["new_alerts"].append(new_alert)
                            add_alert(new_alert)
                except Exception:
                    pass

            # Try ingestion anomaly detection
            try:
                anomalies = await self.health_analyzer.analyze_ingestion_anomalies()
                for anomaly in anomalies:
                    if anomaly.get("message", "") not in last_alert_messages:
                        new_alert = {
                            "severity": anomaly.get("severity", "critical"),
                            "message": anomaly.get("message", ""),
                            "source": "patrol",
                            "timestamp": patrol_result["timestamp"],
                        }
                        patrol_result["new_alerts"].append(new_alert)
                        add_alert(new_alert)
            except Exception:
                pass

            patrol_result["issues_found"] = len(patrol_result["new_alerts"])

            # Update state
            self._last_state = {
                "alerts": current_alerts,
                "health_score": current_score,
                "indices": current_indices,
                "timestamp": patrol_result["timestamp"],
            }

            # Store in history (keep last 50)
            self._patrol_history.append(patrol_result)
            if len(self._patrol_history) > 50:
                self._patrol_history = self._patrol_history[-50:]

            # Notify callback
            if self._on_new_alerts and patrol_result["new_alerts"]:
                try:
                    await self._on_new_alerts(patrol_result["new_alerts"])
                except Exception as e:
                    logger.warning(f"Alert callback error: {e}")

            if patrol_result["issues_found"] > 0:
                logger.info(f"Patrol found {patrol_result['issues_found']} new issues")
            else:
                logger.debug("Patrol complete — no new issues")

        except Exception as e:
            logger.error(f"Patrol failed: {e}")
            patrol_result["error"] = str(e)

        return patrol_result

    async def start(self):
        """Start the patrol loop in the background."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._patrol_loop())
        logger.info(f"Patrol started (interval: {self.interval_seconds}s)")

    async def stop(self):
        """Stop the patrol loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Patrol stopped")

    async def _patrol_loop(self):
        """Background loop that runs patrol cycles."""
        while self._running:
            try:
                await self.run_patrol()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Patrol loop error: {e}")
            await asyncio.sleep(self.interval_seconds)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def patrol_history(self) -> List[Dict[str, Any]]:
        return self._patrol_history

    @property
    def last_patrol(self) -> Optional[Dict[str, Any]]:
        return self._patrol_history[-1] if self._patrol_history else None
