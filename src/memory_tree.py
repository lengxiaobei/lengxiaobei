"""
Memory Tree — 四层记忆分层模型
===============================
raw_event → episode → knowledge → profile

每层有自己的 schema、TTL 和提炼策略。低层记忆自动向上提炼为高层知识。

设计参考 OpenHuman 的 Memory Tree 理念，但保持本地轻量：
- raw_event: 原始事件日志（命令、对话、错误），30 天 TTL
- episode:   会话摘要（今天做了什么），90 天 TTL，由 AutoDream 提炼
- knowledge: 稳定知识（架构、偏好、技术结论），永久保留
- profile:   用户/项目画像（潘豪的风格、冷小北的长期目标），永久保留
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .llm import chat


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class MemoryLayer:
    """记忆层定义"""
    name: str
    description: str
    ttl_days: Optional[int]  # None = 永久
    schema_fields: List[str]


LAYERS = {
    "raw_event": MemoryLayer(
        name="raw_event",
        description="原始事件: 一次命令、一段对话、一个错误",
        ttl_days=30,
        schema_fields=["event_type", "source", "content", "context"],
    ),
    "episode": MemoryLayer(
        name="episode",
        description="会话摘要: 一个时间段内做了什么",
        ttl_days=90,
        schema_fields=["period", "summary", "key_decisions", "outcomes"],
    ),
    "knowledge": MemoryLayer(
        name="knowledge",
        description="稳定知识: 项目架构、用户偏好、技术结论",
        ttl_days=None,
        schema_fields=["domain", "content", "confidence", "evidence", "contradictions"],
    ),
    "profile": MemoryLayer(
        name="profile",
        description="画像: 用户风格、长期目标、核心约束",
        ttl_days=None,
        schema_fields=["subject", "traits", "preferences", "goals", "constraints"],
    ),
}


# ---------------------------------------------------------------------------
# LLM Prompt 模板
# ---------------------------------------------------------------------------

RAW_TO_EPISODE_PROMPT = """你是一个会话摘要引擎。将以下原始事件提炼为会话摘要。

原始事件（最近一批）：
{raw_events}

请以 JSON 返回摘要：
{{
  "period": "时间段描述（如 2026-05-21 上午）",
  "summary": "这一时段做了什么（2-3句）",
  "key_decisions": ["决策1", "决策2"],
  "outcomes": ["结果1", "结果2"],
  "tags": ["标签1", "标签2"]
}}

只返回 JSON 对象，不要其他文字。"""

EPISODE_TO_KNOWLEDGE_PROMPT = """你是一个知识提炼引擎。从近期会话摘要中提取稳定知识。

会话摘要：
{episodes}

已有知识：
{existing_knowledge}

请以 JSON 数组返回新发现的知识条目，每项包含：
- domain: 领域（architecture/coding/preference/tooling/lesson）
- content: 知识内容（一句话）
- confidence: 置信度 0-100
- evidence: 支撑该知识的摘要引用
- contradicts: 是否与已有知识冲突（如有，列出冲突的知识内容）

只返回 JSON 数组，不要其他文字。"""

UPDATE_PROFILE_PROMPT = """你是一个用户画像引擎。根据最近的稳定知识更新用户/项目画像。

当前画像：
{current_profile}

新知识：
{new_knowledge}

请以 JSON 返回更新后的画像：
{{
  "subject": "潘豪 / 冷小北",
  "traits": {{"trait_name": "description"}},
  "preferences": ["偏好1", "偏好2"],
  "goals": ["目标1", "目标2"],
  "constraints": ["约束1"],
  "changes": ["本次更新内容1"]
}}

