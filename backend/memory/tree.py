"""Editable memory tree API.

参考来源：OpenHuman 的记忆树：节点可层级化、可编辑、可摘要、可检索，并能被同步器写入。
增强：接入 VectorStore 进行语义混合检索。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MemoryTree:
    """长期记忆树门面，隔离 SQLite/向量库具体实现。"""

    def __init__(self, sqlite_backend: Any, vector_store: Any | None = None):
        self.sqlite = sqlite_backend
        self._vector_store = vector_store

    @property
    def vector_store(self) -> Any | None:
        return self._vector_store

    @vector_store.setter
    def vector_store(self, store: Any) -> None:
        self._vector_store = store

    def add_node(
        self,
        content: str,
        node_type: str = "knowledge",
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """写入一个 OpenHuman 风格记忆节点。"""
        node = self.sqlite.insert_memory_node(content, node_type, parent_id, metadata, summary)
        # Auto-index in vector store if available
        if self._vector_store and node:
            try:
                self._vector_store.index_node(node)
            except Exception:
                logger.debug("Failed to index node %s in vector store", node.get("id"), exc_info=True)
        return node

    def update_node(self, node_id: str, **changes: Any) -> dict[str, Any] | None:
        """允许人工修正记忆，这是 OpenHuman 记忆系统的关键特征。"""
        node = self.sqlite.update_memory_node(node_id, **changes)
        if self._vector_store and node:
            try:
                self._vector_store.index_node(node)
            except Exception:
                logger.debug("Failed to re-index node %s after update", node_id, exc_info=True)
        return node

    def delete_node(self, node_id: str) -> bool:
        return self.sqlite.delete_memory_node(node_id)

    def get(self, node_id: str) -> dict[str, Any] | None:
        return self.sqlite.get_memory_node(node_id)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Hybrid search: blend vector similarity with keyword matching.

        当 VectorStore 可用时，优先使用语义检索，补充关键词结果。
        否则回退到 SQLite LIKE 查询。
        """
        query = (query or "").strip()
        if not query:
            return self.sqlite.list_memory_nodes(limit=limit)

        # Try vector search first
        if self._vector_store:
            try:
                vector_results = self._vector_store.search(query, limit=limit)
                if vector_results:
                    return vector_results
            except Exception:
                logger.debug("Vector search failed for query '%s', falling back to keyword", query[:50], exc_info=True)

        return self.sqlite.search_memory_nodes(query, limit=limit)

    def children(self, parent_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.sqlite.list_memory_nodes(limit=limit, parent_id=parent_id)

    def tree(self, root_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        return self.sqlite.memory_tree(root_id=root_id, limit=limit)

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.sqlite.list_memory_nodes(limit=limit)
