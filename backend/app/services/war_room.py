"""
Async War Room — Concurrent multi-agent collaboration for incident response.

Runs Detector, Investigator, and Fixer agents concurrently with shared context
passing and real-time progress streaming.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.agents.base_agent import Agent
from app.services.agents.detector_agent import DetectorAgent
from app.services.agents.investigator_agent import InvestigatorAgent
from app.services.agents.fixer_agent import FixerAgent

logger = logging.getLogger(__name__)


class AsyncWarRoom:
    """
    Async War Room — orchestrates 3 AI agents concurrently for incident response.

    Unlike the sync WarRoom, this version:
    - Runs agents concurrently where possible
    - Streams progress in real-time
    - Maintains shared context between agents
    - Supports cancellation and timeout
    """

    def __init__(self, incident_id: str, mcp_client=None):
        self.incident_id = incident_id
        self.agents: Dict[str, Agent] = {
            "detector": DetectorAgent(),
            "investigator": InvestigatorAgent(),
            "fixer": FixerAgent(),
        }
        self.mcp_client = mcp_client
        self.conversation_log: List[Dict[str, Any]] = []
        self.status = "initialized"
        self.start_time: Optional[datetime] = None
        self._shared_context: Dict[str, Any] = {}
        self._progress_callbacks: List[callable] = []

    def on_progress(self, callback):
        """Register a callback to receive progress updates in real-time."""
        self._progress_callbacks.append(callback)

    async def start(self, timeout_seconds: int = 120) -> Dict[str, Any]:
        """
        Start the war room with concurrent agent execution.

        Runs phases:
        1. Detection (Detector agent observes)
        2. Investigation (Investigator analyzes in parallel with additional detection)
        3. Remediation (Fixer proposes actions)
        """
        self.status = "active"
        self.start_time = datetime.utcnow()
        self._log("system", f"Async War Room started for incident {self.incident_id}")

        try:
            # Phase 1: Detection
            await self._phase_detection()

            if self.status == "cancelled":
                return self.get_result()

            # Phase 2: Investigation (can run sub-tasks concurrently)
            await self._phase_investigation()

            if self.status == "cancelled":
                return self.get_result()

            # Phase 3: Remediation
            await self._phase_remediation()

            self.status = "completed"
            self._log("system", "Async War Room completed successfully")

        except asyncio.TimeoutError:
            self.status = "timeout"
            self._log("system", "War Room timed out")
        except asyncio.CancelledError:
            self.status = "cancelled"
            self._log("system", "War Room was cancelled")
        except Exception as e:
            self.status = "error"
            self._log("system", f"War Room error: {e}")
            logger.error(f"War Room error: {e}", exc_info=True)

        return self.get_result()

    async def cancel(self):
        """Cancel the current war room operation."""
        self.status = "cancelling"
        # Cancel all running agents
        for agent in self.agents.values():
            if hasattr(agent, 'cancel'):
                await agent.cancel()
        self.status = "cancelled"
        self._log("system", "War Room cancelled by operator")

    async def _phase_detection(self):
        """Phase 1: Detector agent observes the incident."""
        self._log("system", "Phase 1: Detection started")
        detector = self.agents["detector"]

        # Run detection with timeout
        try:
            observation = await asyncio.wait_for(
                detector.observe(self.incident_id),
                timeout=30.0
            )
            self._shared_context["observation"] = observation
            self._log("detector", f"Observed: {json.dumps(observation, default=str)[:200]}")

            # Notify progress callbacks
            await self._notify_progress({
                "phase": "detection",
                "status": "complete",
                "observation": observation,
            })

        except asyncio.TimeoutError:
            self._log("detector", "Detection timed out — using cached data")
            self._shared_context["observation"] = {
                "error": "timeout",
                "es_health": "unknown",
            }

    async def _phase_investigation(self):
        """Phase 2: Investigator analyzes the observation with concurrent sub-tasks."""
        self._log("system", "Phase 2: Investigation started")
        investigator = self.agents["investigator"]
        observation = self._shared_context.get("observation", {})

        # Run multiple investigation tasks concurrently
        tasks = [
            self._investigate_shards(),
            self._investigate_mappings(),
            self._investigate_errors(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Consolidate investigation results
        investigation_data = {"error": "timeout" if isinstance(r, asyncio.TimeoutError) else r for r in results if not isinstance(r, Exception)}

        # Run AI analysis on gathered data
        try:
            analysis = await asyncio.wait_for(
                investigator.think(observation),
                timeout=60.0
            )
            self._shared_context["analysis"] = analysis
            self._shared_context["investigation_data"] = investigation_data
            self._log("investigator", f"Analysis: {json.dumps(analysis, default=str)[:200]}")

            await self._notify_progress({
                "phase": "investigation",
                "status": "complete",
                "analysis": analysis,
            })

        except asyncio.TimeoutError:
            self._log("investigator", "Investigation timed out")
            self._shared_context["analysis"] = {"root_cause": "timeout during analysis"}

    async def _investigate_shards(self) -> Dict:
        """Investigate shard allocation issues."""
        try:
            if self.mcp_client:
                shards = await asyncio.wait_for(
                    self.mcp_client.get_shards(),
                    timeout=15.0
                )
                unassigned = [s for s in shards.get("shards", []) if s.get("state") == "UNASSIGNED"]
                self._shared_context["shard_issues"] = len(unassigned)
                return {"unassigned_shards": len(unassigned), "total": len(shards.get("shards", []))}
        except Exception as e:
            return {"error": str(e)}
        return {"skipped": True}

    async def _investigate_mappings(self) -> Dict:
        """Investigate potential mapping issues."""
        try:
            if self.mcp_client:
                indices = await asyncio.wait_for(
                    self.mcp_client.list_indices(),
                    timeout=15.0
                )
                large_indices = [i for i in indices.get("indices", []) if i.get("docs", 0) > 100000]
                return {"large_indices": len(large_indices), "total": len(indices.get("indices", []))}
        except Exception as e:
            return {"error": str(e)}
        return {"skipped": True}

    async def _investigate_errors(self) -> Dict:
        """Investigate error patterns."""
        try:
            if self.mcp_client:
                result = await asyncio.wait_for(
                    self.mcp_client.esql(
                        'FROM logs-* | STATS error_count = COUNT(*) WHERE level = "error" BY service | SORT error_count DESC | LIMIT 5'
                    ),
                    timeout=15.0
                )
                return {"services_with_errors": len(result.get("values", []))}
        except Exception as e:
            return {"error": str(e)}
        return {"skipped": True}

    async def _phase_remediation(self):
        """Phase 3: Fixer proposes and executes remediation."""
        self._log("system", "Phase 3: Remediation started")
        fixer = self.agents["fixer"]
        analysis = self._shared_context.get("analysis", {})

        try:
            action = await asyncio.wait_for(
                fixer.act(analysis),
                timeout=30.0
            )
            self._shared_context["action"] = action
            self._log("fixer", f"Action: {json.dumps(action, default=str)[:200]}")

            await self._notify_progress({
                "phase": "remediation",
                "status": "complete",
                "action": action,
            })

        except asyncio.TimeoutError:
            self._log("fixer", "Remediation timed out")
            self._shared_context["action"] = {"action": "timeout", "status": "manual_intervention_required"}

    def get_result(self) -> Dict[str, Any]:
        """Get the final war room result."""
        return {
            "incident_id": self.incident_id,
            "status": self.status,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": datetime.utcnow().isoformat(),
            "agents": {name: agent.get_state() for name, agent in self.agents.items()},
            "shared_context": self._shared_context,
            "conversation_length": len(self.conversation_log),
            "timeline": self.conversation_log,
        }

    def _log(self, speaker: str, message: str) -> None:
        """Add entry to conversation log."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "speaker": speaker,
            "message": message,
        }
        self.conversation_log.append(entry)
        # Notify callbacks
        asyncio.create_task(self._notify_progress({
            "type": "log",
            "speaker": speaker,
            "message": message,
        }))

    async def _notify_progress(self, update: Dict[str, Any]) -> None:
        """Notify all registered progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(update)
                else:
                    callback(update)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")


# Keep the original sync WarRoom for backward compatibility
class WarRoom:
    """Legacy sync War Room — delegates to AsyncWarRoom internally."""

    def __init__(self, incident_id: str):
        self.incident_id = incident_id
        self._async_room = AsyncWarRoom(incident_id)
        self.conversation_log: List[Dict[str, Any]] = []
        self.status = "initialized"
        self.start_time: Optional[datetime] = None

    def start(self) -> None:
        """Start the war room synchronously."""
        self.status = "active"
        self.start_time = datetime.utcnow()
        self._async_room._log("system", f"War Room started for incident {self.incident_id}")

        detector = self._async_room.agents["detector"]
        observation = detector.observe()
        self._log("detector", f"Observed: {observation}")

        investigator = self._async_room.agents["investigator"]
        analysis = investigator.think(observation)
        self._log("investigator", f"Analysis: {analysis}")

        fixer = self._async_room.agents["fixer"]
        action = fixer.act(analysis)
        self._log("fixer", f"Action: {action}")

        self.status = "completed"
        self._log("system", "War Room completed")

    def get_status(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "status": self.status,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "agents": {name: agent.get_state() for name, agent in self._async_room.agents.items()},
            "conversation_length": len(self.conversation_log),
        }

    def get_conversation_log(self) -> List[Dict[str, Any]]:
        return self.conversation_log + self._async_room.conversation_log

    def get_result(self) -> Dict[str, Any]:
        """Get the final war room result."""
        return {
            "incident_id": self.incident_id,
            "status": self.status,
            "agents": {name: agent.get_state() for name, agent in self._async_room.agents.items()},
            "shared_context": self._async_room._shared_context,
        }

    def _log(self, speaker: str, message: str) -> None:
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "speaker": speaker,
            "message": message,
        }
        self.conversation_log.append(entry)