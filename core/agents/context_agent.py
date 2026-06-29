# EchoMind — Context Memory Agent with session isolation

import json
import logging
from typing import List, Dict, Optional
from collections import OrderedDict

from ..models.context import ContextMessage, ContextMemory

logger = logging.getLogger("MemoryAgent")


class SessionContext:
    """Holds messages and metadata for a single session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.memory = ContextMemory()

    def add_message(self, message: Dict[str, str]) -> None:
        msg = ContextMessage(**message)
        self.memory.messages.append(msg)
        if len(self.memory.messages) > self.memory.window_size:
            self.memory.messages.pop(0)

    def get_context(self) -> List[Dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.memory.messages]

    def clear(self) -> None:
        self.memory.messages = []


class ContextMemoryAgent:
    """Session-isolated context agent with LRU eviction.

    Each session_id gets its own SessionContext. Up to max_sessions are
    kept in memory; evicted contexts' messages are written to context_archive
    if a store reference is provided.
    """

    def __init__(self, max_sessions: int = 5):
        self.max_sessions = max_sessions
        self._sessions: OrderedDict[str, SessionContext] = OrderedDict()
        self._db = None  # Set externally for archive support

    def bind_store(self, db):
        """Bind a SqliteStore for archiving evicted messages."""
        self._db = db

    def get_session(self, session_id: str) -> SessionContext:
        """Get or create a SessionContext for the given session_id."""
        if session_id not in self._sessions:
            # Evict oldest if at capacity
            if len(self._sessions) >= self.max_sessions:
                self._evict_oldest()
            self._sessions[session_id] = SessionContext(session_id)
        # Move to end (most recently used)
        self._sessions.move_to_end(session_id)
        return self._sessions[session_id]

    def add_message(self, message: Dict[str, str], session_id: str = "") -> None:
        """Add a message to the session's context."""
        ctx = self.get_session(session_id)
        ctx.add_message(message)

    def get_context(self, session_id: str = "") -> List[Dict[str, str]]:
        """Get context for a specific session (defaults to current)."""
        ctx = self.get_session(session_id)
        return ctx.get_context()

    def clear(self, session_id: str = "") -> None:
        """Clear context for a specific session."""
        if session_id in self._sessions:
            self._sessions[session_id].clear()

    def clear_all(self) -> None:
        """Clear all session contexts."""
        self._sessions.clear()

    def _evict_oldest(self) -> None:
        """Evict the oldest session, archiving messages if db is bound."""
        if not self._sessions:
            return
        _sid, ctx = self._sessions.popitem(last=False)
        logger.debug("Evicting session %s (%d messages)", _sid, len(ctx.memory.messages))
        # Archive evicted messages to context_archive table
        if self._db and self._db._conn and ctx.memory.messages:
            try:
                rows = [(_sid, msg.role, msg.content) for msg in ctx.memory.messages]
                with self._db._lock:
                    self._db._conn.executemany(
                        "INSERT INTO context_archive (session_id, role, content) VALUES (?, ?, ?)", rows)
                    self._db._conn.commit()
            except Exception as e:
                logger.debug("Failed to archive evicted messages: %s", e)