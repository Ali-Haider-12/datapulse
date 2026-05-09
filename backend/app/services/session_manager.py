"""
Session Manager — Persistent chat sessions with auto-cleanup.

Stores conversation history per session with configurable TTL.
Supports session persistence across restarts via JSON file.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class Session:
    """Represents a single chat session with full conversation history."""

    def __init__(self, session_id: str, metadata: Dict[str, Any] = None):
        self.session_id = session_id
        self.metadata = metadata or {}
        self.messages: List[Dict[str, Any]] = []
        self.created_at = datetime.now(timezone.utc)
        self.last_active = datetime.now(timezone.utc)
        self.state: Dict[str, Any] = {}  # Arbitrary session state

    def add_message(self, role: str, content: str, **kwargs) -> None:
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self.messages.append(msg)
        self.last_active = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "metadata": self.metadata,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        session = cls(data["session_id"], data.get("metadata", {}))
        session.messages = data.get("messages", [])
        session.created_at = datetime.fromisoformat(data["created_at"])
        session.last_active = datetime.fromisoformat(data["last_active"])
        session.state = data.get("state", {})
        return session


class SessionManager:
    """
    Manages chat sessions with persistence, TTL-based cleanup, and history limits.
    """

    def __init__(self, storage_path: str = None, max_history: int = 100):
        self.storage_path = Path(storage_path) if storage_path else Path(
            os.environ.get("SESSIONS_DIR", "/tmp/datapulse_sessions")
        )
        self.max_history = max_history
        self.sessions: Dict[str, Session] = {}
        self._cleanup_task = None

    async def start(self) -> None:
        """Start the session manager — load persisted sessions and begin cleanup."""
        self._ensure_storage_dir()
        self._load_sessions()
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info(f"SessionManager started — loaded {len(self.sessions)} sessions")

    def _ensure_storage_dir(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def stop(self) -> None:
        """Stop the session manager — save all sessions."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        self._save_all_sessions()
        logger.info("SessionManager stopped")

    async def create_session(
        self,
        user_id: str = "anonymous",
        metadata: Dict[str, Any] = None,
        session_id: str = None,
    ) -> Session:
        """Create a new session with optional user association."""
        session_id = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        session = Session(session_id, metadata or {"user_id": user_id})
        self.sessions[session_id] = session
        self._save_session(session_id)
        logger.info(f"Created session {session_id} for user {user_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID, loading from disk if needed."""
        if session_id in self.sessions:
            self.sessions[session_id].last_active = datetime.now(timezone.utc)
            return self.sessions[session_id]

        # Try loading from disk
        session_file = self.storage_path / f"{session_id}.json"
        if session_file.exists():
            try:
                with open(session_file) as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                self.sessions[session_id] = session
                logger.info(f"Loaded session {session_id} from disk")
                return session
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to load session {session_id}: {e}")
                return None

        return None

    async def get_user_sessions(self, user_id: str) -> List[Session]:
        """Get all sessions for a specific user."""
        result = [s for s in self.sessions.values() if s.metadata.get("user_id") == user_id]
        # Also check disk for sessions not in memory
        if self.storage_path.exists():
            for f in self.storage_path.glob("*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                    if data.get("metadata", {}).get("user_id") == user_id and data["session_id"] not in self.sessions:
                        session = Session.from_dict(data)
                        self.sessions[data["session_id"]] = session
                        result.append(session)
                except Exception:
                    continue
        return sorted(result, key=lambda s: s.last_active, reverse=True)

    async def add_message(self, session_id: str, role: str, content: str, **kwargs) -> bool:
        """Add a message to a session."""
        session = await self.get_session(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found for message")
            return False

        session.add_message(role, content, **kwargs)

        # Trim history if needed
        if len(session.messages) > self.max_history:
            session.messages = session.messages[-self.max_history:]

        self._save_session(session_id)
        return True

    async def get_session_history(self, session_id: str, limit: int = None) -> List[Dict]:
        """Get message history for a session."""
        session = await self.get_session(session_id)
        if not session:
            return []
        messages = session.messages
        if limit:
            messages = messages[-limit:]
        return messages

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and its persisted data."""
        if session_id in self.sessions:
            del self.sessions[session_id]
        session_file = self.storage_path / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
        logger.info(f"Deleted session {session_id}")
        return True

    async def delete_old_sessions(self, max_age_hours: int = 24) -> int:
        """Delete sessions older than max_age_hours. Returns count deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        deleted = 0
        for sid in list(self.sessions.keys()):
            if self.sessions[sid].last_active < cutoff:
                await self.delete_session(sid)
                deleted += 1
        return deleted

    def _ensure_storage_dir(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _save_session(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if not session:
            return
        self._ensure_storage_dir()
        session_file = self.storage_path / f"{session_id}.json"
        try:
            with open(session_file, "w") as f:
                json.dump(session.to_dict(), f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")

    def _save_all_sessions(self) -> None:
        for session_id in self.sessions:
            self._save_session(session_id)

    def _load_sessions(self) -> None:
        if not self.storage_path.exists():
            return
        for f in self.storage_path.glob("*.json"):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                session = Session.from_dict(data)
                self.sessions[data["session_id"]] = session
            except Exception as e:
                logger.warning(f"Failed to load session from {f}: {e}")

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up old sessions."""
        try:
            while True:
                await asyncio.sleep(300)  # Every 5 minutes
                deleted = await self.delete_old_sessions(max_age_hours=24)
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old sessions")
        except asyncio.CancelledError:
            pass


# Global session manager instance
_session_manager: Optional[SessionManager] = None


async def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(
            storage_path="./sessions",
            max_history=100,
        )
        await _session_manager.start()
    return _session_manager


async def get_or_create_session(
    session_id: str = None, user_id: str = "anonymous", **metadata
) -> Session:
    """Get existing session or create new one."""
    mgr = await get_session_manager()
    if session_id:
        session = await mgr.get_session(session_id)
        if session:
            return session
    return await mgr.create_session(user_id=user_id, metadata=metadata)


def format_session_history(messages: List[Dict], system_prompt: str = None) -> List[Dict]:
    """Format session history for LLM consumption."""
    formatted = []
    if system_prompt:
        formatted.append({"role": "system", "content": system_prompt})
    for msg in messages:
        role = msg.get("role", "user")
        if role == "tool":
            formatted.append({"role": "tool", "content": msg.get("content", msg.get("result_preview", ""))})
        else:
            formatted.append({"role": role, "content": msg.get("content", "")})
    return formatted