"""
混合记忆系统 - Phase 3
基于 SQLite + 向量后端策略链架构

策略模式: MemoryAPI -> Qdrant -> FAISS -> SQLite关键词
"""

import sqlite3
import os
import json
import time
from typing import List, Dict, Optional, Tuple
import hashlib

from .db_pool import ThreadSafeConnectionPool
from .memory_backends import build_backend_chain, StorageBackend, FAISSStrategy
from .performance import measure_performance

# 可选导入
try:
    import numpy as np
except ImportError:
    np = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


class HybridMemory:
    """
    混合记忆系统
    - SQLite 本地持久存储(冷数据)
    - 向量后端策略链: MemoryAPI -> Qdrant -> FAISS
    - SQLite 关键词搜索作为最终降级
    """

    def __init__(self, config):
        self.config = config
        self.db_path = os.path.join(config.memory_dir, "memory.db")
        self.memory_md_path = os.path.join(config.memory_dir, "MEMORY.md")
        self.buffer = []  # 内存缓冲

        # 线程安全连接池
        self._pool = None

        # 初始化嵌入模型
        self.embedding_model = None
        self.embedding_dim = 384

        # 初始化数据库
        self._init_db()
        self._init_memory_index()

        # 初始化嵌入模型
        if SentenceTransformer:
            try:
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            except Exception as e:
                print(f"[HybridMemory] 初始化嵌入模型失败: {e}")
                self.embedding_model = None

        # 构建后端策略链（延迟初始化，不在 __init__ 中发起 HTTP 请求）
        self._backends: List[StorageBackend] = []
        self._backends_initialized = False

        # 兼容旧代码的属性
        self.index = None
        self.id_to_memory = {}
        self.index_path = os.path.join(config.memory_dir, "faiss_index.bin")
        self.memory_api_enabled = False

    @property
    def conn(self):
        """兼容旧代码 — 返回当前线程的连接"""
        if self._pool is None:
            self._pool = ThreadSafeConnectionPool(self.db_path)
        return self._pool.conn

    def _init_db(self):
        """初始化数据库"""
        os.makedirs(self.config.memory_dir, exist_ok=True)
        if self._pool is None:
            self._pool = ThreadSafeConnectionPool(self.db_path)
        conn = self._pool.conn
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,       -- user|feedback|project|reference
                content TEXT NOT NULL,
                role TEXT,                -- user|assistant
                tags TEXT,                -- JSON array
                embedding REAL DEFAULT 0, -- 简单重要性分数
                created_at REAL NOT NULL,
                accessed_at REAL,
                accessed_count INTEGER DEFAULT 0,
                name TEXT,                -- 记忆名称
                description TEXT,         -- 记忆描述
                hash_key TEXT             -- 内容哈希，避免重复
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE,
                started_at REAL NOT NULL,
                ended_at REAL,
                summary TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_hash_key ON memories(hash_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type_created ON memories(type, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_accessed ON memories(accessed_count DESC, created_at DESC)")

        # 检查并添加缺失的列（如果数据库已存在但列缺失）
        self._ensure_columns_exist()

        conn.commit()

    def _init_memory_index(self):
        """初始化MEMORY.md索引文件"""
        if not os.path.exists(self.memory_md_path):
            with open(self.memory_md_path, 'w', encoding='utf-8') as f:
                f.write("# MEMORY.md\n\n")
                f.write("## 记忆索引\n\n")
                f.write("此文件是记忆索引，每个条目指向具体的记忆文件。\n\n")
                f.write("格式：`- [类型] 名称: 描述`\n\n")

    def _ensure_backends(self):
        """延迟初始化后端策略链（避免 __init__ 中发起 HTTP 请求）"""
        if self._backends_initialized:
            return
        self._backends_initialized = True
        try:
            self._backends = build_backend_chain(self.config)
            # 从策略链中找到 FAISS 后端，兼容旧代码的 index 属性
            for b in self._backends:
                if isinstance(b, FAISSStrategy) and b.is_available():
                    self.index = b.index
                    self.id_to_memory = b.id_to_memory
                    break
            if self._backends:
                names = [b.name for b in self._backends if b.is_available()]
                print(f"[HybridMemory] 可用后端: {names}")
        except Exception as e:
            print(f"[HybridMemory] 初始化后端策略链失败: {e}")
    
    def _ensure_columns_exist(self):
        """确保数据库表包含所需的列"""
        try:
            # 检查是否存在name列
            self.conn.execute("SELECT name FROM memories LIMIT 1;")
        except sqlite3.OperationalError:
            # 如果不存在name列，添加它
            try:
                self.conn.execute("ALTER TABLE memories ADD COLUMN name TEXT;")
            except sqlite3.OperationalError:
                pass  # 列可能已存在
        
        try:
            # 检查是否存在description列
            self.conn.execute("SELECT description FROM memories LIMIT 1;")
        except sqlite3.OperationalError:
            # 如果不存在description列，添加它
            try:
                self.conn.execute("ALTER TABLE memories ADD COLUMN description TEXT;")
            except sqlite3.OperationalError:
                pass  # 列可能已存在
        
        try:
            # 检查是否存在hash_key列
            self.conn.execute("SELECT hash_key FROM memories LIMIT 1;")
        except sqlite3.OperationalError:
            # 如果不存在hash_key列，添加它
            try:
                self.conn.execute("ALTER TABLE memories ADD COLUMN hash_key TEXT;")
            except sqlite3.OperationalError:
                pass  # 列可能已存在
        
        self.conn.commit()

    def _generate_hash(self, content: str, mem_type: str) -> str:
        """生成内容哈希以避免重复"""
        hash_input = f"{mem_type}:{content}".encode('utf-8')
        return hashlib.sha256(hash_input).hexdigest()

    @measure_performance
    def store(self, content: str, role: str = "context",
              mem_type: str = "context", tags: List[str] = None,
              name: str = "", description: str = ""):
        """存入记忆到双库"""
        valid_types = ["user", "feedback", "project", "reference", "context"]
        if mem_type not in valid_types:
            mem_type = "context"

        hash_key = self._generate_hash(content, mem_type)

        # 检查是否已存在
        cursor = self.conn.execute("SELECT id FROM memories WHERE hash_key = ?", (hash_key,))
        if cursor.fetchone():
            self.conn.execute(
                "UPDATE memories SET accessed_at = ?, accessed_count = accessed_count + 1 WHERE hash_key = ?",
                (time.time(), hash_key)
            )
            self.conn.commit()
            return

        now = time.time()
        cursor = self.conn.execute("""
            INSERT INTO memories (type, content, role, tags, created_at, accessed_at, accessed_count, name, description, hash_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (mem_type, content, role, json.dumps(tags or []), now, now, 0, name, description, hash_key))
        self.conn.commit()
        mem_id = cursor.lastrowid

        # 通过策略链存储向量
        if self.embedding_model:
            try:
                embedding = self.embedding_model.encode([content])[0]
                self._store_to_backends(mem_id, content, embedding, mem_type, role, tags, name, description, now, hash_key)
            except Exception as e:
                print(f"[HybridMemory] 生成向量嵌入失败: {e}")

        # 更新MEMORY.md索引
        self._update_memory_index(name or f"记忆_{int(now)}", description or content[:100], mem_type)

    def _store_to_backends(self, mem_id, content, embedding, mem_type, role, tags, name, description, now, hash_key):
        """通过策略链存储向量（尝试第一个可用后端）"""
        self._ensure_backends()
        metadata = {
            "content": content, "type": mem_type, "role": role,
            "tags": tags or [], "name": name, "description": description,
            "created_at": now, "hash_key": hash_key, "mem_type": mem_type,
        }
        embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

        for backend in self._backends:
            if backend.is_available():
                try:
                    if backend.store_vector(mem_id, content, embedding_list, metadata):
                        print(f"[HybridMemory] 向量已存储到 {backend.name}: {mem_id}")
                        return
                except Exception as e:
                    print(f"[HybridMemory] {backend.name} 存储失败: {e}")

        # 所有后端都不可用，静默降级（SQLite 已存储原始数据）

    def _update_memory_index(self, name: str, description: str, mem_type: str):
        """更新MEMORY.md索引"""
        # 读取现有内容
        try:
            with open(self.memory_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            content = "# MEMORY.md\n\n## 记忆索引\n\n"
        
        # 检查是否已存在相同的条目
        entry_line = f"- [{mem_type}] {name}: {description}"
        if entry_line not in content:
            # 添加新条目
            lines = content.split('\n')
            # 找到"## 记忆索引"后的第一个空行位置
            idx = -1
            for i, line in enumerate(lines):
                if line.startswith("## 记忆索引"):
                    idx = i
                    break
            
            if idx != -1:
                # 在索引部分后插入新条目
                insert_pos = idx + 1
                while insert_pos < len(lines) and lines[insert_pos].strip() != "":
                    insert_pos += 1
                
                if insert_pos < len(lines):
                    lines.insert(insert_pos, entry_line)
                else:
                    lines.append(entry_line)
            
            # 写回文件
            with open(self.memory_md_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

    @measure_performance
    def search(self, query: str, limit: int = 5, mem_type: Optional[str] = None) -> List[Dict]:
        """按类型和向量相似度搜索记忆"""
        if not query:
            return []

        # 无嵌入模型时直接走关键词搜索
        if not self.embedding_model:
            return self._keyword_search(query, limit, mem_type)

        try:
            query_embedding = self.embedding_model.encode([query])[0]
            query_embedding_list = query_embedding.tolist() if hasattr(query_embedding, 'tolist') else list(query_embedding)

            # 通过策略链搜索
            self._ensure_backends()
            for backend in self._backends:
                if not backend.is_available():
                    continue
                try:
                    results = backend.search_vector(query_embedding_list, limit, mem_type)
                    if results:
                        # FAISS 后端只返回 ID，需要从 SQLite 补全
                        if results and results[0].get("_from_faiss"):
                            results = self._enrich_faiss_results(results, limit, mem_type)
                        else:
                            # 标准化结果格式
                            results = [self._normalize_result(r) for r in results]
                        # 更新访问次数
                        self._update_access_counts(results)
                        print(f"[HybridMemory] 使用 {backend.name} 搜索完成，找到 {len(results)} 个结果")
                        return results
                except Exception as e:
                    print(f"[HybridMemory] {backend.name} 搜索失败: {e}")
                    continue

            # 所有向量后端失败，降级到关键词搜索
            return self._keyword_search(query, limit, mem_type)
        except Exception as e:
            print(f"[HybridMemory] 搜索失败: {e}")
            return self._keyword_search(query, limit, mem_type)

    def _keyword_search(self, query: str, limit: int, mem_type: Optional[str] = None) -> List[Dict]:
        """SQLite 关键词搜索（最终降级）"""
        search_term = f"%{query}%"
        if mem_type:
            sql = "SELECT id, type, content, role, tags, accessed_count, name, description FROM memories WHERE type = ? AND content LIKE ? ORDER BY accessed_count DESC, created_at DESC LIMIT ?"
            cursor = self.conn.execute(sql, (mem_type, search_term, limit))
        else:
            sql = "SELECT id, type, content, role, tags, accessed_count, name, description FROM memories WHERE content LIKE ? ORDER BY accessed_count DESC, created_at DESC LIMIT ?"
            cursor = self.conn.execute(sql, (search_term, limit))
        results = [self._row_to_dict(row) for row in cursor.fetchall()]
        self._update_access_counts(results)
        return results

    def _enrich_faiss_results(self, faiss_results: List[Dict], limit: int, mem_type: Optional[str]) -> List[Dict]:
        """从 SQLite 补全 FAISS 搜索结果"""
        mem_ids = [r["id"] for r in faiss_results if "id" in r]
        if not mem_ids:
            return []
        placeholders = ",".join(["?"] * len(mem_ids))
        sql = f"SELECT id, type, content, role, tags, accessed_count, name, description FROM memories WHERE id IN ({placeholders})"
        params = mem_ids
        if mem_type:
            sql += " AND type = ?"
            params = mem_ids + [mem_type]
        cursor = self.conn.execute(sql, params)
        return [self._row_to_dict(row) for row in cursor.fetchall()][:limit]

    @staticmethod
    def _normalize_result(r: Dict) -> Dict:
        """标准化后端返回的结果格式"""
        return {
            "id": r.get("id", 0),
            "type": r.get("type", "context"),
            "content": r.get("content", ""),
            "role": r.get("role", ""),
            "tags": r.get("tags", []),
            "accessed_count": r.get("accessed_count", 0),
            "name": r.get("name", ""),
            "description": r.get("description", ""),
        }

    @staticmethod
    def _row_to_dict(row) -> Dict:
        """将 SQLite 行转为字典"""
        return {
            "id": row[0], "type": row[1], "content": row[2], "role": row[3],
            "tags": json.loads(row[4]) if row[4] else [],
            "accessed_count": row[5], "name": row[6] or "", "description": row[7] or "",
        }

    def _update_access_counts(self, results: List[Dict]):
        """批量更新访问次数"""
        if not results:
            return
        update_ids = [r["id"] for r in results if "id" in r]
        if not update_ids:
            return
        placeholders = ",".join(["?"] * len(update_ids))
        self.conn.execute(
            f"UPDATE memories SET accessed_at = ?, accessed_count = accessed_count + 1 WHERE id IN ({placeholders})",
            [time.time()] + update_ids
        )
        self.conn.commit()

    def get_memory_by_type(self, mem_type: str, limit: int = 10) -> List[Dict]:
        """根据类型获取记忆"""
        cursor = self.conn.execute("""
            SELECT id, type, content, role, tags, accessed_count, name, description
            FROM memories WHERE type = ?
            ORDER BY accessed_count DESC, created_at DESC LIMIT ?
        """, (mem_type, limit))
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_relevant_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """
        获取与查询相关的关键记忆（类似Claude Code的findRelevantMemories）
        这里简化实现，实际可引入AI模型选择最相关的记忆
        """
        # 先按类型搜索，优先返回user和feedback类型的记忆
        user_memories = self.search(query, limit=max(1, limit//3), mem_type="user")
        feedback_memories = self.search(query, limit=max(1, limit//3), mem_type="feedback")
        project_memories = self.search(query, limit=max(1, limit//3), mem_type="project")
        
        # 合并并确保不超过限制
        all_relevant = user_memories + feedback_memories + project_memories
        return all_relevant[:limit]

    def recall_all(self) -> List[Dict]:
        """读取所有记忆（最新优先）"""
        cursor = self.conn.execute("""
            SELECT id, type, content, role, tags, accessed_count, created_at, name, description
            FROM memories ORDER BY created_at DESC LIMIT 20
        """)
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "type": row[1],
                "content": row[2],
                "role": row[3],
                "tags": json.loads(row[4]) if row[4] else [],
                "accessed_count": row[5],
                "created_at": row[6],
                "name": row[7] or "",
                "description": row[8] or "",
            })
        return results

    def get_memory_index_content(self) -> str:
        """获取MEMORY.md的内容"""
        try:
            with open(self.memory_md_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return ""
    
    def search_similar(self, query: str, limit: int = 5) -> List[Dict]:
        """
        向量相似性搜索 - 返回语义上相似的记忆
        如果向量搜索不可用，则降级到关键词搜索
        """
        return self.search(query, limit=limit)  # search方法已经支持向量相似性搜索

    def optimize(self):
        """优化记忆（清理、压缩等）— 预留接口"""
        pass

    def save(self):
        """保存（目前是即时写入，save 是预留接口）"""
        self.conn.commit()

    def add_thought(self, input_str: str, response: str):
        """添加思考记录到记忆系统
        
        Args:
            input_str: 输入内容
            response: 响应内容
        """
        thought_content = f"用户输入: {input_str}\n系统响应: {response}"
        self.store(
            content=thought_content,
            role="assistant",
            mem_type="project",
            name="思考记录",
            description=f"关于'{input_str[:50]}...'的思考"
        )

    def close(self):
        """关闭连接"""
        if self._pool is not None:
            self._pool.close()
            self._pool = None
