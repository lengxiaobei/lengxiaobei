"""
枚举定义
"""

from enum import Enum


class SpawnMode(Enum):
    """Spawn模式"""
    SINGLE_SESSION = "single-session"
    SAME_DIR = "same-dir"
    WORKTREE = "worktree"


class SessionStatus(Enum):
    """会话状态"""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
