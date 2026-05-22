"""
知识策展系统 (Knowledge Curator)
================================

灵感来源: hermes-agent 的 Curator 系统

设计原则:
- LLM 决策: 分类、相似度判断、合并策略全部由 LLM 决定，不硬编码规则
- 代码只提供工具和数据管理，LLM 自己决定怎么做
- 永不删除，只归档（archived 状态，始终可恢复）
- 基于使用率自动管理生命周期（纯确定性逻辑，不需 LLM）
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class PatternState(Enum):
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"
    PINNED = "pinned"


@dataclass
class Pattern:
    """可复用的知识模式 — 纯数据模型，无决策逻辑"""
    id: str
    title: str
    description: str
    content: str
    state: PatternState = PatternState.ACTIVE
    confidence: float = 0.5
    usage_count: int = 0
    last_used_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    source_ids: List[str] = field(default_factory=list)
    merged_from: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    category: str = ""
    success_rate: float = 0.0
    total_applications: int = 0
    successful_applications: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "content": self.content, "state": self.state.value,
            "confidence": self.confidence, "usage_count": self.usage_count,
            "last_used_at": self.last_used_at, "created_at": self.created_at,
            "updated_at": self.updated_at, "source_ids": self.source_ids,
            "merged_from": self.merged_from, "tags": self.tags,
            "category": self.category, "success_rate": self.success_rate,
            "total_applications": self.total_applications,
            "successful_applications": self.successful_applications,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pattern":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            content=data.get("content", ""),
            state=PatternState(data.get("state", "active")),
            confidence=data.get("confidence", 0.5),
            usage_count=data.get("usage_count", 0),
            last_used_at=data.get("last_used_at"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            source_ids=data.get("source_ids", []),
            merged_from=data.get("merged_from", []),
            tags=data.get("tags", []),
            category=data.get("category", ""),
            success_rate=data.get("success_rate", 0.0),
            total_applications=data.get("total_applications", 0),
            successful_applications=data.get("successful_applications", 0),
        )

    def summary(self) -> str:
        return (
            f"[{self.id}] {self.title} | state={self.state.value} "
            f"| confidence={self.confidence:.2f} | uses={self.usage_count} "
            f"| tags={', '.join(self.tags)} | category={self.category}\n"
            f"  content: {self.content[:150]}..."
        )


class KnowledgeCurator:
    """LLM 驱动的知识策展系统"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.curator_dir = self.project_root / "curator"
        self.curator_dir.mkdir(exist_ok=True)

        self.patterns_file = self.curator_dir / "patterns.json"
        self.state_file = self.curator_dir / "curator_state.json"
        self.reports_dir = self.curator_dir / "reports"
        self.reports_dir.mkdir(exist_ok=True)

        self.prompt_file = self.curator_dir / "CURATOR.md"

        self.patterns: Dict[str, Pattern] = {}
        self._pattern_id_counter = 0
        self.state = self._load_state()
        self._load_patterns()

        self.stale_after_days = 14
        self.archive_after_days = 60

    # =========================================================================
    # 状态持久化
    # =========================================================================

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"last_run_at": None, "enabled": True, "paused": False}

    def _save_state(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def _load_patterns(self):
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, "r", encoding="utf-8") as f:
                    for d in json.load(f):
                        p = Pattern.from_dict(d)
                        self.patterns[p.id] = p
                        try:
                            pid = int(p.id)
                            if pid > self._pattern_id_counter:
                                self._pattern_id_counter = pid
                        except ValueError:
                            pass
            except Exception as e:
                print(f"[KnowledgeCurator] 加载 patterns 失败: {e}")

    def _save_patterns(self):
        with open(self.patterns_file, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in self.patterns.values()], f, indent=2, ensure_ascii=False)

    def _next_id(self) -> str:
        self._pattern_id_counter += 1
        return str(self._pattern_id_counter)

    # =========================================================================
    # 工具方法 — 供 LLM 通过结构化输出来"调用"
    # =========================================================================

    def create_pattern(self, title: str, content: str, category: str = "",
                       tags: List[str] = None, confidence: float = 0.6) -> Pattern:
        """创建一个新模式"""
        p = Pattern(
            id=self._next_id(),
            title=title,
            description=f"LLM 策展创建",
            content=content,
            category=category,
            tags=tags or [],
            confidence=confidence,
        )
        self.patterns[p.id] = p
        self._save_patterns()
        print(f"   📝 创建: {p.title}")
        return p

    def merge_patterns(self, source_ids: List[str], umbrella_title: str,
                       umbrella_content: str, reason: str = "") -> Optional[Pattern]:
        """将多个模式合并为一个伞形模式"""
        sources = [self.patterns[sid] for sid in source_ids if sid in self.patterns]
        if not sources:
            return None

        all_tags = list(set(tag for p in sources for tag in p.tags))
        all_source_ids = list(set(sid for p in sources for sid in p.source_ids))

        umbrella = Pattern(
            id=self._next_id(),
            title=umbrella_title,
            description=f"伞形模式: 合并了 {len(sources)} 个模式 ({reason})",
            content=umbrella_content,
            category=sources[0].category,
            tags=all_tags,
            confidence=sum(p.confidence for p in sources) / max(len(sources), 1),
            merged_from=[p.id for p in sources],
            source_ids=all_source_ids,
            total_applications=sum(p.total_applications for p in sources),
            successful_applications=sum(p.successful_applications for p in sources),
            success_rate=sum(p.successful_applications for p in sources) / max(sum(p.total_applications for p in sources), 1),
        )

        for p in sources:
            p.state = PatternState.ARCHIVED

        self.patterns[umbrella.id] = umbrella
        self._save_patterns()
        print(f"   ☂️  伞形合并: {', '.join(p.title for p in sources)} → {umbrella_title}")
        return umbrella

    def archive_pattern(self, pattern_id: str, reason: str = "") -> bool:
        """归档一个模式（不删除）"""
        p = self.patterns.get(pattern_id)
        if not p:
            return False
        p.state = PatternState.ARCHIVED
        self._save_patterns()
        print(f"   📦 归档: {p.title} ({reason})")
        return True

    def append_to_pattern(self, pattern_id: str, content_section: str) -> bool:
        """向已有模式追加内容"""
        p = self.patterns.get(pattern_id)
        if not p:
            return False
        p.content += f"\n\n---\n{content_section}"
        p.updated_at = time.time()
        self._save_patterns()
        print(f"   📎 追加到: {p.title}")
        return True

    def update_pattern_tags(self, pattern_id: str, tags: List[str], category: str = "") -> bool:
        """更新模式的标签和分类"""
        p = self.patterns.get(pattern_id)
        if not p:
            return False
        p.tags = tags
        if category:
            p.category = category
        p.updated_at = time.time()
        self._save_patterns()
        return True

    def pin_pattern(self, pattern_id: str):
        p = self.patterns.get(pattern_id)
        if p:
            p.state = PatternState.PINNED
            self._save_patterns()

    def unpin_pattern(self, pattern_id: str):
        p = self.patterns.get(pattern_id)
        if p and p.state == PatternState.PINNED:
            p.state = PatternState.ACTIVE
            self._save_patterns()

    # =========================================================================
    # 自动状态迁移 — 纯确定性逻辑，不需要 LLM
    # =========================================================================

    def _apply_automatic_transitions(self) -> Dict[str, int]:
        now = time.time()
        counts = {"to_stale": 0, "to_archived": 0, "reactivated": 0}
        for p in self.patterns.values():
            if p.state == PatternState.PINNED:
                continue
            if p.last_used_at is None:
                p.last_used_at = p.created_at
            days = (now - p.last_used_at) / 86400
            if p.state == PatternState.ACTIVE:
                if days > self.archive_after_days:
                    p.state = PatternState.ARCHIVED
                    counts["to_archived"] += 1
                elif days > self.stale_after_days:
                    p.state = PatternState.STALE
                    counts["to_stale"] += 1
            elif p.state == PatternState.STALE:
                if days > self.archive_after_days:
                    p.state = PatternState.ARCHIVED
                    counts["to_archived"] += 1
                elif days <= self.stale_after_days:
                    p.state = PatternState.ACTIVE
                    counts["reactivated"] += 1
            elif p.state == PatternState.ARCHIVED:
                if days <= self.stale_after_days:
                    p.state = PatternState.ACTIVE
                    counts["reactivated"] += 1
        self._save_patterns()
        return counts

    # =========================================================================
    # LLM 驱动的策展流程
    # =========================================================================

    def is_due(self, min_interval_hours: int = 168) -> bool:
        if not self.state.get("enabled", True):
            return False
        if self.state.get("paused", False):
            return False
        last_run = self.state.get("last_run_at")
        if last_run is None:
            self.state["last_run_at"] = datetime.now().isoformat()
            self._save_state()
            return False
        return (datetime.now() - datetime.fromisoformat(last_run)).total_seconds() >= min_interval_hours * 3600

    def run_curation(self, dry_run: bool = False) -> Dict[str, Any]:
        """执行一次完整的策展流程"""
        print(f"\n{'='*60}")
        print(f"🧠 Knowledge Curator - 知识策展")
        print(f"{'='*60}")

        result = {
            "timestamp": datetime.now().isoformat(),
            "dry_run": dry_run,
            "transitioned": {},
            "llm_actions": {},
        }

        # 阶段 1: 自动状态迁移（确定性，不需要 LLM）
        print("\n📋 阶段 1: 自动状态迁移...")
        if not dry_run:
            result["transitioned"] = self._apply_automatic_transitions()
            print(f"   stale: {result['transitioned']['to_stale']}, "
                  f"archived: {result['transitioned']['to_archived']}, "
                  f"reactivated: {result['transitioned']['reactivated']}")

        # 阶段 2: 从进化历史提取新模式（LLM 驱动）
        print("\n🔍 阶段 2: LLM 提取进化经验...")
        if not dry_run:
            new_count = self._extract_with_llm()
            result["llm_actions"]["new_patterns"] = new_count

        # 阶段 3: LLM 驱动的伞形合并
        print("\n☂️  阶段 3: LLM 驱动的伞形合并...")
        if not dry_run:
            consolidated = self._consolidate_with_llm()
            result["llm_actions"]["consolidated"] = consolidated

        # 阶段 4: 同步到 ActiveLearner
        print("\n🔄 阶段 4: 同步到 ActiveLearner...")
        if not dry_run:
            self._sync_to_active_learner()

        # 生成报告
        report_path = self._generate_report(result)

        self.state["last_run_at"] = datetime.now().isoformat()
        self._save_state()

        print(f"\n✅ 策展完成 → {report_path}")
        return result

    # =========================================================================
    # LLM 调用 — 核心：给 LLM 目标和数据，让它自己决策
    # =========================================================================

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM，返回响应文本"""
        try:
            from . import llm
            return llm.chat(prompt=user_prompt, system=system_prompt)
        except Exception as e:
            print(f"   ⚠️  LLM 调用失败: {e}")
            return ""

    def _load_curator_prompt(self) -> str:
        """加载 CURATOR.md 作为 system prompt"""
        if self.prompt_file.exists():
            return self.prompt_file.read_text(encoding="utf-8")
        return "你是知识策展人，负责审查和整理知识模式。"

    def _extract_with_llm(self) -> int:
        """让 LLM 从进化历史中提取可复用的知识模式"""
        evo_path = self.project_root / "evolution_history.json"
        if not evo_path.exists():
            print("   ⏭️  无进化历史文件")
            return 0

        try:
            history = json.loads(evo_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"   ✗ 读取失败: {e}")
            return 0

        if not isinstance(history, list):
            history = [history] if isinstance(history, dict) else []

        recent = history[-5:]  # 只处理最近5条，避免 prompt 过长
        if not recent:
            return 0

        existing_ids = set()
        for p in self.patterns.values():
            existing_ids.update(p.source_ids)
        new_records = [r for r in recent if str(r.get("id", "")) not in existing_ids]
        if not new_records:
            print("   ⏭️  无新记录")
            return 0

        user_prompt = f"""请从以下进化历史记录中提取可复用的知识模式。

