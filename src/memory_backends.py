"""
记忆存储后端策略
================
将 HybridMemory 中的三重嵌套 if/elif/elif 降级逻辑
提取为独立的策略类，每个后端实现统一接口。

后端优先级:
1. MemoryAPIStrategy — 独立记忆层 API (Rust)
2. QdrantStrategy — Qdrant 向量数据库
3. FAISSStrategy — 本地 FAISS 索引
4. SQLiteFallbackStrategy — SQLite 关键词搜索（最终降级）
"""

import os
import json
import time
import hashlib
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any


class StorageBackend(ABC):
    """存储后端抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """后端名称"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查后端是否可用"""
        ...

    @abstractmethod
    def store_vector(self, mem_id: int, content: str, embedding: List[float],
                     metadata: Dict[str, Any]) -> bool:
        """存储向量"""
        ...

    @abstractmethod
    def search_vector(self, query_embedding: List[float], limit: int,
                      mem_type: Optional[str] = None) -> List[Dict]:
        """向量搜索，返回 [{id, score, metadata}, ...]"""
        ...


class MemoryAPIStrategy(StorageBackend):
    """独立记忆层 API 后端（Rust 实现）"""

    def __init__(self, api_url: str, load_balancer=None):
        self.api_url = api_url.rstrip('/')
        self.load_balancer = load_balancer
        self._available = False
        self._requests = None

        try:
            import requests
            self._requests = requests
            resp = requests.post(
                f"{self.api_url}/memory/search",
                json={"query": "test", "limit": 1}, timeout=5
            )
            if resp.status_code == 200:
                self._available = True
                if load_balancer is not None:
                    load_balancer.add_memory_instance(api_url, "primary_memory", weight=10)
        except Exception:
            pass

    @property
    def name(self) -> str:
        return "memory_api"

    def is_available(self) -> bool:
        return self._available

    def store_vector(self, mem_id: int, content: str, embedding: List[float],
                     metadata: Dict[str, Any]) -> bool:
        if not self._available or self._requests is None:
            return False
        try:
            def _store(url):
                resp = self._requests.post(
                    f"{url.rstrip('/')}/memory/add",
                    json={"content": content, "memory_type": metadata.get("mem_type", "context")}
                )
                return resp.status_code == 200

            if self.load_balancer:
                return self.load_balancer.execute_with_instance(_store)
            else:
                return _store(self.api_url)
        except Exception:
            return False

    def search_vector(self, query_embedding: List[float], limit: int,
                      mem_type: Optional[str] = None) -> List[Dict]:
        if not self._available or self._requests is None:
            return []
        try:
            search_data = {"query_vector": query_embedding, "limit": limit}
            if mem_type:
                search_data["memory_type"] = mem_type

            if self.load_balancer:
                return self.load_balancer.execute_with_instance(
                    lambda url: self._do_search(url, search_data)
                )
            else:
                return self._do_search(self.api_url, search_data)
        except Exception:
            return []

    def _do_search(self, url: str, search_data: dict) -> List[Dict]:
        resp = self._requests.post(
            f"{url.rstrip('/')}/memory/search",
            json=search_data, timeout=10
        )
        if resp.status_code != 200:
            return []
        results = []
        for r in resp.json().get("results", []):
            results.append({
                "id": r.get("id", 0),
                "content": r.get("content", ""),
                "type": r.get("memory_type", "context"),
                "score": r.get("score", 0.0),
            })
        return results


