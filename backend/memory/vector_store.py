"""Vector retrieval boundary with local semantic indexing.

参考来源：
- OpenHuman：记忆节点生成 embedding 并通过语义检索召回。
- OpenClaw：向量检索作为工具/上下文能力隐藏在边界内。

实现说明：优先尝试可选 Chroma；不可用时使用纯 Python hashing embedding + cosine，
这样在离线/轻依赖环境也具备真实向量索引能力，而不是简单 LIKE 搜索。
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

TOKEN_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)


class HashEmbedding:
    """离线 hashing embedding，功能等价 OpenHuman 本地向量召回的轻量实现。"""

    def __init__(self, dims: int = 256):
        self.dims = dims

    def encode(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        tokens = TOKEN_RE.findall((text or "").lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dims
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class VectorStore:
    """可替换的向量检索门面。"""

    def __init__(self, memory_tree: Any, sqlite: Any | None = None, persist_dir: str | None = None):
        self.memory_tree = memory_tree
        self.sqlite = sqlite or getattr(memory_tree, "sqlite", None)
        self.embedding = HashEmbedding()
        self.chroma = self._try_chroma(persist_dir)

    def index_node(self, node: dict[str, Any]) -> dict[str, Any]:
        """为记忆节点生成 embedding；Chroma 可用时同步写入 Chroma。"""
        text = self._node_text(node)
        embedding = self.embedding.encode(text)
        if self.sqlite and node.get("id"):
            metadata = dict(node.get("metadata") or {})
            metadata["vector_indexed"] = True
            self.sqlite.update_memory_node(node["id"], metadata=metadata)
        if self.chroma and node.get("id"):
            self.chroma.add(
                ids=[node["id"]],
                documents=[text],
                embeddings=[embedding],
                metadatas=[{"path": node.get("path", "")}],
            )
        return {"id": node.get("id"), "embedding_dims": len(embedding), "backend": "chroma" if self.chroma else "hash"}

    def reindex(self, limit: int = 1000) -> dict[str, Any]:
        """重建当前 SQLite 记忆的向量索引。"""
        nodes = self.memory_tree.list_recent(limit=limit)
        for node in nodes:
            self.index_node(node)
        return {"status": "ok", "count": len(nodes), "backend": "chroma" if self.chroma else "hash"}

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """语义向量检索；query 为空时返回最近节点。"""
        query = (query or "").strip()
        if not query:
            return self.memory_tree.list_recent(limit=limit)
        qvec = self.embedding.encode(query)
        if self.chroma:
            try:
                result = self.chroma.query(query_embeddings=[qvec], n_results=limit)
                ids = (result.get("ids") or [[]])[0]
                return [node for node_id in ids if (node := self.memory_tree.get(node_id))]
            except Exception:
                pass
        candidates = self.memory_tree.list_recent(limit=1000)
        scored = []
        for node in candidates:
            text = self._node_text(node)
            score = cosine(qvec, self.embedding.encode(text))
            lexical = 0.25 if query.lower() in text.lower() else 0.0
            scored.append((score + lexical, node))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, node in scored[:limit]:
            item = dict(node)
            item["score"] = round(float(score), 4)
            item["vector_backend"] = "hash"
            results.append(item)
        return results

    def _node_text(self, node: dict[str, Any]) -> str:
        return "\n".join(str(node.get(key) or "") for key in ("summary", "content", "path", "type"))

    def _try_chroma(self, persist_dir: str | None):
        try:
            import chromadb

            client = chromadb.PersistentClient(path=persist_dir) if persist_dir else chromadb.Client()
            return client.get_or_create_collection("lengxiaobei_memory")
        except Exception:
            return None
