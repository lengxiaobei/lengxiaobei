"""SQLite persistence for YourAgent runtime data.

参考来源：
- OpenHuman：memory_nodes 表承载可编辑记忆树，节点可摘要、可挂父节点、可被检索。
- Hermes：skills/tool_traces 表保留技能状态、执行轨迹、成功/失败计数，支持 pending 审核流。
- OpenClaw：conversations/sync_status/graph_edges 表给多渠道网关、工具调度和外部同步器提供统一持久层。
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class SQLiteBackend:
    """本地优先 SQLite 后端，实现 YourAgent 的主要持久化能力。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        """创建 YourAgent 文档中的核心表，并补齐功能等价所需的 trace/graph 表。"""
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
            self._ensure_column(conn, "memory_nodes", "embedding", "TEXT")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def insert_memory_node(
        self,
        content: str,
        node_type: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        summary: str | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """新增记忆节点，参考 OpenHuman 的树形节点模型。"""
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
                    record["id"], record["parent_id"], record["path"], record["type"],
                    record["content"], record["summary"],
                    json.dumps(embedding, ensure_ascii=False) if embedding is not None else None,
                    json.dumps(record["metadata"], ensure_ascii=False), record["created_at"], record["updated_at"],
                ),
            )
        return record

    def update_memory_node(self, node_id: str, **changes: Any) -> dict[str, Any] | None:
        """编辑记忆节点，体现 OpenHuman 的可人工修正原则。"""
        allowed = {"content", "summary", "parent_id", "type", "metadata"}
        updates = {k: v for k, v in changes.items() if k in allowed}
        if not updates:
            return self.get_memory_node(node_id)
        updates["updated_at"] = time.time()
        assignments = ", ".join(f"{key}=?" for key in updates)
        values = [json.dumps(v, ensure_ascii=False) if key == "metadata" else v for key, v in updates.items()]
        with self.connect() as conn:
            conn.execute(f"UPDATE memory_nodes SET {assignments} WHERE id=?", [*values, node_id])
        return self.get_memory_node(node_id)

    def delete_memory_node(self, node_id: str) -> bool:
        """删除单个记忆节点；子节点保留但会失去父级，方便人工重组。"""
        with self.connect() as conn:
            conn.execute("UPDATE memory_nodes SET parent_id=NULL, updated_at=? WHERE parent_id=?", (time.time(), node_id))
            cur = conn.execute("DELETE FROM memory_nodes WHERE id=?", (node_id,))
        return cur.rowcount > 0

    def get_memory_node(self, node_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM memory_nodes WHERE id=?", (node_id,)).fetchone()
        return self._decode_row(row) if row else None

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
        return [self._decode_row(row) for row in rows]

    def list_memory_nodes(self, limit: int = 100, parent_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if parent_id is None:
                rows = conn.execute("SELECT * FROM memory_nodes ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_nodes WHERE parent_id=? ORDER BY updated_at DESC LIMIT ?",
                    (parent_id, limit),
                ).fetchall()
        return [self._decode_row(row) for row in rows]

    def memory_tree(self, root_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        """返回扁平树节点，前端可按 parent_id 渲染树。"""
        with self.connect() as conn:
            if root_id:
                rows = conn.execute(
                    "SELECT * FROM memory_nodes WHERE id=? OR path LIKE (SELECT path || '/%' FROM memory_nodes WHERE id=?) ORDER BY path LIMIT ?",
                    (root_id, root_id, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM memory_nodes ORDER BY path LIMIT ?", (limit,)).fetchall()
        return [self._decode_row(row) for row in rows]

    def upsert_skill(self, name: str, trigger: str, body: dict[str, Any], status: str = "pending") -> dict[str, Any]:
        """记录 Hermes 风格技能草稿，默认 pending 等待人工审核。"""
        now = time.time()
        skill_id = uuid.uuid4().hex
        body_text = json.dumps(body, ensure_ascii=False)
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM skills WHERE name=?", (name,)).fetchone()
            if existing:
                skill_id = existing["id"]
                conn.execute(
                    "UPDATE skills SET trigger=?, body=?, status=?, updated_at=? WHERE id=?",
                    (trigger, body_text, status, now, skill_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO skills (id, name, trigger, body, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (skill_id, name, trigger, body_text, status, now, now),
                )
        return {"id": skill_id, "name": name, "trigger": trigger, "body": body, "status": status}

    def update_skill_status(self, name: str, status: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute("UPDATE skills SET status=?, updated_at=? WHERE name=?", (status, time.time(), name))
        return self.get_skill(name)

    def get_skill(self, name: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM skills WHERE name=? OR id=?", (name, name)).fetchone()
        return self._decode_skill(row) if row else None

    def list_skills(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if status:
                rows = conn.execute("SELECT * FROM skills WHERE status=? ORDER BY updated_at DESC", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM skills ORDER BY updated_at DESC").fetchall()
        return [self._decode_skill(row) for row in rows]

    def record_skill_result(self, name: str, ok: bool) -> None:
        field = "success_count" if ok else "fail_count"
        with self.connect() as conn:
            conn.execute(f"UPDATE skills SET {field}={field}+1, updated_at=? WHERE name=?", (time.time(), name))

    def record_tool_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        trace_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tool_traces (id, tool, args, ok, result, error, elapsed_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    str(trace.get("tool") or "unknown"),
                    json.dumps(trace.get("args") or {}, ensure_ascii=False),
                    1 if trace.get("ok") else 0,
                    json.dumps(trace.get("result"), ensure_ascii=False, default=str),
                    trace.get("error"),
                    float(trace.get("elapsed_ms") or 0),
                    now,
                ),
            )
        return {"id": trace_id, **trace, "created_at": now}

    def list_tool_traces(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM tool_traces ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode_trace(row) for row in rows]

    def add_graph_edge(self, source: str, relation: str, target: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        now = time.time()
        edge_id = uuid.uuid4().hex
        edge = {"id": edge_id, "source": source, "relation": relation, "target": target, "metadata": metadata or {}, "created_at": now}
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO graph_edges (id, source, relation, target, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (edge_id, source, relation, target, json.dumps(edge["metadata"], ensure_ascii=False), now),
            )
        return edge

    def graph_neighbors(self, entity: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM graph_edges WHERE source=? OR target=? ORDER BY created_at DESC LIMIT ?",
                (entity, entity, limit),
            ).fetchall()
        return [self._decode_edge(row) for row in rows]

    def set_sync_status(self, service: str, status: str, detail: dict[str, Any] | None = None) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_status(service, last_sync, status, detail) VALUES (?, ?, ?, ?)
                ON CONFLICT(service) DO UPDATE SET last_sync=excluded.last_sync, status=excluded.status, detail=excluded.detail
                """,
                (service, now, status, json.dumps(detail or {}, ensure_ascii=False)),
            )

    def list_sync_status(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM sync_status ORDER BY service").fetchall()
        return [dict(row) | {"detail": self._json(row["detail"], {})} for row in rows]

    def _parent_path(self, parent_id: str | None) -> str:
        if not parent_id:
            return ""
        parent = self.get_memory_node(parent_id)
        return str(parent.get("path") or "") if parent else ""

    def _json(self, value: Any, fallback: Any) -> Any:
        try:
            return json.loads(value) if value not in (None, "") else fallback
        except (TypeError, json.JSONDecodeError):
            return fallback

    def _decode_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = self._json(data.get("metadata"), {})
        data["embedding"] = self._json(data.get("embedding"), None)
        return data

    def _decode_skill(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["body"] = self._json(data.get("body"), {})
        return data

    def _decode_trace(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["args"] = self._json(data.get("args"), {})
        data["result"] = self._json(data.get("result"), data.get("result"))
        data["ok"] = bool(data.get("ok"))
        return data

    def _decode_edge(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = self._json(data.get("metadata"), {})
        return data
