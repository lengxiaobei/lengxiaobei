"""
主动学习模块
============
LLM 驱动的知识提取、模式识别和能力反思。

设计原则：
- 持久化层保留 JSON CRUD（存储结构化知识）
- 智能层全部通过 LLM prompt 实现（模式提取、知识缺口发现、语义检索）
- 不预设策略枚举，让 LLM 根据上下文动态决策
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .llm import chat


# ---------------------------------------------------------------------------
# 知识类型常量（向后兼容旧调用方）
# ---------------------------------------------------------------------------

class KnowledgeType:
    """知识类型 — 向后兼容的字符串常量"""
    FACTS = "facts"
    CONCEPTS = "concepts"
    SKILLS = "skills"
    PATTERNS = "patterns"
    PRINCIPLES = "principles"
    HEURISTICS = "heuristics"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeItem:
    """知识条目"""
    id: str
    content: str
    source: str
    confidence: float          # 0–100
    category: str = "general"  # facts | concepts | patterns | principles | heuristics
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    usage_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "content": self.content, "source": self.source,
            "confidence": self.confidence, "category": self.category,
            "tags": self.tags, "created_at": self.created_at,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeItem":
        return cls(
            id=d["id"], content=d["content"], source=d["source"],
            confidence=d.get("confidence", 50), category=d.get("category", "general"),
            tags=d.get("tags", []), created_at=d.get("created_at", time.time()),
            usage_count=d.get("usage_count", 0),
        )


# ---------------------------------------------------------------------------
# LLM Prompt 模板
# ---------------------------------------------------------------------------

EXTRACT_PATTERNS_PROMPT = """你是一个知识提取引擎。分析以下经验文本，提取可复用的模式和原则。

经验描述：{description}
经验内容：{content}
结果：{outcome}

请以 JSON 数组返回提取的知识条目，每项包含：
- content: 知识内容（一句话概括）
- category: 类型（facts/concepts/patterns/principles/heuristics）
- confidence: 置信度 0-100

只返回 JSON 数组，不要其他文字。"""

DISCOVER_GAPS_PROMPT = """你是一个知识审计引擎。分析当前知识库状态，发现需要补充的知识缺口。

已有知识类别及数量：{knowledge_summary}
近期经验数量：{experience_count}

请以 JSON 数组返回 3-5 个知识缺口，每项包含：
- description: 缺口描述（一句话）
- category: 建议学习的知识类型
- priority: 优先级 0-100

只返回 JSON 数组，不要其他文字。"""

SEMANTIC_RETRIEVAL_PROMPT = """你是一个知识检索引擎。根据查询，从知识库中找出最相关的条目。

查询：{query}

知识库：
{knowledge_list}

请以 JSON 数组返回最相关的知识条目 id（最多 5 个），按相关度降序。只返回 JSON 数组，不要其他文字。
示例：["3", "7", "1"]"""

SELF_REFLECTION_PROMPT = """你是一个元认知引擎。根据最近的经验和知识变化，进行自我反思。

近期经验摘要：{experience_summary}
知识库变化：{knowledge_changes}

请以 JSON 返回反思结果：
{{
  "insights": ["洞察1", "洞察2"],
  "improvements": ["可改进的方向1"],
  "confidence": 0-100
}}

