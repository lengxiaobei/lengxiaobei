"""Vector retrieval boundary with local semantic indexing.

参考来源：
- OpenHuman：记忆节点生成 embedding 并通过语义检索召回。
- OpenClaw：向量检索作为工具/上下文能力隐藏在边界内。

实现说明：优先尝试可选 Chroma；不可用时使用纯 Python hashing embedding + cosine，
同时缓存已编码的 embedding，避免每次搜索都全量重编码。

性能优化：使用增量分页加载而非一次加载全部节点。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)

# Re-encode nodes older than this many seconds
EMBEDDING_TTL = 3600

# Batch size for incremental search
_SEARCH_BATCH = 200


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
    """可替换的向量检索门面，内建 embedding 缓存避免重复编码。"""

    def __init__(
        self,
        memory_tree: Any,
        sqlite: Any | None = None,
        persist_dir: str | None = None,
        pre_filter_min_candidates: int = 5,
    ):
        self.memory_tree = memory_tree
        self.sqlite = sqlite or getattr(memory_tree, "sqlite", None)
        self.embedding = HashEmbedding()
        self.chroma = self._try_chroma(persist_dir)
        # In-memory cache: node_id -> (embedding, cached_at)
        self._cache: dict[str, tuple[list[float], float]] = {}
        # Minimum keyword-match candidates required to skip full scan.
        # If keyword pre-filtering returns fewer than this many nodes
        # the search falls back to a full vector scan for quality.
        self.pre_filter_min_candidates = pre_filter_min_candidates
        # Cache for the most recent query embedding to avoid re-encoding
        # when the same query is searched multiple times in quick succession.
        self._query_embedding_cache: tuple[str, list[float]] | None = None

    def index_node(self, node: dict[str, Any]) -> dict[str, Any]:
        """为记忆节点生成 embedding；Chroma 可用时同步写入 Chroma。"""
        text = self._node_text(node)
        embedding = self.embedding.encode(text)
        node_id = node.get("id")
        if node_id:
            self._cache[str(node_id)] = (embedding, time.time())
            if self.sqlite:
                self.sqlite.update_memory_node(node["id"], embedding=embedding)
        if self.chroma and node_id:
            self.chroma.add(
                ids=[node["id"]],
                documents=[text],
                embeddings=[embedding],
                metadatas=[{"path": node.get("path", "")}],
            )
        return {"id": node_id, "embedding_dims": len(embedding), "backend": "chroma" if self.chroma else "hash"}

    def reindex(self, limit: int = 1000) -> dict[str, Any]:
        """重建当前 SQLite 记忆的向量索引。"""
        nodes = self.memory_tree.list_recent(limit=limit)
        for node in nodes:
            self.index_node(node)
        return {"status": "ok", "count": len(nodes), "backend": "chroma" if self.chroma else "hash"}

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """语义向量检索；query 为空时返回最近节点。

        性能优化：使用 SQLite embedding 字段，避免加载全部节点到内存。
        """
        query = (query or "").strip()
        if not query:
            return self.memory_tree.list_recent(limit=limit)

        # Cache the query embedding so repeated searches with the same
        # query don't re-encode (the HashEmbedding.encode call is cheap
        # but this guards against more expensive future encoders).
        if self._query_embedding_cache and self._query_embedding_cache[0] == query:
            qvec = self._query_embedding_cache[1]
        else:
            qvec = self.embedding.encode(query)
            self._query_embedding_cache = (query, qvec)

        # Chroma path
        if self.chroma:
            try:
                result = self.chroma.query(query_embeddings=[qvec], n_results=limit)
                ids = (result.get("ids") or [[]])[0]
                return [node for node_id in ids if (node := self.memory_tree.get(node_id))]
            except Exception:
                logger.debug("Chroma query failed, falling back to SQLite", exc_info=True)

        # SQLite path: try to use stored embeddings first
        if self.sqlite:
            return self._search_with_stored_embeddings(qvec, query, limit)

        # Fallback: load recent nodes
        return self._search_fallback(qvec, query, limit)

    def _search_with_stored_embeddings(
        self, qvec: list[float], query: str, limit: int
    ) -> list[dict[str, Any]]:
        """Search using embeddings stored in SQLite.

        Optimisation: a keyword-based pre-filter narrows the candidate set
        before the O(n) cosine similarity pass.  When the pre-filter returns
        fewer than *pre_filter_min_candidates* nodes the method falls back
        to a full scan so that result quality is not compromised.
        """
        # -- Fast path: keyword pre-filtering ----------------------------
        candidates = self._keyword_pre_filter(query, limit)
        if candidates is not None:
            logger.debug(
                "Keyword pre-filter returned %d candidates for query %r",
                len(candidates), query,
            )
            return self._score_candidates(qvec, query, candidates, limit)

        # -- Slow path: full scan with incremental loading ---------------
        logger.debug("Pre-filter returned too few candidates; falling back to full scan")
        scored: list[tuple[float, dict[str, Any]]] = []
        query_lower = query.lower()
        offset = 0

        while len(scored) < limit * 3:  # Collect more than needed for sorting
            nodes = self.sqlite.list_memory_nodes(limit=_SEARCH_BATCH, offset=offset) if hasattr(
                self.sqlite, 'list_memory_nodes'
            ) else []
            if not nodes:
                break

            for node in nodes:
                node_id = str(node.get("id") or "")
                embedding = self._get_embedding(node_id, node)
                score = cosine(qvec, embedding)
                # Boost exact keyword matches
                if query_lower in self._node_text(node).lower():
                    score += 0.25
                scored.append((score, node))

            offset += _SEARCH_BATCH
            # Early termination: if we have enough high-scoring results
            if len(scored) >= limit * 5:
                break

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, node in scored[:limit]:
            item = dict(node)
            item["score"] = round(float(score), 4)
            item["vector_backend"] = "hash"
            results.append(item)
        return results

    # ------------------------------------------------------------------
    # Keyword pre-filter helpers
    # ------------------------------------------------------------------

    def _keyword_pre_filter(
        self, query: str, limit: int
    ) -> list[dict[str, Any]] | None:
        """Return candidate nodes via keyword search, or *None* to signal
        that the caller should fall back to a full vector scan.

        Keywords are extracted by splitting on whitespace and discarding
        tokens shorter than 2 characters.  If the SQLite backend does not
        expose ``search_memory_nodes_by_keywords`` the method returns
        *None* immediately.
        """
        if not hasattr(self.sqlite, "search_memory_nodes_by_keywords"):
            return None

        keywords = [w for w in query.split() if len(w) >= 2]
        if not keywords:
            return None

        # Request more candidates than *limit* to give the vector
        # re-ranking step a broader pool to work with.
        candidates = self.sqlite.search_memory_nodes_by_keywords(
            keywords, limit=max(limit * 5, 50)
        )

        if len(candidates) < self.pre_filter_min_candidates:
            return None

        return candidates

    def _score_candidates(
        self,
        qvec: list[float],
        query: str,
        candidates: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Compute cosine similarity for a pre-filtered candidate set and
        return the top *limit* results sorted by descending score."""
        query_lower = query.lower()
        scored: list[tuple[float, dict[str, Any]]] = []

        for node in candidates:
            node_id = str(node.get("id") or "")
            embedding = self._get_embedding(node_id, node)
            score = cosine(qvec, embedding)
            if query_lower in self._node_text(node).lower():
                score += 0.25
            scored.append((score, node))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, node in scored[:limit]:
            item = dict(node)
            item["score"] = round(float(score), 4)
            item["vector_backend"] = "hash"
            results.append(item)
        return results

    def _search_fallback(
        self, qvec: list[float], query: str, limit: int
    ) -> list[dict[str, Any]]:
        """Fallback: load recent nodes and score them."""
        candidates = self.memory_tree.list_recent(limit=500)
        scored = []
        query_lower = query.lower()
        for node in candidates:
            node_id = str(node.get("id") or "")
            embedding = self._get_embedding(node_id, node)
            score = cosine(qvec, embedding)
            if query_lower in self._node_text(node).lower():
                score += 0.25
            scored.append((score, node))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, node in scored[:limit]:
            item = dict(node)
            item["score"] = round(float(score), 4)
            item["vector_backend"] = "hash"
            results.append(item)
        return results

    # ------------------------------------------------------------------
    # Embedding cache with SQLite fallback
    # ------------------------------------------------------------------

    def _get_embedding(self, node_id: str, node: dict[str, Any]) -> list[float]:
        """Return cached embedding, or encode & cache if missing/stale."""
        now = time.time()
        cached = self._cache.get(node_id)
        if cached:
            embedding, cached_at = cached
            if now - cached_at < EMBEDDING_TTL:
                return embedding

        # Try SQLite-stored embedding
        stored = node.get("embedding")
        if isinstance(stored, str) and stored:
            try:
                parsed = json.loads(stored)
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], (int, float)):
                    self._cache[node_id] = (parsed, now)
                    return parsed
            except (json.JSONDecodeError, TypeError):
                logger.debug("Failed to parse stored embedding for node %s", node_id)
        elif isinstance(stored, list) and stored and isinstance(stored[0], (int, float)):
            self._cache[node_id] = (stored, now)
            return stored

        # Fall back to re-encoding
        embedding = self.embedding.encode(self._node_text(node))
        self._cache[node_id] = (embedding, now)
        return embedding

    def _node_text(self, node: dict[str, Any]) -> str:
        return "\n".join(str(node.get(key) or "") for key in ("summary", "content", "path", "type"))

    def _try_chroma(self, persist_dir: str | None):
        try:
            import chromadb

            client = chromadb.PersistentClient(path=persist_dir) if persist_dir else chromadb.Client()
            return client.get_or_create_collection("lengxiaobei_memory")
        except Exception:
            logger.debug("Chroma not available, using hash embedding fallback", exc_info=True)
            return None