只返回 JSON 对象，不要其他文字。"""


# ---------------------------------------------------------------------------
# MemoryTree
# ---------------------------------------------------------------------------

class MemoryTree:
    """四层记忆树 — 基于现有 hybrid_memory 存储，增加分层提炼能力"""

    def __init__(self, project_root: str, memory_backend=None):
        self.project_root = Path(project_root)
        self.memory_dir = self.project_root / "memory"
        self.memory_dir.mkdir(exist_ok=True)
        self.backend = memory_backend  # HybridMemory 实例

    # ---- 存储 ----

    def log_event(self, event_type: str, content: str,
                  source: str = "system", context: dict = None):
        """记录一条原始事件"""
        data = {
            "event_type": event_type,
            "source": source,
            "content": content,
            "context": json.dumps(context or {}, ensure_ascii=False),
        }
        if self.backend:
            self.backend.store(
                json.dumps(data, ensure_ascii=False),
                mem_type="raw_event",
                role="system",
            )

    def store_episode(self, period: str, summary: str,
                      decisions: List[str] = None, outcomes: List[str] = None,
                      tags: List[str] = None):
        """手动存储一条会话摘要"""
        data = {
            "period": period, "summary": summary,
            "key_decisions": decisions or [], "outcomes": outcomes or [],
            "tags": tags or [],
        }
        if self.backend:
            self.backend.store(
                json.dumps(data, ensure_ascii=False),
                mem_type="episode",
                role="system",
            )

    def store_knowledge(self, domain: str, content: str, confidence: float = 50,
                        evidence: str = ""):
        """存储一条稳定知识"""
        data = {
            "domain": domain, "content": content,
            "confidence": confidence, "evidence": evidence,
            "contradictions": "",
        }
        if self.backend:
            self.backend.store(
                json.dumps(data, ensure_ascii=False),
                mem_type="knowledge",
                role="system",
            )

    # ---- 提炼 ----

    def refine_raw_to_episode(self) -> Optional[dict]:
        """LLM 驱动的 raw_event → episode 提炼"""
        raw = self.get_layer("raw_event", limit=30)
        if not raw:
            return None

        events_text = "\n".join(
            f"[{r.get('role', '?')}] {r['content'][:300]}" for r in raw
        )

        prompt = RAW_TO_EPISODE_PROMPT.format(raw_events=events_text[:4000])
        try:
            result = chat(prompt, system="你是一个会话摘要引擎，只返回 JSON。")
            data = json.loads(self._extract_json(result))
            self.store_episode(
                period=data.get("period", ""),
                summary=data.get("summary", ""),
                decisions=data.get("key_decisions", []),
                outcomes=data.get("outcomes", []),
                tags=data.get("tags", []),
            )
            return data
        except Exception as e:
            print(f"[MemoryTree] raw→episode 提炼失败: {e}")
            return None

    def refine_episode_to_knowledge(self) -> List[dict]:
        """LLM 驱动的 episode → knowledge 提炼"""
        episodes = self.get_layer("episode", limit=10)
        if not episodes:
            return []

        eps_text = "\n".join(
            r['content'][:400] for r in episodes
        )
        existing = self.get_layer("knowledge", limit=20)
        existing_text = "\n".join(r['content'][:200] for r in existing) or "无已有知识"

        prompt = EPISODE_TO_KNOWLEDGE_PROMPT.format(
            episodes=eps_text[:3000],
            existing_knowledge=existing_text[:2000],
        )
        try:
            result = chat(prompt, system="你是一个知识提炼引擎，只返回 JSON。")
            items = json.loads(self._extract_json(result))
            new_count = 0
            for item in items:
                # 去重检查
                if existing and any(item.get("content", "")[:60] in e['content'] for e in existing):
                    continue
                self.store_knowledge(
                    domain=item.get("domain", "general"),
                    content=item.get("content", ""),
                    confidence=item.get("confidence", 50),
                    evidence=item.get("evidence", ""),
                )
                new_count += 1
            return items
        except Exception as e:
            print(f"[MemoryTree] episode→knowledge 提炼失败: {e}")
            return []

    def refine_knowledge_to_profile(self, profile_subject: str = "冷小北") -> Optional[dict]:
        """LLM 驱动的 knowledge → profile 提炼"""
        current = self.get_layer("profile", limit=5)
        profile_text = "\n".join(r['content'][:300] for r in current) or "{}"

        new_knowledge = self.get_layer("knowledge", limit=10)
        knowledge_text = "\n".join(
            f"[{r.get('tags', '')}] {r['content'][:200]}" for r in new_knowledge
        ) or "无新知识"

        prompt = UPDATE_PROFILE_PROMPT.format(
            current_profile=profile_text,
            new_knowledge=knowledge_text[:3000],
        )
        try:
            result = chat(prompt, system="你是一个用户画像引擎，只返回 JSON。")
            data = json.loads(self._extract_json(result))
            if self.backend:
                self.backend.store(
                    json.dumps(data, ensure_ascii=False),
                    mem_type="profile", role="system",
                    name=profile_subject,
                )
            return data
        except Exception as e:
            print(f"[MemoryTree] knowledge→profile 提炼失败: {e}")
            return None

    # ---- 查询 ----

    def get_layer(self, layer: str, limit: int = 20) -> List[dict]:
        """获取某一层的记忆"""
        if self.backend and hasattr(self.backend, "scan_layer"):
            return self.backend.scan_layer(layer, limit=limit)
        return []

    def search_all(self, query: str, limit: int = 10) -> List[dict]:
        """跨层关键词搜索"""
        if self.backend and query:
            return self.backend.search(query, limit=limit)
        return []

    def get_profile(self) -> Optional[dict]:
        """获取最新画像"""
        profiles = self.get_layer("profile", limit=1)
        if profiles:
            try:
                return json.loads(profiles[0]["content"])
            except json.JSONDecodeError:
                return {"raw": profiles[0]["content"]}
        return None

    def stats(self) -> dict:
        """各层记忆统计"""
        counts = {}
        for layer in LAYERS:
            items = self.get_layer(layer, limit=1000)
            counts[layer] = len(items)
        return {"layers": counts, "total": sum(counts.values())}

    # ---- 工具 ----

    def _extract_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return text
