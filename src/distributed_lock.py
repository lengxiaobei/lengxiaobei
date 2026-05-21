"""分布式锁 — 单进程精简版（本地进程锁）"""

import time
from typing import Any, Dict, Optional


class _LocalLock:
    def __init__(self, lock_name: str, timeout: int = 3600):
        self._name = lock_name
        self._acquired_at = time.time()
        self._locked = False

    def get_lock_info(self) -> Optional[Dict[str, Any]]:
        return {"name": self._name, "acquired_at": self._acquired_at}

    def acquire(self, block: bool = True) -> bool:
        if self._locked and not block:
            return False
        self._locked = True
        self._acquired_at = time.time()
        return True

    def release(self):
        self._locked = False


class _LockManager:
    def get_lock(self, lock_name: str, timeout: int = 3600) -> _LocalLock:
        return _LocalLock(lock_name, timeout)


_lock_manager = _LockManager()


def get_lock_manager() -> _LockManager:
    return _lock_manager


def get_lock(lock_name: str, timeout: int = 3600) -> _LocalLock:
    return _LocalLock(lock_name, timeout)