只返回 JSON 对象，不要其他文字。"""


# ---------------------------------------------------------------------------
# ActiveLearner
# ---------------------------------------------------------------------------

class ActiveLearner:
    """LLM 驱动的主动学习系统"""

    def __init__(self, project_root: str):
        self.learning_dir = os.path.join(project_root, "learning")
        os.makedirs(self.learning_dir, exist_ok=True)
        self.knowledge_file = os.path.join(self.learning_dir, "knowledge.json")
        self.experiences_file = os.path.join(self.learning_dir, "experiences.json")

        self.knowledge: Dict[str, KnowledgeItem] = {}
        self.experiences: List[dict] = []
        self._id_counter = 0
        self._load()

    # ---- 持久化 ----

    def _load(self):
        for path, target, cls in [
            (self.knowledge_file, self.knowledge, KnowledgeItem),
            (self.experiences_file, self.experiences, None),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    if cls:
                        for item in data:
                            obj = cls.from_dict(item)
                            target[obj.id] = obj
                            self._id_counter = max(self._id_counter, int(obj.id))
                    else:
                        target.extend(data)
                        for item in data:
                            if item.get("id", "").isdigit():
                                self._id_counter = max(self._id_counter, int(item["id"]))
                except Exception as e:
                    print(f"[ActiveLearner] 加载失败: {path} - {e}")

    def _save(self):
        for path, data in [
            (self.knowledge_file, [v.to_dict() for v in self.knowledge.values()]),
            (self.experiences_file, self.experiences),
        ]:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[ActiveLearner] 保存失败: {path} - {e}")

    def _next_id(self) -> str:
        self._id_counter += 1
        return str(self._id_counter)

    # ---- 知识 CRUD ----

    def add_knowledge(self, content: str, source: str = "manual",
                      confidence: float = 50, category: str = "general",
                      knowledge_type: str = None, tags: List[str] = None) -> KnowledgeItem:
        """添加知识条目。knowledge_type 是 category 的别名，向后兼容旧调用方。"""
        cat = knowledge_type or category
        item = KnowledgeItem(
            id=self._next_id(), content=content, source=source,
            confidence=min(max(confidence, 0), 100), category=cat,
            tags=tags or [],
        )
        self.knowledge[item.id] = item
        self._save()
        return item

    def list_knowledge(self, category: str = None) -> List[KnowledgeItem]:
        result = list(self.knowledge.values())
        if category:
            result = [k for k in result if k.category == category]
        result.sort(key=lambda k: (k.usage_count, k.confidence), reverse=True)
        return result

    # ---- 经验 ----

    def add_experience(self, description: str, content: str, outcome: str,
                       tags: List[str] = None) -> dict:
        exp = {
            "id": self._next_id(), "description": description,
            "content": content, "outcome": outcome,
            "tags": tags or [], "created_at": time.time(),
        }
        self.experiences.append(exp)

        # LLM 驱动的模式提取
        patterns = self._llm_extract_patterns(exp)
        for p in patterns:
            self.add_knowledge(
                content=p["content"], source=f"experience:{exp['id']}",
                confidence=p.get("confidence", 70), category=p.get("category", "patterns"),
                tags=["auto-extracted"],
            )

        self._save()
        return exp

    # ---- LLM 驱动的智能方法 ----

    def _llm_extract_patterns(self, experience: dict) -> List[dict]:
        """用 LLM 从经验中提取可复用模式"""
        prompt = EXTRACT_PATTERNS_PROMPT.format(
            description=experience["description"],
            content=experience["content"][:3000],
            outcome=experience["outcome"],
        )
        try:
            result = chat(prompt, system="你是一个知识提取引擎，只返回 JSON。")
            return json.loads(self._extract_json(result))
        except Exception as e:
            print(f"[ActiveLearner] LLM 模式提取失败: {e}")
            return []

    def discover_gaps(self) -> List[dict]:
        """用 LLM 发现知识缺口"""
        summary = {}
        for k in self.knowledge.values():
            summary[k.category] = summary.get(k.category, 0) + 1
        summary_str = ", ".join(f"{cat}: {cnt}" for cat, cnt in summary.items())

        prompt = DISCOVER_GAPS_PROMPT.format(
            knowledge_summary=summary_str or "无已有知识",
            experience_count=len(self.experiences),
        )
        try:
            result = chat(prompt, system="你是一个知识审计引擎，只返回 JSON。")
            return json.loads(self._extract_json(result))
        except Exception as e:
            print(f"[ActiveLearner] 知识缺口发现失败: {e}")
            return []

    def retrieve(self, query: str, top_k: int = 5) -> List[KnowledgeItem]:
        """用 LLM 做语义知识检索"""
        if not self.knowledge:
            return []

        # 构建知识列表供 LLM 筛选
        items = list(self.knowledge.values())
        knowledge_list = "\n".join(
            f"  [{k.id}] ({k.category}) {k.content[:120]}" for k in items
        )

        prompt = SEMANTIC_RETRIEVAL_PROMPT.format(
            query=query, knowledge_list=knowledge_list[:4000],
        )
        try:
            result = chat(prompt, system="你是一个知识检索引擎，只返回 JSON。")
            ids = json.loads(self._extract_json(result))
            retrieved = []
            for kid in ids:
                if kid in self.knowledge:
                    self.knowledge[kid].usage_count += 1
                    retrieved.append(self.knowledge[kid])
            if retrieved:
                self._save()
            return retrieved[:top_k]
        except Exception as e:
            print(f"[ActiveLearner] 语义检索失败，降级到关键词匹配: {e}")
            return self._fallback_keyword_search(query, top_k)

    def reflect(self) -> dict:
        """LLM 驱动的自我反思"""
        recent = self.experiences[-5:] if self.experiences else []
        exp_summary = "\n".join(
            f"- {e['description']}: {e['outcome'][:100]}" for e in recent
        ) or "无近期经验"

        knowledge_items = list(self.knowledge.values())
        knowledge_items.sort(key=lambda k: k.created_at, reverse=True)
        recent_knowledge = knowledge_items[:10]
        k_changes = "\n".join(
            f"- [{k.category}] {k.content[:100]}" for k in recent_knowledge
        ) or "无知识变化"

        prompt = SELF_REFLECTION_PROMPT.format(
            experience_summary=exp_summary,
            knowledge_changes=k_changes,
        )
        try:
            result = chat(prompt, system="你是一个元认知引擎，只返回 JSON。")
            return json.loads(self._extract_json(result))
        except Exception as e:
            print(f"[ActiveLearner] 反思失败: {e}")
            return {"insights": [], "improvements": [], "confidence": 0}

    # ---- 回退方法 ----

    def _fallback_keyword_search(self, query: str, limit: int) -> List[KnowledgeItem]:
        """LLM 不可用时的关键词回退"""
        keywords = set(query.lower().split())
        scored = []
        for item in self.knowledge.values():
            score = sum(1 for kw in keywords if kw in item.content.lower())
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: (x[0], x[1].confidence), reverse=True)
        return [item for _, item in scored[:limit]]

    def _extract_json(self, text: str) -> str:
        """从 LLM 回复中提取 JSON 部分"""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return text


def create_active_learner(project_root: str) -> ActiveLearner:
    return ActiveLearner(project_root)