"""Session management with multi-session support and context pruning.

参考来源：OpenClaw 的 session 管理 —— 多 session 隔离、context pruning（cache-ttl + compaction）、
session history、session listing。

植入目标：让 lengxiaobei 支持 OpenClaw 级别的 session 生命周期管理。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # user | assistant | system | tool
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0


@dataclass
class Session:
    """A conversation session with context management."""
    id: str
    name: str = ""
    agent_id: str = "main"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: list[Message] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    context_tokens: int = 0
    max_context_tokens: int = 200000
    compaction_count: int = 0

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def is_active(self) -> bool:
        return time.time() - self.updated_at < 3600  # Active if updated within 1 hour


class SessionManager:
    """Manages conversation sessions with context pruning.

    Features:
    - Multi-session support (create, list, switch, delete)
    - Context pruning via TTL-based cache expiry
    - Compaction: summarize old messages to stay within token budget
    - Session history retrieval
    """

    def __init__(
        self,
        max_sessions: int = 50,
        default_max_context: int = 200000,
        compaction_threshold: float = 0.7,
        cache_ttl_seconds: int = 900,  # 15 minutes
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._active_session_id: str | None = None
        self.max_sessions = max_sessions
        self.default_max_context = default_max_context
        self.compaction_threshold = compaction_threshold
        self.cache_ttl_seconds = cache_ttl_seconds

    # ── Session CRUD ─────────────────────────────────────────────────

    def create_session(
        self,
        name: str = "",
        agent_id: str = "main",
        max_context: int | None = None,
    ) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())[:12]
        session = Session(
            id=session_id,
            name=name or f"session-{session_id[:6]}",
            agent_id=agent_id,
            max_context_tokens=max_context or self.default_max_context,
        )
        self._sessions[session_id] = session

        # Auto-cleanup if too many sessions
        if len(self._sessions) > self.max_sessions:
            self._cleanup_old_sessions()

        logger.info("Created session: %s (%s)", session_id, session.name)
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str | None = None, **kwargs: Any) -> Session:
        """Get existing session or create new one."""
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            session.updated_at = time.time()
            return session
        return self.create_session(**kwargs)

    def list_sessions(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """List all sessions with summary info."""
        sessions = []
        for s in self._sessions.values():
            if agent_id and s.agent_id != agent_id:
                continue
            sessions.append({
                "id": s.id,
                "name": s.name,
                "agent_id": s.agent_id,
                "message_count": s.message_count,
                "context_tokens": s.context_tokens,
                "max_context_tokens": s.max_context_tokens,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "is_active": s.is_active,
                "compaction_count": s.compaction_count,
            })
        return sorted(sessions, key=lambda x: x["updated_at"], reverse=True)

    def delete_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            if self._active_session_id == session_id:
                self._active_session_id = None
            return True
        return False

    def set_active(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._active_session_id = session_id
            self._sessions[session_id].updated_at = time.time()
            return True
        return False

    @property
    def active_session(self) -> Session | None:
        if self._active_session_id:
            return self._sessions.get(self._active_session_id)
        return None

    # ── Message management ───────────────────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Message | None:
        """Add a message to a session, triggering context pruning if needed."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        msg = Message(
            role=role,
            content=content,
            token_count=token_count,
            metadata=metadata or {},
        )
        session.messages.append(msg)
        session.context_tokens += token_count
        session.updated_at = time.time()

        # Trigger pruning if over threshold
        if session.context_tokens > session.max_context_tokens * self.compaction_threshold:
            self._prune_context(session)

        return msg

    def get_messages(
        self,
        session_id: str,
        limit: int | None = None,
        include_system: bool = True,
    ) -> list[dict[str, str]]:
        """Get messages in OpenAI format for LLM calls."""
        session = self._sessions.get(session_id)
        if not session:
            return []

        messages = []
        for msg in session.messages:
            if not include_system and msg.role == "system":
                continue
            messages.append({"role": msg.role, "content": msg.content})

        if limit:
            messages = messages[-limit:]
        return messages

    def get_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get message history with metadata."""
        session = self._sessions.get(session_id)
        if not session:
            return []

        history = []
        for msg in session.messages[-limit:]:
            history.append({
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "token_count": msg.token_count,
                "metadata": msg.metadata,
            })
        return history

    # ── Context pruning ──────────────────────────────────────────────

    def _prune_context(self, session: Session) -> None:
        """Prune context to stay within token budget.

        Strategy (mirrors OpenClaw's cache-ttl + compaction):
        1. Remove expired cached messages (older than TTL)
        2. If still over budget, compact old messages into a summary
        """
        target_tokens = int(session.max_context_tokens * 0.5)  # Prune to 50%
        now = time.time()

        # Phase 1: Remove expired messages (keep recent + system messages)
        expired_indices = []
        for i, msg in enumerate(session.messages):
            if msg.role == "system":
                continue
            if now - msg.timestamp > self.cache_ttl_seconds:
                expired_indices.append(i)

        # Remove expired (in reverse order to preserve indices)
        for i in reversed(expired_indices):
            removed = session.messages.pop(i)
            session.context_tokens -= removed.token_count

        # Phase 2: If still over budget, compact oldest messages
        if session.context_tokens > target_tokens:
            self._compact_messages(session, target_tokens)

    def _compact_messages(self, session: Session, target_tokens: int) -> None:
        """Compact old messages into a summary to reduce token count.

        Takes the oldest non-system messages and replaces them with a summary.
        """
        if len(session.messages) < 4:
            return  # Don't compact very short conversations

        # Find the midpoint of non-system messages
        non_system = [(i, m) for i, m in enumerate(session.messages) if m.role != "system"]
        if len(non_system) < 4:
            return

        mid = len(non_system) // 2
        old_messages = non_system[:mid]

        # Build summary content
        summary_parts = []
        for _, msg in old_messages:
            summary_parts.append(f"[{msg.role}] {msg.content[:100]}...")

        summary_content = f"[历史消息摘要 - {len(old_messages)}条消息已压缩]\n" + "\n".join(summary_parts)

        # Remove old messages and insert summary
        indices_to_remove = [i for i, _ in old_messages]
        for i in reversed(indices_to_remove):
            removed = session.messages.pop(i)
            session.context_tokens -= removed.token_count

        # Insert summary at the beginning (after any system messages)
        insert_at = 0
        for i, msg in enumerate(session.messages):
            if msg.role != "system":
                insert_at = i
                break

        summary_msg = Message(
            role="system",
            content=summary_content,
            token_count=len(summary_content) // 2,  # Rough estimate
            metadata={"compacted": True, "original_count": len(old_messages)},
        )
        session.messages.insert(insert_at, summary_msg)
        session.context_tokens += summary_msg.token_count
        session.compaction_count += 1

        logger.info(
            "Compacted %d messages in session %s (tokens: %d -> %d)",
            len(old_messages), session.id,
            session.context_tokens + sum(m.token_count for _, m in old_messages),
            session.context_tokens,
        )

    # ── Maintenance ──────────────────────────────────────────────────

    def _cleanup_old_sessions(self) -> None:
        """Remove oldest inactive sessions to stay under max_sessions."""
        sorted_sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
        )
        while len(self._sessions) > self.max_sessions:
            oldest = sorted_sessions.pop(0)
            if oldest.id != self._active_session_id:
                del self._sessions[oldest.id]
                logger.info("Cleaned up old session: %s", oldest.id)

    def get_stats(self) -> dict[str, Any]:
        """Return session manager statistics."""
        total_messages = sum(s.message_count for s in self._sessions.values())
        total_tokens = sum(s.context_tokens for s in self._sessions.values())
        return {
            "total_sessions": len(self._sessions),
            "active_session": self._active_session_id,
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "max_sessions": self.max_sessions,
        }


# ── Singleton ───────────────────────────────────────────────────────

_manager: SessionManager | None = None


def get_session_manager(**kwargs: Any) -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager(**kwargs)
    return _manager
