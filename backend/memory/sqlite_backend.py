"""Persistent memory backend using SQLite.

Stores conversation nodes, facts, goals, and skill metadata.
Used by AgentLoop and Commander for long-term recall.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator

try:
    import sqlite_utils
except ImportError:  # pragma: no cover - exercised in lean test environments
    sqlite_utils = None


def _sqlite_utils_not_found_error() -> type[Exception]:
    if sqlite_utils is None:
        return KeyError
    return sqlite_utils.db.NotFoundError


@dataclass
class MemoryNode:
    """A single memory node stored in SQLite."""

    id: int | None
    content: str
    node_type: str  # conversation | autonomy_learning | fact | goal | skill | system
    metadata_json: str  # JSON-serialized metadata
    summary: str
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["metadata"] = json.loads(d.pop("metadata_json"))
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "MemoryNode":
        return cls(
            id=row["id"],
            content=row["content"],
            node_type=row["node_type"],
            metadata_json=row["metadata_json"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SQLiteMemoryBackend:
    """SQLite-backed memory store with keyword + recency recall."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from backend.config import PROJECT_ROOT

            db_path = Path(PROJECT_ROOT) / "data" / "memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if sqlite_utils is None:
            raise RuntimeError("SQLiteMemoryBackend requires sqlite-utils; install sqlite-utils>=3.36")
        self.db = sqlite_utils.Database(self.db_path)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        if "nodes" not in self.db.table_names():
            self.db["nodes"].insert(
                {
                    "id": 0,
                    "content": "",
                    "node_type": "",
                    "metadata_json": "{}",
                    "summary": "",
                    "created_at": 0.0,
                    "updated_at": 0.0,
                },
                pk="id",
                replace=True,
            )
            self.db["nodes"].transform(drop={"id"})  # auto-increment
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type)"
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_created ON nodes(created_at)"
            )

    def _query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return self.db.execute_returning_dicts(sql, params)

    # ── Write ─────────────────────────────────────────────────────────

    def add_node(
        self,
        content: str,
        node_type: str = "conversation",
        metadata: dict[str, Any] | None = None,
        summary: str = "",
        created_at: float | None = None,
    ) -> dict[str, Any]:
        """Insert a new memory node. Returns the created node dict."""
        now = created_at or time.time()
        node = MemoryNode(
            id=None,
            content=content,
            node_type=node_type,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            summary=summary or content[:120],
            created_at=now,
            updated_at=now,
        )
        self.db["nodes"].insert(node.__dict__, pk="id")
        new_id = node.__dict__["id"]
        return self.get_node(new_id)

    def get_node(self, node_id: int) -> dict[str, Any] | None:
        try:
            row = self.db["nodes"].get(node_id)
            return MemoryNode.from_row(row).to_dict()
        except (KeyError, IndexError, _sqlite_utils_not_found_error()):
            return None

    def update_node(self, node_id: int, **fields: Any) -> dict[str, Any] | None:
        """Update specified fields on a node."""
        try:
            existing = self.get_node(node_id)
            if existing is None:
                return None
            updates: dict[str, Any] = {"updated_at": time.time()}
            for key in ("content", "node_type", "summary"):
                if key in fields:
                    updates[key] = fields[key]
            if "metadata" in fields:
                updates["metadata_json"] = json.dumps(fields["metadata"], ensure_ascii=False)
            if not updates:
                return existing
            self.db["nodes"].update(node_id, updates)
            return self.get_node(node_id)
        except (KeyError, IndexError, _sqlite_utils_not_found_error()):
            return None

    def delete_node(self, node_id: int) -> bool:
        try:
            self.db["nodes"].delete_where("id = ?", [node_id])
            return True
        except Exception:
            return False

    # ── Search ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: int = 8,
        node_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Keyword + recency search. Returns most recent matching nodes."""
        if node_types:
            placeholders = ", ".join("?" * len(node_types))
            sql = f"""
                SELECT * FROM nodes
                WHERE content LIKE ? AND node_type IN ({placeholders})
                ORDER BY created_at DESC LIMIT ?
            """
            params = (f"%{query}%", *node_types, limit)
        else:
            sql = """
                SELECT * FROM nodes
                WHERE content LIKE ?
                ORDER BY created_at DESC LIMIT ?
            """
            params = (f"%{query}%", limit)
        rows = self._query(sql, params)
        return [MemoryNode.from_row(r).to_dict() for r in rows]

    def list_recent(self, limit: int = 20, node_types: list[str] | None = None) -> list[dict[str, Any]]:
        """Return the most recent memory nodes."""
        if node_types:
            placeholders = ", ".join("?" * len(node_types))
            sql = f"SELECT * FROM nodes WHERE node_type IN ({placeholders}) ORDER BY created_at DESC LIMIT ?"
            params = (*node_types, limit)
        else:
            sql = "SELECT * FROM nodes ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        rows = self._query(sql, params)
        return [MemoryNode.from_row(r).to_dict() for r in rows]

    def get_context_window(self, before_ts: float, limit: int = 30) -> list[dict[str, Any]]:
        """Get recent nodes before a given timestamp for context building."""
        sql = "SELECT * FROM nodes WHERE created_at < ? ORDER BY created_at DESC LIMIT ?"
        rows = self._query(sql, (before_ts, limit))
        return [MemoryNode.from_row(r).to_dict() for r in rows]

    def count(self, node_type: str | None = None) -> int:
        if node_type:
            sql = "SELECT COUNT(*) as c FROM nodes WHERE node_type = ?"
            rows = self._query(sql, (node_type,))
        else:
            sql = "SELECT COUNT(*) as c FROM nodes"
            rows = self._query(sql)
        return rows[0]["c"]

    def iter_nodes(
        self, node_type: str | None = None, batch_size: int = 100
    ) -> Iterator[dict[str, Any]]:
        """Yield all nodes, optionally filtered by type. For batch processing."""
        offset = 0
        while True:
            if node_type:
                sql = "SELECT * FROM nodes WHERE node_type = ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params = (node_type, batch_size, offset)
            else:
                sql = "SELECT * FROM nodes ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params = (batch_size, offset)
            rows = self._query(sql, params)
            if not rows:
                break
            for row in rows:
                yield MemoryNode.from_row(row).to_dict()
            offset += batch_size
            if len(rows) < batch_size:
                break

    # ── Maintenance ────────────────────────────────────────────────────

    def prune(self, keep_count: int = 5000) -> int:
        """Remove oldest nodes beyond keep_count. Returns count removed."""
        total = self.count()
        if total <= keep_count:
            return 0
        to_remove = total - keep_count
        sql = "SELECT id FROM nodes ORDER BY created_at ASC LIMIT ?"
        rows = self._query(sql, (to_remove,))
        for row in rows:
            self.db["nodes"].delete_where("id = ?", [row["id"]])
        return len(rows)


# ── Legacy compatibility shim ────────────────────────────────────────────────
# Existing code (MemoryTree, tests) expects `SQLiteBackend` with methods like
# `insert_memory_node`, `update_memory_node`, `delete_memory_node`, etc.


class SQLiteBackend:
    """Compatibility backend for the main YourAgent runtime tables."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from backend.config import PROJECT_ROOT

            db_path = Path(PROJECT_ROOT) / "data" / "sqlite" / "agent.db"
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    channel TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_nodes (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    path TEXT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT,
                    embedding TEXT,
                    metadata TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_parent ON memory_nodes(parent_id);
                CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_nodes(type);
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    trigger TEXT,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tool_traces (
                    id TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    args TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    result TEXT,
                    error TEXT,
                    elapsed_ms REAL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tool_traces_created ON tool_traces(created_at);
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_edges(source);
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sync_status (
                    service TEXT PRIMARY KEY,
                    last_sync REAL,
                    status TEXT NOT NULL,
                    detail TEXT
                );
                """
            )

    def insert_memory_node(
        self,
        content: str,
        node_type: str = "knowledge",
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        summary: str | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        node_id = uuid.uuid4().hex
        parent_path = self._parent_path(parent_id)
        path = f"{parent_path.rstrip('/')}/{node_type}/{node_id}" if parent_path else f"/{node_type}/{node_id}"
        record = {
            "id": node_id,
            "parent_id": parent_id,
            "path": path,
            "type": node_type,
            "content": content,
            "summary": summary or content[:180],
            "embedding": embedding,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_nodes
                (id, parent_id, path, type, content, summary, embedding, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["parent_id"],
                    record["path"],
                    record["type"],
                    record["content"],
                    record["summary"],
                    json.dumps(embedding, ensure_ascii=False) if embedding is not None else None,
                    json.dumps(record["metadata"], ensure_ascii=False),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return record

    def update_memory_node(self, node_id: str | int, **changes: Any) -> dict[str, Any] | None:
        allowed = {"content", "summary", "parent_id", "type", "metadata", "embedding"}
        updates = {key: value for key, value in changes.items() if key in allowed}
        if not updates:
            return self.get_memory_node(node_id)
        updates["updated_at"] = time.time()
        assignments = ", ".join(f"{key}=?" for key in updates)
        values = [
            json.dumps(value, ensure_ascii=False) if key in {"metadata", "embedding"} and value is not None else value
            for key, value in updates.items()
        ]
        with self.connect() as conn:
            conn.execute(f"UPDATE memory_nodes SET {assignments} WHERE id=?", [*values, str(node_id)])
        return self.get_memory_node(node_id)

    def delete_memory_node(self, node_id: str | int) -> bool:
        with self.connect() as conn:
            conn.execute("UPDATE memory_nodes SET parent_id=NULL, updated_at=? WHERE parent_id=?", (time.time(), str(node_id)))
            cur = conn.execute("DELETE FROM memory_nodes WHERE id=?", (str(node_id),))
        return cur.rowcount > 0

    def get_memory_node(self, node_id: str | int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM memory_nodes WHERE id=?", (str(node_id),)).fetchone()
        return self._decode_memory_row(row) if row else None

    def list_memory_nodes(
        self,
        limit: int = 100,
        offset: int = 0,
        node_type: str | None = None,
        parent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if node_type is not None:
            clauses.append("type=?")
            params.append(node_type)
        if parent_id is not None:
            clauses.append("parent_id=?")
            params.append(parent_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_nodes {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [self._decode_memory_row(row) for row in rows]

    def search_memory_nodes(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        query = (query or "").strip()
        with self.connect() as conn:
            if not query:
                rows = conn.execute("SELECT * FROM memory_nodes ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                like = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT * FROM memory_nodes
                    WHERE content LIKE ? OR summary LIKE ? OR path LIKE ? OR metadata LIKE ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (like, like, like, like, limit),
                ).fetchall()
        return [self._decode_memory_row(row) for row in rows]

    def memory_tree(self, root_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if root_id:
                rows = conn.execute(
                    """
                    SELECT * FROM memory_nodes
                    WHERE id=? OR path LIKE (SELECT path || '/%' FROM memory_nodes WHERE id=?)
                    ORDER BY path LIMIT ?
                    """,
                    (root_id, root_id, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM memory_nodes ORDER BY path LIMIT ?", (limit,)).fetchall()
        return [self._decode_memory_row(row) for row in rows]

    def upsert_skill(self, name: str, trigger: str, body: dict[str, Any], status: str = "pending") -> dict[str, Any]:
        now = time.time()
        skill_id = uuid.uuid5(uuid.NAMESPACE_URL, name).hex
        payload = json.dumps(body, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO skills (id, name, trigger, body, status, success_count, fail_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    trigger=excluded.trigger,
                    body=excluded.body,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (skill_id, name, trigger, payload, status, now, now),
            )
        return self.get_skill(name) or {}

    def get_skill(self, name: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM skills WHERE name=?", (name,)).fetchone()
        return self._decode_skill_row(row) if row else None

    def list_skills(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if status:
                rows = conn.execute("SELECT * FROM skills WHERE status=? ORDER BY updated_at DESC", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM skills ORDER BY updated_at DESC").fetchall()
        return [self._decode_skill_row(row) for row in rows]

    def record_skill_result(self, name: str, ok: bool) -> None:
        field = "success_count" if ok else "fail_count"
        with self.connect() as conn:
            conn.execute(f"UPDATE skills SET {field}={field}+1, updated_at=? WHERE name=?", (time.time(), name))

    def record_tool_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "tool": str(trace.get("tool") or ""),
            "args": json.dumps(trace.get("args") or {}, ensure_ascii=False),
            "ok": 1 if trace.get("ok") else 0,
            "result": json.dumps(trace.get("result"), ensure_ascii=False, default=str),
            "error": str(trace.get("error") or ""),
            "elapsed_ms": float(trace.get("elapsed_ms") or 0),
            "created_at": float(trace.get("created_at") or time.time()),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tool_traces (id, tool, args, ok, result, error, elapsed_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(record.values()),
            )
        return record

    def list_tool_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM tool_traces ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["args"] = self._loads(item.get("args"), {})
            item["result"] = self._loads(item.get("result"), item.get("result"))
            item["ok"] = bool(item.get("ok"))
            result.append(item)
        return result

    def graph_neighbors(self, entity: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM graph_edges
                WHERE source=? OR target=?
                ORDER BY created_at DESC LIMIT ?
                """,
                (entity, entity, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_user_profile(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM user_profile WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_user_profile(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_profile (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, time.time()),
            )

    def list_sync_status(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM sync_status ORDER BY service").fetchall()
        return [dict(row) for row in rows]

    def search_sessions(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        like = f"%{query.strip()}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM conversations
                WHERE messages LIKE ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _parent_path(self, parent_id: str | None) -> str:
        if not parent_id:
            return ""
        parent = self.get_memory_node(parent_id)
        return str((parent or {}).get("path") or "")

    def _decode_memory_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = self._loads(data.get("metadata"), {})
        data["embedding"] = self._loads(data.get("embedding"), None)
        return data

    def _decode_skill_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["body"] = self._loads(data.get("body"), {})
        return data

    def _loads(self, value: Any, default: Any) -> Any:
        if value in (None, ""):
            return default
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default