已有模式ID（不要重复提取）: {list(existing_ids)}

进化历史:
{json.dumps(new_records, indent=2, ensure_ascii=False)[:4000]}

请分析这些记录，提取有复用价值的知识模式。对每个模式，输出以下信息:
- title: 简洁的标题（20字以内）
- content: 具体内容，表达"怎么做"（how-to），而非"发生了什么"（what happened）
- category: 领域分类（performance/security/architecture/testing/code_quality/debugging/llm_usage/general）
- tags: 1-3个标签
- confidence: 0-1之间的置信度

用 JSON 数组格式输出:
```json
[
  {{"title": "...", "content": "...", "category": "...", "tags": [...], "confidence": 0.8}},
  ...
]
```

如果某条记录没有可复用的知识，可以跳过它。
不要提取已经在已有模式ID列表中的记录。"""

        response = self._call_llm(self._load_curator_prompt(), user_prompt)
        if not response:
            print("   ⚠️  LLM 无响应")
            return 0

        actions = self._parse_llm_json_actions(response, "new")
        count = 0
        for action in actions:
            self.create_pattern(
                title=action.get("title", ""),
                content=action.get("content", ""),
                category=action.get("category", "general"),
                tags=action.get("tags", []),
                confidence=action.get("confidence", 0.6),
            )
            count += 1
        print(f"   ✓ LLM 提取了 {count} 个新模式")
        return count

    def _consolidate_with_llm(self) -> int:
        """让 LLM 审查所有活跃模式，决定合并和归档策略"""
        active = [p for p in self.patterns.values() if p.state in (PatternState.ACTIVE, PatternState.STALE)]
        if len(active) < 2:
            print("   ⏭️  活跃模式不足2个，无需合并")
            return 0

        candidates = "\n\n".join(p.summary() for p in active)
        user_prompt = f"""以下是当前所有活跃(active/stale)的知识模式:

{candidates[:6000]}

请作为策展人审查这些模式，执行伞形合并。你的任务是:
1. 识别共享领域关键词的模式簇
2. 对每个簇，判断是否应该合并
3. 决定合并策略：合并进已有宽泛条目 / 创建新伞形 / 子内容

输出你的决策为 JSON 数组。支持的操作:
- merge: 将多个来源合并成一个新伞形
- archive: 归档不再有价值的模式
- append: 向已有模式追加内容
- retag: 重新标记标签和分类

```json
[
  {{"action": "merge", "source_ids": ["1","2"], "umbrella_title": "性能优化总则", "umbrella_content": "合并后的内容...", "reason": "都是关于性能优化"}},
  {{"action": "archive", "pattern_id": "3", "reason": "过时且无复用价值"}},
  {{"action": "append", "pattern_id": "4", "content_section": "补充内容..."}},
  {{"action": "retag", "pattern_id": "5", "tags": ["新标签"], "category": "新分类"}},
  ...
]
```

注意:
- 不要合并来源id列表中没有的模式
- 如果无需操作，返回空数组 []
- umbrealla_content 要综合各来源的要点，不是简单拼接"""

        response = self._call_llm(self._load_curator_prompt(), user_prompt)
        if not response:
            print("   ⚠️  LLM 无响应")
            return 0

        actions = self._parse_llm_json_actions(response, "consolidate")
        consolidated = 0
        for action in actions:
            action_type = action.get("action", "")
            try:
                if action_type == "merge":
                    self.merge_patterns(
                        source_ids=action.get("source_ids", []),
                        umbrella_title=action.get("umbrella_title", "合并模式"),
                        umbrella_content=action.get("umbrella_content", ""),
                        reason=action.get("reason", ""),
                    )
                    consolidated += 1
                elif action_type == "archive":
                    self.archive_pattern(
                        action.get("pattern_id", ""),
                        action.get("reason", ""),
                    )
                elif action_type == "append":
                    self.append_to_pattern(
                        action.get("pattern_id", ""),
                        action.get("content_section", ""),
                    )
                elif action_type == "retag":
                    self.update_pattern_tags(
                        action.get("pattern_id", ""),
                        action.get("tags", []),
                        action.get("category", ""),
                    )
            except Exception as e:
                print(f"   ⚠️  执行操作失败: {action_type} - {e}")

        print(f"   ✓ LLM 策展完成: {consolidated} 次合并")
        return consolidated

    def _parse_llm_json_actions(self, response: str, context: str) -> List[Dict]:
        """从 LLM 响应中提取 JSON 操作数组"""
        import re
        # 尝试匹配 ```json ... ``` 代码块
        m = re.search(r'```json\s*\n(.*?)\n```', response, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # 尝试匹配裸 JSON 数组
        m = re.search(r'\[\s*\{.*?\}\s*\]', response, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        print(f"   ⚠️  无法解析 {context} 的 LLM 响应 JSON")
        return []

    # =========================================================================
    # 同步 & 报告
    # =========================================================================

    def _sync_to_active_learner(self):
        try:
            from .active_learner import ActiveLearner, KnowledgeType
        except ImportError:
            return

        try:
            learner = ActiveLearner(str(self.project_root))
        except Exception:
            return

        existing = {k.content for k in learner.knowledge.values()}
        count = 0
        for p in self.patterns.values():
            if p.state != PatternState.ACTIVE:
                continue
            if p.content in existing:
                continue
            learner.add_knowledge(
                knowledge_type=KnowledgeType.PATTERNS,
                content=p.content[:500],
                source=f"curator/{p.id}",
                confidence=p.confidence * 100,
                tags=p.tags,
            )
            existing.add(p.content)
            count += 1
        if count:
            print(f"   ✓ 同步 {count} 个模式到 ActiveLearner")

    def _generate_report(self, result: Dict[str, Any]) -> str:
        now = datetime.now()
        report_path = self.reports_dir / f"report_{now.strftime('%Y%m%d_%H%M%S')}.json"
        active = sum(1 for p in self.patterns.values() if p.state == PatternState.ACTIVE)
        total = len(self.patterns)
        report = {
            **result,
            "overview": {
                "total": total,
                "active": active,
                "stale": sum(1 for p in self.patterns.values() if p.state == PatternState.STALE),
                "archived": sum(1 for p in self.patterns.values() if p.state == PatternState.ARCHIVED),
                "pinned": sum(1 for p in self.patterns.values() if p.state == PatternState.PINNED),
            },
            "health_score": (active / max(total, 1)) * 100,
            "top_patterns": sorted(
                [p.to_dict() for p in self.patterns.values() if p.state == PatternState.ACTIVE],
                key=lambda x: (x.get("usage_count", 0), x.get("confidence", 0)),
                reverse=True,
            )[:10],
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(report_path)

    # =========================================================================
    # 运行时查询
    # =========================================================================

    def record_pattern_usage(self, pattern_id: str, success: bool = True):
        p = self.patterns.get(pattern_id)
        if not p:
            return
        p.usage_count += 1
        p.last_used_at = time.time()
        p.total_applications += 1
        if success:
            p.successful_applications += 1
        p.success_rate = p.successful_applications / max(p.total_applications, 1)
        p.confidence = min(1.0, p.confidence + 0.02 if success else p.confidence - 0.01)
        if p.state in (PatternState.STALE, PatternState.ARCHIVED):
            p.state = PatternState.ACTIVE
        self._save_patterns()

    def find_relevant_patterns(self, query: str, limit: int = 5) -> List[Pattern]:
        """简单的关键词检索 — 不需要 LLM，轻量级即可"""
        query_lower = query.lower()
        scored = []
        for p in self.patterns.values():
            if p.state not in (PatternState.ACTIVE, PatternState.PINNED):
                continue
            score = 0.0
            for word in query_lower.split():
                if word in p.title.lower():
                    score += 3
                if word in p.content.lower():
                    score += 1
            for tag in p.tags:
                if tag.lower() in query_lower:
                    score += 2
            score += p.success_rate * 0.5 + p.confidence * 0.3
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

    def get_dashboard(self) -> Dict[str, Any]:
        active = sum(1 for p in self.patterns.values() if p.state == PatternState.ACTIVE)
        total = len(self.patterns)
        top = sorted(self.patterns.values(), key=lambda p: p.usage_count, reverse=True)[:5]
        return {
            "total": total,
            "active": active,
            "stale": sum(1 for p in self.patterns.values() if p.state == PatternState.STALE),
            "archived": sum(1 for p in self.patterns.values() if p.state == PatternState.ARCHIVED),
            "pinned": sum(1 for p in self.patterns.values() if p.state == PatternState.PINNED),
            "health_score": (active / max(total, 1)) * 100,
            "top_used": [{"title": p.title, "uses": p.usage_count, "success_rate": p.success_rate} for p in top],
            "last_curation": self.state.get("last_run_at"),
        }


def create_knowledge_curator(project_root: str) -> KnowledgeCurator:
    return KnowledgeCurator(project_root)