class QdrantStrategy(StorageBackend):
    """Qdrant 向量数据库后端"""

    def __init__(self, qdrant_url: str, collection: str, embedding_dim: int = 384):
        self.qdrant_url = qdrant_url.rstrip('/')
        self.collection = collection
        self.embedding_dim = embedding_dim
        self._available = False
        self._requests = None

        try:
            import requests
            self._requests = requests
            self._ensure_collection()
            self._available = True
        except Exception:
            pass

    @property
    def name(self) -> str:
        return "qdrant"

    def is_available(self) -> bool:
        return self._available

    def _ensure_collection(self):
        """确保 Qdrant 集合存在"""
        try:
            resp = self._requests.get(f"{self.qdrant_url}/collections", timeout=5)
            if resp.status_code != 200:
                return
            names = [c["name"] for c in resp.json().get("result", {}).get("collections", [])]
            if self.collection not in names:
                self._requests.put(
                    f"{self.qdrant_url}/collections/{self.collection}",
                    json={"vectors": {"size": self.embedding_dim, "distance": "Cosine"}},
                    timeout=10
                )
        except Exception:
            pass

    def store_vector(self, mem_id: int, content: str, embedding: List[float],
                     metadata: Dict[str, Any]) -> bool:
        if not self._available:
            return False
        try:
            payload = {
                "points": [{
                    "id": mem_id,
                    "vector": embedding,
                    "payload": metadata,
                }]
            }
            resp = self._requests.post(
                f"{self.qdrant_url}/collections/{self.collection}/points/upsert",
                json=payload, timeout=10
            )
            return resp.status_code == 200
        except Exception:
            return False

    def search_vector(self, query_embedding: List[float], limit: int,
                      mem_type: Optional[str] = None) -> List[Dict]:
        if not self._available:
            return []
        try:
            search_payload = {
                "vector": query_embedding,
                "limit": limit,
                "with_payload": True
            }
            if mem_type:
                search_payload["filter"] = {
                    "must": [{"key": "type", "match": {"value": mem_type}}]
                }
            resp = self._requests.post(
                f"{self.qdrant_url}/collections/{self.collection}/points/search",
                json=search_payload, timeout=10
            )
            if resp.status_code != 200:
                return []
            results = []
            for r in resp.json().get("result", []):
                p = r.get("payload", {})
                results.append({
                    "id": r.get("id", 0),
                    "content": p.get("content", ""),
                    "type": p.get("type", "context"),
                    "role": p.get("role", ""),
                    "tags": p.get("tags", []),
                    "name": p.get("name", ""),
                    "description": p.get("description", ""),
                    "score": r.get("score", 0.0),
                })
            return results
        except Exception:
            return []


class FAISSStrategy(StorageBackend):
    """本地 FAISS 索引后端"""

    def __init__(self, index_path: str, embedding_dim: int = 384):
        self.index_path = index_path
        self.embedding_dim = embedding_dim
        self.index = None
        self.id_to_memory: Dict[int, int] = {}
        self._faiss = None
        self._available = False

        try:
            import faiss
            self._faiss = faiss
            self.index = self._load_or_create_index()
            self._available = True
        except Exception:
            pass

    @property
    def name(self) -> str:
        return "faiss"

    def is_available(self) -> bool:
        return self._available and self.index is not None

    def _load_or_create_index(self):
        if os.path.exists(self.index_path):
            try:
                return self._faiss.read_index(self.index_path)
            except Exception:
                pass
        return self._faiss.IndexFlatL2(self.embedding_dim)

    def store_vector(self, mem_id: int, content: str, embedding: List[float],
                     metadata: Dict[str, Any]) -> bool:
        if not self._available or self.index is None:
            return False
        try:
            import numpy as np
            self.index.add(np.array([embedding]))
            self.id_to_memory[len(self.id_to_memory)] = mem_id
            self._faiss.write_index(self.index, self.index_path)
            return True
        except Exception:
            return False

    def search_vector(self, query_embedding: List[float], limit: int,
                      mem_type: Optional[str] = None) -> List[Dict]:
        """FAISS 搜索返回 ID 列表，详细信息需从 SQLite 补全"""
        if not self._available or self.index is None:
            return []
        try:
            import numpy as np
            k = min(limit * 3, self.index.ntotal)
            if k == 0:
                return []
            distances, indices = self.index.search(np.array([query_embedding]), k)
            mem_ids = []
            seen = set()
            for idx in indices[0]:
                if idx != -1:
                    mid = self.id_to_memory.get(int(idx))
                    if mid and mid not in seen:
                        mem_ids.append(mid)
                        seen.add(mid)
                        if len(mem_ids) >= limit * 2:
                            break
            # 返回 ID 列表，由 HybridMemory 从 SQLite 补全
            return [{"id": mid, "_from_faiss": True} for mid in mem_ids]
        except Exception:
            return []

    def rebuild_from_db(self, conn, embedding_model):
        """从数据库重建 FAISS 索引"""
        if not self._available or self.index is None or embedding_model is None:
            return
        try:
            import numpy as np
            cursor = conn.execute("SELECT id, content FROM memories")
            memories = cursor.fetchall()
            if not memories:
                return
            self.index.reset()
            self.id_to_memory = {}
            batch_size = min(64, len(memories))
            contents = [m[1] for m in memories]
            embeddings = []
            for i in range(0, len(contents), batch_size):
                batch = contents[i:i + batch_size]
                embeddings.extend(embedding_model.encode(batch, batch_size=batch_size, show_progress_bar=False))
            embeddings = np.array(embeddings)
            if hasattr(self.index, 'train') and not self.index.is_trained:
                self.index.train(embeddings)
            self.index.add(embeddings)
            for i, (mem_id, _) in enumerate(memories):
                self.id_to_memory[i] = mem_id
            self._faiss.write_index(self.index, self.index_path)
        except Exception:
            pass


