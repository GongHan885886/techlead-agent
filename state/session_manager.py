"""Session and pending task management."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from typing import Awaitable

from config import settings


@dataclass
class PendingTask:
    """Represents a task pending user confirmation."""

    task_type: str  # e.g., "cr_comments", "design_review_approval"
    task_data: Dict[str, Any]
    execute_callback: Callable[[], Awaitable[Dict[str, Any]]]
    created_at: datetime
    expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if task has expired.

        Returns:
            bool: True if expired
        """
        if not self.expires_at:
            # Default timeout from settings
            timeout = timedelta(minutes=settings.session_timeout_minutes)
            return datetime.now() > self.created_at + timeout

        return datetime.now() > self.expires_at

    async def execute(self) -> Dict[str, Any]:
        """Execute the pending task.

        Returns:
            dict: Execution result
        """
        return await self.execute_callback()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            dict: Serialized task
        """
        data = {
            "task_type": self.task_type,
            "task_data": self.task_data,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
        # Note: execute_callback is not serializable
        return data


class SessionManager:
    """Manages user sessions and pending tasks."""

    def __init__(self):
        """Initialize session manager."""
        self.state_file = settings.state_dir / "pending_tasks.json"
        self.state_dir = settings.state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # In-memory storage
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._pending_tasks: Dict[str, PendingTask] = {}

    def create_session(self, session_id: str) -> Dict[str, Any]:
        """Create a new session.

        Args:
            session_id: Unique session identifier

        Returns:
            dict: Session data
        """
        session = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "context": {},
        }

        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data.

        Args:
            session_id: Session identifier

        Returns:
            dict or None: Session data if found
        """
        return self._sessions.get(session_id)

    def update_session(self, session_id: str, updates: Dict[str, Any]):
        """Update session data.

        Args:
            session_id: Session identifier
            updates: Data to update
        """
        if session_id in self._sessions:
            self._sessions[session_id].update(updates)
            self._sessions[session_id]["last_activity"] = datetime.now().isoformat()

    def delete_session(self, session_id: str):
        """Delete a session.

        Args:
            session_id: Session identifier
        """
        self._sessions.pop(session_id, None)
        self.clear_pending(session_id)

    def set_pending_task(self, session_id: str, task: PendingTask):
        """Set a pending task for a session.

        Args:
            session_id: Session identifier
            task: Pending task
        """
        self._pending_tasks[session_id] = task
        self._persist_pending_tasks()

    def get_pending_task(self, session_id: str) -> Optional[PendingTask]:
        """Get pending task for a session.

        Args:
            session_id: Session identifier

        Returns:
            PendingTask or None
        """
        task = self._pending_tasks.get(session_id)

        # Check if expired
        if task and task.is_expired():
            self.clear_pending(session_id)
            return None

        return task

    def clear_pending(self, session_id: str):
        """Clear pending task for a session.

        Args:
            session_id: Session identifier
        """
        self._pending_tasks.pop(session_id, None)
        self._persist_pending_tasks()

    def _persist_pending_tasks(self):
        """Persist pending tasks to disk."""
        try:
            # Convert pending tasks to serializable format
            serializable = {
                session_id: task.to_dict()
                for session_id, task in self._pending_tasks.items()
            }

            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"⚠️  Failed to persist pending tasks: {e}")

    def cleanup_expired_sessions(self):
        """Clean up expired sessions and pending tasks."""
        now = datetime.now()
        timeout = timedelta(minutes=settings.session_timeout_minutes)

        expired_sessions = []

        for session_id, session in self._sessions.items():
            last_activity = datetime.fromisoformat(session.get("last_activity", ""))
            if now - last_activity > timeout:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self.delete_session(session_id)

        if expired_sessions:
            print(f"🧹 Cleaned up {len(expired_sessions)} expired sessions")

    def get_active_session_count(self) -> int:
        """Get count of active sessions.

        Returns:
            int: Number of active sessions
        """
        return len(self._sessions)

    def get_pending_task_count(self) -> int:
        """Get count of pending tasks.

        Returns:
            int: Number of pending tasks
        """
        return len(self._pending_tasks)