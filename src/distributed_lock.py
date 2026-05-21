"""
分布式锁 — 基于文件锁 (fcntl.flock) 的跨进程互斥锁

支持：
- 跨进程互斥（同机器多实例/daemon/launchd 重启并发）
- 可重入（同一线程可多次获取）
- Stale lock 检测（基于 timeout）
- 上下文管理器 (with 语句)
"""

import fcntl
import os
import threading
import time
from typing import Any, Dict, Optional


class _FileLock:
    """基于 fcntl.flock 的跨进程文件锁"""

    def __init__(self, lock_name: str, timeout: int = 3600):
        self._name = lock_name
        self._timeout = timeout
        # 进程内线程互斥
        self._thread_lock = threading.Lock()
        self._owner: Optional[int] = None
        self._reentrant_count = 0
        self._acquired_at: Optional[float] = None
        # 文件锁
        self._lock_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "state", "locks"
        )
        os.makedirs(self._lock_dir, exist_ok=True)
        # 锁名安全化
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in lock_name)
        self._lock_path = os.path.join(self._lock_dir, f"{safe_name}.lock")
        self._fd = None

    def get_lock_info(self) -> Optional[Dict[str, Any]]:
        if self._owner is None:
            return None
        return {
            "name": self._name,
            "owner": self._owner,
            "acquired_at": self._acquired_at,
            "reentrant_count": self._reentrant_count,
            "lock_file": self._lock_path,
        }

    def acquire(self, block: bool = True) -> bool:
        current_thread = threading.current_thread().ident
        # 可重入：同一线程可多次获取
        if self._owner == current_thread:
            self._reentrant_count += 1
            return True

        # 先获取进程内线程锁
        if not self._thread_lock.acquire(blocking=block):
            return False

        try:
            # 检查 stale lock：如果锁文件存在且内容显示已超时，强制释放
            self._check_stale()

            # 打开锁文件
            self._fd = open(self._lock_path, "w")
            # 非阻塞尝试获取文件锁
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, IOError):
                if not block:
                    self._fd.close()
                    self._fd = None
                    self._thread_lock.release()
                    return False
                # 阻塞模式：循环等待
                self._fd.close()
                self._fd = None
                while True:
                    self._check_stale()
                    self._fd = open(self._lock_path, "w")
                    try:
                        fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX)
                        break
                    except (OSError, IOError):
                        self._fd.close()
                        self._fd = None
                        time.sleep(0.1)
                        continue

            # 写入锁持有者信息
            self._fd.write(f"{os.getpid()}\n{current_thread}\n{time.time()}\n")
            self._fd.flush()

            self._owner = current_thread
            self._reentrant_count = 1
            self._acquired_at = time.time()
            return True
        except Exception:
            if self._fd:
                self._fd.close()
                self._fd = None
            self._thread_lock.release()
            raise

    def release(self):
        current_thread = threading.current_thread().ident
        if self._owner != current_thread:
            raise RuntimeError(
                f"线程 {current_thread} 尝试释放由线程 {self._owner} 持有的锁 '{self._name}'"
            )
        self._reentrant_count -= 1
        if self._reentrant_count == 0:
            self._owner = None
            self._acquired_at = None
            # 释放文件锁
            if self._fd:
                try:
                    fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
                    self._fd.close()
                except Exception:
                    pass
                self._fd = None
            self._thread_lock.release()

    def _check_stale(self):
        """检查并清理过期锁（其他进程持有但已超时）"""
        if not os.path.exists(self._lock_path):
            return
        try:
            with open(self._lock_path, "r") as f:
                content = f.read().strip().split("\n")
            if len(content) >= 3:
                acquired_at = float(content[2])
                if time.time() - acquired_at > self._timeout:
                    # 尝试获取并释放（清理 stale lock）
                    try:
                        fd = open(self._lock_path, "w")
                        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                        fd.close()
                    except (OSError, IOError):
                        pass  # 锁仍被持有，跳过
        except Exception:
            pass

    def __enter__(self):
        self.acquire(block=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class _LockManager:
    """锁管理器 — 同名锁共享同一实例"""

    def __init__(self):
        self._locks: Dict[str, _FileLock] = {}
        self._mutex = threading.Lock()

    def get_lock(self, lock_name: str, timeout: int = 3600) -> _FileLock:
        with self._mutex:
            if lock_name not in self._locks:
                self._locks[lock_name] = _FileLock(lock_name, timeout)
            return self._locks[lock_name]


_lock_manager = _LockManager()


def get_lock_manager() -> _LockManager:
    return _lock_manager


def get_lock(lock_name: str, timeout: int = 3600) -> _FileLock:
    return _lock_manager.get_lock(lock_name, timeout)