class SQLiteFallbackStrategy(StorageBackend):
    """SQLite 关键词搜索后端（最终降级）"""

    def __init__(self, conn_provider):
        """conn_provider: callable 返回 sqlite3.Connection"""
        self._conn_provider = conn_provider

    @property
    def name(self) -> str:
        return "sqlite_fallback"

    def is_available(self) -> bool:
        return True  # SQLite 始终可用

    def store_vector(self, mem_id: int, content: str, embedding: List[float],
                     metadata: Dict[str, Any]) -> bool:
        return True  # SQLite 存储由 HybridMemory 自身管理

    def search_vector(self, query_embedding: List[float], limit: int,
                      mem_type: Optional[str] = None) -> List[Dict]:
        """关键词搜索（忽略 embedding，用 query 文本）"""
        # 此方法在向量搜索场景下不直接使用
        # HybridMemory 会在所有向量后端失败时调用 _keyword_search
        return []


# ---------------------------------------------------------------------------
# 辅助：构建后端链
# ---------------------------------------------------------------------------

def build_backend_chain(config) -> List[StorageBackend]:
    """
    根据配置构建后端链（优先级从高到低）
    返回可用的后端列表，SQLite 降级总是最后一个
    """
    from .config import config_manager

    backends: List[StorageBackend] = []

    # 1. Memory API
    api_url = config_manager.get("memory_layer.api_url", "")
    if api_url:
        try:
            lb = None
            try:
                from .load_balancer import get_memory_load_balancer
                lb = get_memory_load_balancer()
            except Exception:
                pass
            strategy = MemoryAPIStrategy(api_url, load_balancer=lb)
            if strategy.is_available():
                backends.append(strategy)
        except Exception:
            pass

    # 2. Qdrant
    qdrant_url = config_manager.get("qdrant.url", "")
    qdrant_collection = config_manager.get("qdrant.collection", "lengxiaobei_memory")
    if qdrant_url:
        try:
            strategy = QdrantStrategy(qdrant_url, qdrant_collection)
            if strategy.is_available():
                backends.append(strategy)
        except Exception:
            pass

    # 3. FAISS
    try:
        index_path = os.path.join(config.memory_dir, "faiss_index.bin")
        strategy = FAISSStrategy(index_path)
        if strategy.is_available():
            backends.append(strategy)
    except Exception:
        pass

    return backends
