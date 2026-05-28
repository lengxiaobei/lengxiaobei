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
    """Thin wrapper that delegates to :class:`SQLiteBackend`.

    Preserves the legacy public API used by AgentLoop and other callers
    while sharing the richer ``memory_nodes`` schema from ``SQLiteBackend``.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from backend.config import PROJECT_ROOT

            db_path = Path(PROJECT_ROOT) / "data" / "memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Delegate all storage to the richer backend
        self._backend = SQLiteBackend(self.db_path)
        # Ensure legacy flat nodes table still exists for any old data
        self._ensure_tables()

    # -- internal helpers -------------------------------------------------

    def _ensure_tables(self) -> None:
        """Create the legacy ``nodes`` table if it does not already exist."""
        with self._backend.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT,
                    node_type TEXT,
                    metadata_json TEXT DEFAULT '{}',
                    summary TEXT,
                    created_at REAL,
                    updated_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
                CREATE INDEX IF NOT EXISTS idx_nodes_created ON nodes(created_at);
                """
            )

    @staticmethod
    def _to_flat_format(record: dict[str, Any] | None) -> dict[str, Any] | None:
        """Convert a ``memory_nodes`` record to the legacy flat dict shape.

        The returned dict mirrors the old ``MemoryNode.to_dict()`` output::

            {id, content, node_type, metadata, summary, created_at, updated_at}
        """
        if record is None:
            return None
        metadata = record.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (TypeError, json.JSONDecodeError):
                metadata = {}
        elif metadata is None:
            metadata = {}
        return {
            "id": record.get("id"),
            "content": record.get("content", ""),
            "node_type": record.get("type", ""),
            "metadata": metadata,
            "summary": record.get("summary", ""),
            "created_at": record.get("created_at", 0.0),
            "updated_at": record.get("updated_at", 0.0),
        }

    # -- Write ------------------------------------------------------------

    def add_node(
        self,
        content: str,
        node_type: str = "conversation",
        metadata: dict[str, Any] | None = None,
        summary: str = "",
        created_at: float | None = None,
    ) -> dict[str, Any]:
        """Insert a new memory node.  Returns the created node in flat format."""
        result = self._backend.insert_memory_node(
            content=content,
            node_type=node_type,
            metadata=metadata,
            summary=summary or content[:120],
        )
        return self._to_flat_format(result) or {}

    def get_node(self, node_id: int | str) -> dict[str, Any] | None:
        return self._to_flat_format(self._backend.get_memory_node(node_id))

    def update_node(self, node_id: int | str, **fields: Any) -> dict[str, Any] | None:
        """Update specified fields on a node, mapping legacy field names."""
        changes: dict[str, Any] = {}
        for key in ("content", "summary"):
            if key in fields:
                changes[key] = fields[key]
        if "node_type" in fields:
            changes["type"] = fields["node_type"]
        if "metadata" in fields:
            changes["metadata"] = fields["metadata"]
        if not changes:
            return self.get_node(node_id)
        result = self._backend.update_memory_node(node_id, **changes)
        return self._to_flat_format(result)

    def delete_node(self, node_id: int | str) -> bool:
        return self._backend.delete_memory_node(node_id)

    # -- Search -----------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 8,
        node_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Keyword + recency search.  Returns most recent matching nodes."""
        query = (query or "").strip()
        with self._backend.connect() as conn:
            if node_types:
                placeholders = ", ".join("?" * len(node_types))
                sql = (
                    f"SELECT * FROM memory_nodes"
                    f" WHERE (content LIKE ? OR summary LIKE ? OR path LIKE ? OR metadata LIKE ?)"
                    f" AND type IN ({placeholders})"
                    f" ORDER BY updated_at DESC LIMIT ?"
                )
                like = f"%{query}%"
                params: tuple = (like, like, like, like, *node_types, limit)
            else:
                sql = (
                    "SELECT * FROM memory_nodes"
                    " WHERE content LIKE ? OR summary LIKE ? OR path LIKE ? OR metadata LIKE ?"
                    " ORDER BY updated_at DESC LIMIT ?"
                )
                like = f"%{query}%"
                params = (like, like, like, like, limit)
            rows = conn.execute(sql, params).fetchall()
        return [self._to_flat_format(dict(r)) for r in rows]

    def list_recent(
        self, limit: int = 20, node_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Return the most recent memory nodes."""
        if node_types:
            with self._backend.connect() as conn:
                placeholders = ", ".join("?" * len(node_types))
                rows = conn.execute(
                    f"SELECT * FROM memory_nodes WHERE type IN ({placeholders})"
                    f" ORDER BY updated_at DESC LIMIT ?",
                    (*node_types, limit),
                ).fetchall()
            return [self._to_flat_format(dict(r)) for r in rows]
        results = self._backend.list_memory_nodes(limit=limit)
        return [self._to_flat_format(r) for r in results]

    def get_context_window(self, before_ts: float, limit: int = 30) -> list[dict[str, Any]]:
        """Get recent nodes before a given timestamp for context building."""
        with self._backend.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_nodes WHERE created_at < ? ORDER BY created_at DESC LIMIT ?",
                (before_ts, limit),
            ).fetchall()
        return [self._to_flat_format(dict(r)) for r in rows]

    def count(self, node_type: str | None = None) -> int:
        with self._backend.connect() as conn:
            if node_type:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM memory_nodes WHERE type = ?", (node_type,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) as c FROM memory_nodes").fetchone()
        return row["c"] if row else 0

    def iter_nodes(
        self, node_type: str | None = None, batch_size: int = 100
    ) -> Iterator[dict[str, Any]]:
        """Yield all nodes, optionally filtered by type.  For batch processing."""
        offset = 0
        while True:
            with self._backend.connect() as conn:
                if node_type:
                    rows = conn.execute(
                        "SELECT * FROM memory_nodes WHERE type = ?"
                        " ORDER BY created_at DESC LIMIT ? OFFSET ?",
                        (node_type, batch_size, offset),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM memory_nodes ORDER BY created_at DESC LIMIT ? OFFSET ?",
                        (batch_size, offset),
                    ).fetchall()
            if not rows:
                break
            for row in rows:
                yield self._to_flat_format(dict(row))
            if len(rows) < batch_size:
                break
            offset += batch_size

    # -- Maintenance ------------------------------------------------------

    def prune(self, keep_count: int = 5000) -> int:
        """Remove oldest nodes beyond *keep_count*.  Returns count removed."""
        total = self.count()
        if total <= keep_count:
            return 0
        to_remove = total - keep_count
        with self._backend.connect() as conn:
            rows = conn.execute(
                "SELECT id FROM memory_nodes ORDER BY created_at ASC LIMIT ?",
                (to_remove,),
            ).fetchall()
            for row in rows:
                conn.execute("DELETE FROM memory_nodes WHERE id = ?", (row["id"],))
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
                    version INTEGER DEFAULT 1,
                    source_run_id TEXT,
                    last_used_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS failure_patterns (
                    id TEXT PRIMARY KEY,
                    pattern TEXT NOT NULL,
                    tool TEXT,
                    error_signature TEXT NOT NULL,
                    occurrence_count INTEGER DEFAULT 1,
                    first_seen_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    resolution TEXT,
                    resolved INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_failure_patterns_tool ON failure_patterns(tool);
                CREATE INDEX IF NOT EXISTS idx_failure_patterns_resolved ON failure_patterns(resolved);
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
                -- Trace tables for agent observability (Phase 1)
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    user_message TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'web',
                    status TEXT NOT NULL DEFAULT 'running',
                    final_reply TEXT,
                    total_tool_calls INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    elapsed_ms REAL DEFAULT 0,
                    created_at REAL NOT NULL,
                    finished_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);

                CREATE TABLE IF NOT EXISTS agent_steps (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    llm_input_tokens INTEGER DEFAULT 0,
                    llm_output_tokens INTEGER DEFAULT 0,
                    tool_calls_count INTEGER DEFAULT 0,
                    summary TEXT,
                    elapsed_ms REAL DEFAULT 0,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps(run_id);

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT,
                    tool TEXT NOT NULL,
                    args TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    ok INTEGER NOT NULL DEFAULT 1,
                    elapsed_ms REAL DEFAULT 0,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id);

                CREATE TABLE IF NOT EXISTS reflections (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'auto',
                    trigger TEXT,
                    diagnosis TEXT NOT NULL,
                    lesson TEXT,
                    skill_generated TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_reflections_run ON reflections(run_id);
                """
            )
            # Migration: add columns to existing skills table if missing
            self._migrate_skills_table(conn)

    def _migrate_skills_table(self, conn: sqlite3.Connection) -> None:
        """Add new columns to skills table if they don't exist."""
        cursor = conn.execute("PRAGMA table_info(skills)")
        existing = {row[1] for row in cursor.fetchall()}
        migrations = [
            ("version", "INTEGER DEFAULT 1"),
            ("source_run_id", "TEXT"),
            ("last_used_at", "REAL"),
        ]
        for col_name, col_type in migrations:
            if col_name not in existing:
                try:
                    conn.execute(f"ALTER TABLE skills ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass  # Column may already exist from concurrent migration

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

    def search_memory_nodes_by_keywords(
        self, keywords: list[str], limit: int = 50
    ) -> list[dict[str, Any]]:
        """Search memory nodes matching ANY of the given keywords.

        Used by VectorStore for keyword-based pre-filtering before
        vector similarity computation.  Each keyword is matched with
        LIKE against *content*, *summary*, and *path*.
        """
        if not keywords:
            return []
        conditions: list[str] = []
        params: list[Any] = []
        for kw in keywords:
            like = f"%{kw}%"
            conditions.append("(content LIKE ? OR summary LIKE ? OR path LIKE ?)")
            params.extend([like, like, like])
        where_clause = " OR ".join(conditions)
        sql = (
            f"SELECT DISTINCT * FROM memory_nodes "
            f"WHERE {where_clause} "
            f"ORDER BY updated_at DESC LIMIT ?"
        )
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
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
            # Delete-then-insert to avoid ON CONFLICT issues with older schemas
            conn.execute("DELETE FROM skills WHERE name = ?", (name,))
            conn.execute(
                """
                INSERT INTO skills (id, name, trigger, body, status, success_count, fail_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
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
            conn.execute(
                f"UPDATE skills SET {field}={field}+1, last_used_at=?, updated_at=? WHERE name=?",
                (time.time(), time.time(), name),
            )

    def get_skill_stats(self, name: str) -> dict[str, Any] | None:
        """Get skill with calculated success rate."""
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM skills WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        data = dict(row)
        total = data.get("success_count", 0) + data.get("fail_count", 0)
        data["total_uses"] = total
        data["success_rate"] = round(data["success_count"] / total * 100, 1) if total > 0 else 0
        data["body"] = self._loads(data.get("body"), {})
        return data

    def list_skills_with_stats(self, status: str | None = None) -> list[dict[str, Any]]:
        """List skills with calculated success rates."""
        with self.connect() as conn:
            if status:
                rows = conn.execute("SELECT * FROM skills WHERE status=? ORDER BY updated_at DESC", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM skills ORDER BY updated_at DESC").fetchall()
        result = []
        for row in rows:
            data = dict(row)
            total = data.get("success_count", 0) + data.get("fail_count", 0)
            data["total_uses"] = total
            data["success_rate"] = round(data["success_count"] / total * 100, 1) if total > 0 else 0
            data["body"] = self._loads(data.get("body"), {})
            result.append(data)
        return result

    def auto_demote_skills(self, min_uses: int = 5, min_success_rate: float = 30.0) -> list[str]:
        """Auto-demote skills with low success rate. Returns list of demoted skill names."""
        demoted = []
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT name, success_count, fail_count FROM skills
                   WHERE status='approved' AND (success_count + fail_count) >= ?""",
                (min_uses,),
            ).fetchall()
            for row in rows:
                total = row["success_count"] + row["fail_count"]
                rate = row["success_count"] / total * 100 if total > 0 else 0
                if rate < min_success_rate:
                    conn.execute(
                        "UPDATE skills SET status='demoted', updated_at=? WHERE name=?",
                        (time.time(), row["name"]),
                    )
                    demoted.append(row["name"])
        return demoted

    def upgrade_skill_version(self, name: str) -> int:
        """Increment skill version. Returns new version."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE skills SET version=version+1, updated_at=? WHERE name=?",
                (time.time(), name),
            )
            row = conn.execute("SELECT version FROM skills WHERE name=?", (name,)).fetchone()
        return row["version"] if row else 0

    # ── Failure Patterns ──────────────────────────────────────────

    def record_failure_pattern(
        self,
        pattern: str,
        tool: str,
        error_signature: str,
        resolution: str = "",
    ) -> str:
        """Record or increment a failure pattern. Returns pattern id."""
        # Check if this pattern already exists
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id, occurrence_count FROM failure_patterns WHERE error_signature=? AND tool=? AND resolved=0",
                (error_signature, tool),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE failure_patterns SET occurrence_count=occurrence_count+1, last_seen_at=? WHERE id=?",
                    (time.time(), existing["id"]),
                )
                return existing["id"]
            # Create new pattern
            pattern_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO failure_patterns (id, pattern, tool, error_signature, occurrence_count, first_seen_at, last_seen_at, resolution)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
                (pattern_id, pattern, tool, error_signature, time.time(), time.time(), resolution),
            )
        return pattern_id

    def get_failure_patterns(self, tool: str | None = None, unresolved_only: bool = True, min_occurrences: int = 2) -> list[dict[str, Any]]:
        """Get failure patterns, optionally filtered by tool."""
        clauses = []
        params: list[Any] = []
        if unresolved_only:
            clauses.append("resolved=0")
        if tool:
            clauses.append("tool=?")
            params.append(tool)
        clauses.append("occurrence_count>=?")
        params.append(min_occurrences)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM failure_patterns {where} ORDER BY occurrence_count DESC, last_seen_at DESC",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def resolve_failure_pattern(self, pattern_id: str, resolution: str = "") -> None:
        """Mark a failure pattern as resolved."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE failure_patterns SET resolved=1, resolution=?, last_seen_at=? WHERE id=?",
                (resolution, time.time(), pattern_id),
            )

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

    # ── Trace: Agent Runs ─────────────────────────────────────────

    def trace_start_run(self, user_message: str, channel: str = "web") -> str:
        """Create a new agent run. Returns run_id."""
        run_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO agent_runs (id, user_message, channel, status, created_at)
                   VALUES (?, ?, ?, 'running', ?)""",
                (run_id, user_message, channel, time.time()),
            )
        return run_id

    def trace_finish_run(
        self,
        run_id: str,
        *,
        status: str = "completed",
        final_reply: str = "",
        total_tool_calls: int = 0,
        total_steps: int = 0,
        elapsed_ms: float = 0,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """UPDATE agent_runs SET status=?, final_reply=?, total_tool_calls=?,
                   total_steps=?, elapsed_ms=?, finished_at=? WHERE id=?""",
                (status, final_reply, total_tool_calls, total_steps, elapsed_ms, time.time(), run_id),
            )

    # ── Trace: Steps ─────────────────────────────────────────────

    def trace_add_step(
        self,
        run_id: str,
        step_index: int,
        phase: str = "execute",
        summary: str = "",
        tool_calls_count: int = 0,
        elapsed_ms: float = 0,
    ) -> str:
        step_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO agent_steps (id, run_id, step_index, phase, tool_calls_count, summary, elapsed_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (step_id, run_id, step_index, phase, tool_calls_count, summary, elapsed_ms, time.time()),
            )
        return step_id

    # ── Trace: Tool Calls ─────────────────────────────────────────

    def trace_add_tool_call(
        self,
        run_id: str,
        tool: str,
        args: dict[str, Any],
        result: Any = None,
        *,
        step_id: str = "",
        ok: bool = True,
        error: str = "",
        elapsed_ms: float = 0,
    ) -> str:
        call_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO tool_calls (id, run_id, step_id, tool, args, result, error, ok, elapsed_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    call_id, run_id, step_id, tool,
                    json.dumps(args, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
                    error, 1 if ok else 0, elapsed_ms, time.time(),
                ),
            )
        return call_id

    # ── Trace: Reflections ────────────────────────────────────────

    def trace_add_reflection(
        self,
        run_id: str,
        diagnosis: str,
        *,
        kind: str = "auto",
        trigger: str = "",
        lesson: str = "",
        skill_generated: str = "",
    ) -> str:
        ref_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO reflections (id, run_id, kind, trigger, diagnosis, lesson, skill_generated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ref_id, run_id, kind, trigger, diagnosis, lesson, skill_generated, time.time()),
            )
        return ref_id

    # ── Trace: Queries ────────────────────────────────────────────

    def trace_list_runs(self, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM agent_runs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def trace_get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def trace_get_steps(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_steps WHERE run_id=? ORDER BY step_index",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def trace_get_tool_calls(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_calls WHERE run_id=? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["args"] = self._loads(d.get("args"), {})
            d["result"] = self._loads(d.get("result"), d.get("result"))
            d["ok"] = bool(d.get("ok"))
            result.append(d)
        return result

    def trace_get_reflections(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reflections WHERE run_id=? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def trace_get_full_run(self, run_id: str) -> dict[str, Any] | None:
        """Get run with all nested data (steps, tool_calls, reflections)."""
        run = self.trace_get_run(run_id)
        if not run:
            return None
        run["steps"] = self.trace_get_steps(run_id)
        run["tool_calls"] = self.trace_get_tool_calls(run_id)
        run["reflections"] = self.trace_get_reflections(run_id)
        return run

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
