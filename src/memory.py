"""
记忆系统 — Phase 2
基于 SQLite + FAISS 向量数据库
"""

import sqlite3
import os
import json
import time
from typing import List, Dict, Optional, Tuple
import hashlib

from .db_pool import ThreadSafeConnectionPool

try:
    import numpy as np
except ImportError:
    np = None

faiss = None
SentenceTransformer = None

# 尝试导入可选依赖
try:
    import faiss
except ImportError:
    pass

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    pass


class Memory:
    """
    记忆系统
    - SQLite 持久存储
    - 关键词 + 简单向量匹配
    - Claude Code 风格的四层记忆：user/feedback/project/reference
    """

    def __init__(self, config):
        self.config = config
        self.db_path = os.path.join(config.memory_dir, "memory.db")
        self.memory_md_path = os.path.join(config.memory_dir, "MEMORY.md")
        self.buffer = []  # 内存缓冲
        self._pool = None  # 线程安全连接池
        
        # 初始化嵌入模型和FAISS索引
        self.embedding_model = None
        self.embedding_dim = 384  # all-MiniLM-L6-v2 的维度
        self.index_path = os.path.join(config.memory_dir, "faiss_index.bin")
        self.index = None
        self.id_to_memory = {}  # 映射FAISS ID到记忆ID
        
        # 尝试初始化嵌入模型和FAISS索引
        if SentenceTransformer and faiss:
            try:
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                self.index = self._init_faiss_index()
            except Exception as e:
                print(f"[Memory] 初始化嵌入模型和FAISS索引失败: {e}")
                self.embedding_model = None
                self.index = None
        
        self._init_db()
        self._init_memory_index()
        
        # 只有在索引初始化成功时才重建索引
        if self.index:
            self._rebuild_index()  # 从数据库重建FAISS索引

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

        # 检查并添加缺失的列
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

    def _init_faiss_index(self):
        """初始化FAISS索引"""
        if not faiss:
            print("[Memory] FAISS库不可用，跳过索引初始化")
            return None
        
        if os.path.exists(self.index_path):
            # 加载现有索引
            try:
                index = faiss.read_index(self.index_path)
                print(f"[Memory] 加载现有FAISS索引，维度: {index.d}")
                return index
            except Exception as e:
                print(f"[Memory] 加载FAISS索引失败: {e}")
        
        # 创建新索引
        try:
            index = faiss.IndexFlatL2(self.embedding_dim)
            print(f"[Memory] 创建新FAISS索引，维度: {self.embedding_dim}")
            return index
        except Exception as e:
            print(f"[Memory] 创建FAISS索引失败: {e}")
            return None
    
    def _rebuild_index(self):
        """从数据库重建FAISS索引"""
        print("[Memory] 重建FAISS索引...")
        cursor = self.conn.execute("SELECT id, content FROM memories")
        memories = cursor.fetchall()
        
        if not memories:
            print("[Memory] 数据库中无记忆，跳过索引重建")
            return
        
        # 清空现有索引
        self.index.reset()
        self.id_to_memory = {}
        
        # 批量处理嵌入
        contents = [mem[1] for mem in memories]
        embeddings = self.embedding_model.encode(contents, batch_size=32, show_progress_bar=True)
        
        # 添加到索引
        for i, (mem_id, content) in enumerate(memories):
            self.index.add(np.array([embeddings[i]]))
            self.id_to_memory[i] = mem_id
        
        # 保存索引
        faiss.write_index(self.index, self.index_path)
        print(f"[Memory] 索引重建完成，添加了 {len(memories)} 个记忆")
    
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

    def store(self, content: str, role: str = "context",
              mem_type: str = "context", tags: List[str] = None, 
              name: str = "", description: str = ""):
        """
        存入记忆

        Args:
            content: 记忆内容
            role: 角色 (user|assistant|system)
            mem_type: 记忆类型 (user|feedback|project|reference)
            tags: 标签列表
            name: 记忆名称
            description: 记忆描述
        """
        # 确保类型符合Claude Code规范
        valid_types = ["user", "feedback", "project", "reference", "context"]
        if mem_type not in valid_types:
            mem_type = "context"  # 默认类型
            
        # 生成哈希避免重复
        hash_key = self._generate_hash(content, mem_type)
        
        # 检查是否已存在相同内容的记忆
        cursor = self.conn.execute("SELECT id FROM memories WHERE hash_key = ?", (hash_key,))
        if cursor.fetchone():
            # 如果已存在，只是增加访问计数
            self.conn.execute(
                "UPDATE memories SET accessed_at = ?, accessed_count = accessed_count + 1 WHERE hash_key = ?",
                (time.time(), hash_key)
            )
            self.conn.commit()
            return  # 不重复存储
        
        now = time.time()
        cursor = self.conn.execute("""
            INSERT INTO memories (type, content, role, tags, created_at, accessed_at, accessed_count, name, description, hash_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (mem_type, content, role, json.dumps(tags or []), now, now, 0, name, description, hash_key))
        self.conn.commit()
        mem_id = cursor.lastrowid
        
        # 尝试生成向量嵌入并更新FAISS索引
        if self.embedding_model and self.index:
            try:
                embedding = self.embedding_model.encode([content])[0]
                self.index.add(np.array([embedding]))
                self.id_to_memory[len(self.id_to_memory)] = mem_id
                
                # 保存索引
                faiss.write_index(self.index, self.index_path)
            except Exception as e:
                print(f"[Memory] 更新FAISS索引失败: {e}")
        
        # 更新MEMORY.md索引
        self._update_memory_index(name or f"记忆_{int(now)}", description or content[:100], mem_type)

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

    def search(self, query: str, limit: int = 5, mem_type: Optional[str] = None) -> List[Dict]:
        """
        按类型和向量相似度搜索记忆

        Args:
            query: 搜索查询
            limit: 限制返回数量
            mem_type: 记忆类型过滤 (user|feedback|project|reference)
        """
        if not query:
            return []

        # 如果嵌入模型或索引不可用，使用简单的数据库查询
        if not self.embedding_model or not self.index:
            # 简单的关键词搜索
            search_term = f"%{query}%"
            if mem_type:
                query_sql = f"SELECT id, type, content, role, tags, accessed_count, name, description FROM memories WHERE type = ? AND content LIKE ? ORDER BY accessed_count DESC, created_at DESC LIMIT ?"
                cursor = self.conn.execute(query_sql, (mem_type, search_term, limit))
            else:
                query_sql = f"SELECT id, type, content, role, tags, accessed_count, name, description FROM memories WHERE content LIKE ? ORDER BY accessed_count DESC, created_at DESC LIMIT ?"
                cursor = self.conn.execute(query_sql, (search_term, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0], 
                    "type": row[1],
                    "content": row[2], 
                    "role": row[3],
                    "tags": json.loads(row[4]) if row[4] else [],
                    "accessed_count": row[5],
                    "name": row[6] or "",
                    "description": row[7] or ""
                })
            
            # 更新访问次数
            for r in results:
                self.conn.execute(
                    "UPDATE memories SET accessed_at = ?, accessed_count = accessed_count + 1 WHERE id = ?",
                    (time.time(), r["id"])
                )
            self.conn.commit()
            
            return results

        # 生成查询向量
        try:
            query_embedding = self.embedding_model.encode([query])[0]
            
            # 在FAISS索引中搜索
            distances, indices = self.index.search(np.array([query_embedding]), limit * 2)  # 多返回一些结果，然后过滤
            
            # 获取记忆ID
            mem_ids = []
            for i in range(len(indices[0])):
                idx = indices[0][i]
                if idx != -1:  # -1表示无结果
                    mem_id = self.id_to_memory.get(idx)
                    if mem_id:
                        mem_ids.append(mem_id)
            
            if not mem_ids:
                return []
            
            # 从数据库中获取详细信息
            placeholders = ",".join(["?"] * len(mem_ids))
            query = f"SELECT id, type, content, role, tags, accessed_count, name, description FROM memories WHERE id IN ({placeholders})"
            cursor = self.conn.execute(query, mem_ids)
            
            results = []
            for row in cursor.fetchall():
                # 如果指定了类型，则过滤
                if mem_type and row[1] != mem_type:
                    continue
                
                results.append({
                    "id": row[0], 
                    "type": row[1],
                    "content": row[2], 
                    "role": row[3],
                    "tags": json.loads(row[4]) if row[4] else [],
                    "accessed_count": row[5],
                    "name": row[6] or "",
                    "description": row[7] or ""
                })

            # 限制结果数量
            results = results[:limit]

            # 更新访问次数
            for r in results:
                self.conn.execute(
                    "UPDATE memories SET accessed_at = ?, accessed_count = accessed_count + 1 WHERE id = ?",
                    (time.time(), r["id"])
                )
            self.conn.commit()

            return results
        except Exception as e:
            print(f"[Memory] 搜索失败: {e}")
            # 失败时使用简单的数据库查询
            search_term = f"%{query}%"
            if mem_type:
                query_sql = f"SELECT id, type, content, role, tags, accessed_count, name, description FROM memories WHERE type = ? AND content LIKE ? ORDER BY accessed_count DESC, created_at DESC LIMIT ?"
                cursor = self.conn.execute(query_sql, (mem_type, search_term, limit))
            else:
                query_sql = f"SELECT id, type, content, role, tags, accessed_count, name, description FROM memories WHERE content LIKE ? ORDER BY accessed_count DESC, created_at DESC LIMIT ?"
                cursor = self.conn.execute(query_sql, (search_term, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0], 
                    "type": row[1],
                    "content": row[2], 
                    "role": row[3],
                    "tags": json.loads(row[4]) if row[4] else [],
                    "accessed_count": row[5],
                    "name": row[6] or "",
                    "description": row[7] or ""
                })
            
            return results

    def get_memory_by_type(self, mem_type: str, limit: int = 10) -> List[Dict]:
        """根据类型获取记忆"""
        cursor = self.conn.execute("""
            SELECT id, type, content, role, tags, accessed_count, name, description
            FROM memories
            WHERE type = ?
            ORDER BY accessed_count DESC, created_at DESC
            LIMIT ?
        """, (mem_type, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0], 
                "type": row[1],
                "content": row[2], 
                "role": row[3],
                "tags": json.loads(row[4]) if row[4] else [],
                "accessed_count": row[5],
                "name": row[6] or "",
                "description": row[7] or ""
            })
        return results

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
            SELECT type, content, role, tags, accessed_count, created_at, name, description
            FROM memories
            ORDER BY created_at DESC
            LIMIT 20
        """)
        results = []
        for row in cursor.fetchall():
            results.append({
                "type": row[0], 
                "content": row[1],
                "role": row[2], 
                "tags": json.loads(row[3]) if row[3] else [],
                "accessed_count": row[4], 
                "created_at": row[5],
                "name": row[6] or "",
                "description": row[7] or ""
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

    def save(self):
        """保存（目前是即时写入，save 是预留接口）"""
        self.conn.commit()

    def close(self):
        """关闭连接"""
        if self._pool is not None:
            self._pool.close()
            self._pool = None
