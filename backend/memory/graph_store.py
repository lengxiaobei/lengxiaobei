"""Knowledge graph boundary.

参考来源：OpenHuman / OpenClaw 的知识图谱层：实体关系与记忆节点分离，便于后续用
NetworkX、SQLite edge table 或图数据库替换。
"""

from __future__ import annotations

from typing import Any


class GraphStore:
    """SQLite-backed 知识图谱门面。"""

    def __init__(self, sqlite_backend: Any):
        self.sqlite = sqlite_backend

    def add_edge(self, source: str, relation: str, target: str, **metadata: Any) -> dict[str, Any]:
        """添加实体关系，局部参考 OpenHuman graph_store。"""
        return self.sqlite.add_graph_edge(source, relation, target, metadata)

    def neighbors(self, entity: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.sqlite.graph_neighbors(entity, limit=limit)
