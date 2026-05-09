"""
Base Agent — Foundation class for all DataPulse agents.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Agent:
    """Base class for all DataPulse agents."""

    name: str = "BaseAgent"
    description: str = "Base agent"

    def __init__(self, name: str = None):
        if name:
            self.name = name
        self.status = "idle"
        self._observations: List[Dict[str, Any]] = []
        self._last_action: Optional[Dict[str, Any]] = None

    def observe(self) -> Dict[str, Any]:
        """Observe the current state of the system."""
        self.status = "observing"
        observation = {
            "timestamp": _now_iso(),
            "agent": self.name,
            "status": self.status,
        }
        self._observations.append(observation)
        # Keep status as "observing" until next action
        return observation

    def think(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """Process an observation and generate a response."""
        self.status = "thinking"
        response = {
            "timestamp": _now_iso(),
            "agent": self.name,
            "observation_summary": str(observation),
            "thoughts": f"Processing observation from {observation}",
        }
        self._last_action = response
        self.status = "idle"
        return response

    def act(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action based on a plan."""
        self.status = "acting"
        action = {
            "timestamp": _now_iso(),
            "agent": self.name,
            "action": "execute",
            "plan_summary": str(plan),
            "status": "completed",
        }
        self._last_action = action
        self.status = "idle"
        return action

    def get_state(self) -> Dict[str, Any]:
        """Get the current state of this agent."""
        return {
            "name": self.name,
            "status": self.status,
            "last_action": self._last_action if self._last_action else "none",
            "id": id(self),
        }

    def reset(self) -> None:
        """Reset agent state."""
        self.status = "idle"
        self._observations = []
        self._last_action = None