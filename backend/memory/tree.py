"""Editable memory tree API.

参考来源：OpenHuman 的记忆树：节点可层级化、可编辑、可摘要、可检索，并能被同步器写入。
"""

from __future__ import annotations

from typing import Any


class MemoryTree:
    """长期记忆树门面，隔离 SQLite/向量库具体实现。"""

    def __init__(self, sqlite_backend: Any):
        self.sqlite = sqlite_backend

    def add_node(
        self,
        content: str,
        node_type: str = "knowledge",
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """写入一个 OpenHuman 风格记忆节点。"""
        return self.sqlite.insert_memory_node(content, node_type, parent_id, metadata, summary)

    def update_node(self, node_id: str, **changes: Any) -> dict[str, Any] | None:
        """允许人工修正记忆，这是 OpenHuman 记忆系统的关键特征。"""
        return self.sqlite.update_memory_node(node_id, **changes)

    def delete_node(self, node_id: str) -> bool:
        return self.sqlite.delete_memory_node(node_id)

    def get(self, node_id: str) -> dict[str, Any] | None:
        return self.sqlite.get_memory_node(node_id)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.sqlite.search_memory_nodes(query, limit=limit)

    def children(self, parent_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.sqlite.list_memory_nodes(limit=limit, parent_id=parent_id)

    def tree(self, root_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        return self.sqlite.memory_tree(root_id=root_id, limit=limit)

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.sqlite.list_memory_nodes(limit=limit)
