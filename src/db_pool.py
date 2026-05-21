"""
线程安全 SQLite 连接管理器
=========================
解决 HybridMemory/Memory 中 check_same_thread=False 的安全隐患。

策略:
- 每个线程拥有独立的 SQLite 连接（threading.local）
- 写操作加锁，避免并发写入导致 SQLITE_BUSY 或数据损坏
- WAL 模式提升读写并发能力
"""

import sqlite3
import threading
import time
import os
from typing import Optional


class ThreadSafeConnectionPool:
    """
    线程安全 SQLite 连接池

    - 读操作: 每线程独立连接，无锁，支持并发读
    - 写操作: 全局写锁，同一时刻只有一个线程写入
    - WAL 模式: 允许读写并发
    """

    def __init__(self, db_path: str, timeout: float = 30.0):
        self.db_path = db_path
        self.timeout = timeout
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._connections_lock = threading.Lock()
        self._connections = []
        self._closed = False

        # 确保目录存在
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)

        # 在主线程初始化时启用 WAL 模式
        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的连接（惰性创建）"""
        if self._closed:
            raise RuntimeError("ConnectionPool is closed")

        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=False,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f"PRAGMA busy_timeout={int(self.timeout * 1000)}")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
            with self._connections_lock:
                self._connections.append(conn)
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """兼容旧代码的 conn 属性，返回当前线程连接"""
        return self._get_connection()

    def execute_read(self, sql: str, params=()):
        """执行读操作（无锁）"""
        conn = self._get_connection()
        return conn.execute(sql, params)

    def execute_write(self, sql: str, params=()):
        """执行写操作（加锁）"""
        with self._write_lock:
            conn = self._get_connection()
            conn.execute(sql, params)
            conn.commit()

    def execute_write_many(self, sql: str, params_list):
        """批量写操作（加锁，单事务）"""
        with self._write_lock:
            conn = self._get_connection()
            conn.executemany(sql, params_list)
            conn.commit()

    def transaction(self):
        """返回一个事务上下文管理器（写操作加锁）"""
        return _Transaction(self)

    def commit(self):
        """显式提交（加锁）"""
        with self._write_lock:
            self._get_connection().commit()

    def close(self):
        """关闭所有已创建的线程连接"""
        self._closed = True
        with self._connections_lock:
            connections = self._connections
            self._connections = []

        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

        self._local.conn = None

    def __del__(self):
        self.close()


class _Transaction:
    """事务上下文管理器"""

    def __init__(self, pool: ThreadSafeConnectionPool):
        self.pool = pool
        self._lock_acquired = False

    def __enter__(self):
        self.pool._write_lock.acquire()
        self._lock_acquired = True
        conn = self.pool._get_connection()
        conn.execute("BEGIN")
        return conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        conn = self.pool._get_connection()
        try:
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
        finally:
            if self._lock_acquired:
                self.pool._write_lock.release()
                self._lock_acquired = False
        return False
