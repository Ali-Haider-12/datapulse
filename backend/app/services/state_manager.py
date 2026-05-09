"""
State Manager — Persistent state for DataPulse with auto-recovery.

Saves incident state, patrol history, and war room data to disk.
Auto-recovers on restart.
"""

import asyncio
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


class StateManager:
    """
    Manages persistent state for DataPulse.

    Features:
    - Automatic state checkpointing
    - Auto-recovery on restart
    - Versioned state files for rollback
    - Atomic writes (write to temp, then rename)
    """

    def __init__(self, state_dir: str = "./state"):
        self.state_dir = Path(state_dir)
        self._state_file = self.state_dir / "datapulse_state.json"
        self._backup_dir = self.state_dir / "backups"
        self._lock = asyncio.Lock()
        self._in_memory: Dict[str, Any] = {}
        self._auto_save = True
        self._save_interval = 30  # seconds
        self._save_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Initialize state manager — create dirs, load state, start auto-save."""
        self._ensure_dirs()
        self._load_state()
        if self._auto_save:
            self._save_task = asyncio.create_task(self._auto_save_loop())
        logger.info(f"StateManager started — loaded {len(self._in_memory)} state entries")

    async def stop(self) -> None:
        """Stop state manager and save all state."""
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
        await self._save_state()
        logger.info("StateManager stopped — state saved")

    # ── State Operations ────────────────────────────────────────────

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value from state."""
        async with self._lock:
            return self._in_memory.get(key, default)

    async def set(self, key: str, value: Any, persist: bool = True) -> None:
        """Set a value in state."""
        async with self._lock:
            self._in_memory[key] = value
            if persist:
                await self._save_state()

    async def delete(self, key: str) -> bool:
        """Delete a key from state."""
        async with self._lock:
            if key in self._in_memory:
                del self._in_memory[key]
                await self._save_state()
                return True
            return False

    async def get_all(self) -> Dict[str, Any]:
        """Get all state."""
        async with self._lock:
            return self._in_memory.copy()

    async def exists(self, key: str) -> bool:
        """Check if a key exists in state."""
        async with self._lock:
            return key in self._in_memory

    # ── Incident State ───────────────────────────────────────────────

    async def save_incident(self, incident: Dict[str, Any]) -> None:
        """Save an incident to persistent state."""
        incidents = await self.get("incidents", {})
        incidents[incident["id"]] = {
            **incident,
            "updated_at": _now_iso(),
        }
        await self.set("incidents", incidents)
        logger.info(f"Saved incident {incident['id']}")

    async def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Get an incident from state."""
        incidents = await self.get("incidents", {})
        return incidents.get(incident_id)

    async def get_all_incidents(self) -> List[Dict[str, Any]]:
        """Get all incidents, sorted by creation time (newest first)."""
        incidents = await self.get("incidents", {})
        return sorted(
            incidents.values(),
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )

    async def remove_incident(self, incident_id: str) -> bool:
        """Remove an incident from state."""
        incidents = await self.get("incidents", {})
        if incident_id in incidents:
            del incidents[incident_id]
            await self.set("incidents", incidents)
            logger.info(f"Removed incident {incident_id}")
            return True
        return False

    # ── Patrol State ─────────────────────────────────────────────────

    async def save_patrol_state(self, patrol_data: Dict[str, Any]) -> None:
        """Save patrol state (last check, alerts, etc)."""
        patrol_data["last_run"] = _now_iso()
        await self.set("patrol_state", patrol_data)

    async def get_patrol_state(self) -> Optional[Dict[str, Any]]:
        """Get patrol state to resume after restart."""
        return await self.get("patrol_state")

    # ── War Room State ────────────────────────────────────────────────

    async def save_war_room(self, war_room_data: Dict[str, Any]) -> None:
        """Save war room state."""
        war_rooms = await self.get("war_rooms", {})
        war_rooms[war_room_data["incident_id"]] = war_room_data
        await self.set("war_rooms", war_rooms)

    async def get_war_room(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Get war room state for an incident."""
        war_rooms = await self.get("war_rooms", {})
        return war_rooms.get(incident_id)

    # ── Checkpoint Protocol ──────────────────────────────────────────

    async def create_checkpoint(self, task_id: str, progress: Dict[str, Any]) -> None:
        """
        Create a task checkpoint for rate-limit recovery.

        This is used by the hackathon champion skill pattern:
        - Subagents write progress after each sub-step
        - If rate-limited, they report RATE_LIMITED with last checkpoint
        - Orchestrator resumes from checkpoint, not from scratch
        """
        checkpoints = await self.get("checkpoints", {})
        checkpoints[task_id] = {
            **progress,
            "checkpoint_time": _now_iso(),
        }
        await self.set("checkpoints", checkpoints)

    async def get_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the last checkpoint for a task."""
        checkpoints = await self.get("checkpoints", {})
        return checkpoints.get(task_id)

    # ── Persistence ──────────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> None:
        """Load state from disk (with corruption recovery)."""
        if not self._state_file.exists():
            logger.info("No existing state file — starting fresh")
            return

        try:
            with open(self._state_file) as f:
                self._in_memory = json.load(f)
            logger.info(f"Loaded state with {len(self._in_memory)} entries")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"State file corrupted: {e}")
            self._recover_state()

    def _recover_state(self) -> None:
        """Attempt to recover from corrupted state file."""
        backup = self.state_dir / "state_backup.json"
        if backup.exists():
            try:
                with open(backup) as f:
                    self._in_memory = json.load(f)
                logger.info("Recovered state from backup")
                return
            except Exception:
                pass

        backups = sorted(self._backup_dir.glob("state_*.json"), reverse=True)
        for backup_file in backups:
            try:
                with open(backup_file) as f:
                    self._in_memory = json.load(f)
                logger.info(f"Recovered state from {backup_file.name}")
                return
            except Exception:
                continue

        self._in_memory = {}
        logger.warning("State recovery failed — starting with empty state")

    async def _save_state(self) -> None:
        """Save state to disk atomically."""
        try:
            if self._state_file.exists():
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                backup_file = self._backup_dir / f"state_{timestamp}.json"
                shutil.copy2(self._state_file, backup_file)

            temp_file = self._state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(self._in_memory, f, indent=2, default=str)
            temp_file.replace(self._state_file)

            self._cleanup_old_backups()

        except IOError as e:
            logger.error(f"Failed to save state: {e}")

    def _cleanup_old_backups(self, keep: int = 10) -> None:
        """Remove old backup files, keeping the most recent ones."""
        backups = sorted(self._backup_dir.glob("state_*.json"))
        for old_backup in backups[:-keep]:
            try:
                old_backup.unlink()
            except OSError:
                pass

    async def _auto_save_loop(self) -> None:
        """Periodically save state to disk."""
        try:
            while True:
                await asyncio.sleep(self._save_interval)
                if self._in_memory:
                    await self._save_state()
                    logger.debug("Auto-saved state")
        except asyncio.CancelledError:
            await self._save_state()