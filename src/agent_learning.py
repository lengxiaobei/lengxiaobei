"""Agent learning MVP.

Turns a learning topic about other agents into structured lessons that can be
fed into the self-evolution loop.
"""

import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .llm import chat
from .utils import atomic_write_json, extract_json, load_json


@dataclass
class AgentLesson:
    id: str
    source: str
    capability: str
    pattern: str
    why_good: str
    adaptation: str
    suggested_files: List[str]
    status: str = "pending"
    topic: str = ""
    evidence: str = ""
    created_at: float = 0.0
    applied_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentLesson":
        return cls(
            id=str(data.get("id", "")),
            source=str(data.get("source", "unknown")),
            capability=str(data.get("capability", "unknown")),
            pattern=str(data.get("pattern", "")),
            why_good=str(data.get("why_good", "")),
            adaptation=str(data.get("adaptation", "")),
            suggested_files=list(data.get("suggested_files") or []),
            status=str(data.get("status", "pending")),
            topic=str(data.get("topic", "")),
            evidence=str(data.get("evidence", "")),
            created_at=float(data.get("created_at") or 0.0),
            applied_at=data.get("applied_at"),
            result=data.get("result"),
        )


class AgentLearningStore:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.path = self.project_root / "memory" / "agent_lessons.json"
        self.path.parent.mkdir(exist_ok=True)

    def load(self) -> List[AgentLesson]:
        data = load_json(str(self.path), default=[])
        if not isinstance(data, list):
            return []
        lessons = []
        for item in data:
            if isinstance(item, dict):
                try:
                    lessons.append(AgentLesson.from_dict(item))
                except Exception:
                    continue
        return lessons

    def save(self, lessons: List[AgentLesson]) -> None:
        atomic_write_json(str(self.path), [lesson.to_dict() for lesson in lessons])

    def add(self, lesson: AgentLesson) -> AgentLesson:
        lessons = self.load()
        lessons.append(lesson)
        self.save(lessons)
        return lesson

    def update(self, lesson: AgentLesson) -> None:
        lessons = self.load()
        replaced = False
        for index, existing in enumerate(lessons):
            if existing.id == lesson.id:
                lessons[index] = lesson
                replaced = True
                break
        if not replaced:
            lessons.append(lesson)
        self.save(lessons)

    def next_pending(self) -> Optional[AgentLesson]:
        for lesson in self.load():
            if lesson.status == "pending":
                return lesson
        return None


class AgentLearner:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.store = AgentLearningStore(project_root)

    def learn(self, topic: str, url: str = "", kind: str = "external", gap: str = "") -> AgentLesson:
        """提炼一条学习方向为 lesson。

        kind:
            "external"      — 学其他 Agent（默认）：抓 URL + LLM 提炼
            "introspection" — 内省话题：跳过 URL，让 LLM 设计冷小北自己的源码改造方案
        gap: 仅 introspection 时使用，描述这次反思发现的能力缺口
        """
        if kind == "introspection":
            prompt = self._build_introspection_prompt(topic, gap)
            evidence = f"[introspection] gap={gap}"
        else:
            evidence = self._fetch_url(url) if url else ""
            prompt = self._build_prompt(topic, evidence)
        response = chat(
            prompt,
            system="你是冷小北的Agent学习模块。只返回JSON，不要解释。",
            temperature=0.25,
        )
        data = extract_json(response)
        lesson = self._lesson_from_data(topic, data, evidence)
        return self.store.add(lesson)

    def _build_introspection_prompt(self, topic: str, gap: str) -> str:
        """内省话题：不抓 web，直接让 LLM 设计冷小北自己的源码改造方案。"""
        return f"""你是冷小北的自我改造规划器。冷小北刚刚识别出自身一个能力缺口。

学习方向: {topic}
具体缺口: {gap or '（未提供详细描述）'}

冷小北的现有架构:
- 入口: lx_web.py / daemon.py
- 核心: src/core.py（不可直接改）
- 自进化: src/self_evolution.py
- 学习: src/agent_learning.py + src/active_learner.py
- 协作: src/buddy.py + src/dev_team.py
- 审查: src/critic.py
- 变更记录: src/code_change_log.py
- 测试: src/testing.py
- 能力注册: src/learned_capabilities.py（兜底）
- 4 大门面: facade_memory / facade_reasoning / facade_evolution / facade_guardian

请基于这个缺口，设计一个**冷小北自己**就能实施的小改造。
不要去学外部 Agent，这次是为了补冷小北自己的不足。

返回 JSON:
{{
  "source": "self_reflection",
  "capability": "新能力的名字（一个动词短语）",
  "pattern": "改造的具体做法（哪个文件加什么函数）",
  "why_good": "为什么补这个缺口对冷小北有价值",
  "adaptation": "最小化的实现步骤（≤3 步）",
  "suggested_files": ["src/某个白名单内的文件.py"],
  "evidence": "缺口的具体表现"
}}

要求:
- suggested_files 必须是冷小北 SAFE_TARGETS 内的真实文件（src/buddy.py / src/active_learner.py / src/dev_team.py / src/critic.py / src/code_change_log.py / src/testing.py / src/learned_capabilities.py）
- pattern 必须具体到"加一个 XX 函数做 YY"
- 不修改 SOUL/CONSTITUTION/核心/密钥
- 只返回 JSON"""

    def _build_prompt(self, topic: str, evidence: str) -> str:
        evidence_block = f"\n参考资料摘录:\n{evidence[:6000]}\n" if evidence else ""
        return f"""请从其他优秀 Agent / AI 编程系统中提炼一个最适合冷小北吸收的能力。

学习方向: {topic}
{evidence_block}
冷小北当前目标:
- 能学习其他 Agent 的长处
- 能把长处转化为自身源码改进
- 能小步修改、测试、回滚、记忆

请返回 JSON:
{{
  "source": "Agent或项目名称",
  "capability": "能力名称",
  "pattern": "它做得好的具体模式",
  "why_good": "为什么值得学",
  "adaptation": "冷小北如何最小化吸收",
  "suggested_files": ["建议修改的源码文件，优先普通模块"],
  "evidence": "一句话依据"
}}

要求:
- suggested_files 最多 3 个
- 优先选择可以快速落地的小改进
- 不建议修改 SOUL/CONSTITUTION/密钥/核心记忆
- 只返回 JSON"""

    def _lesson_from_data(self, topic: str, data: Dict[str, Any], evidence: str) -> AgentLesson:
        now = time.time()
        suggested = data.get("suggested_files") or ["src/self_evolution.py"]
        if not isinstance(suggested, list):
            suggested = [str(suggested)]
        return AgentLesson(
            id=f"lesson_{int(now)}",
            source=str(data.get("source", "unknown")),
            capability=str(data.get("capability", topic)),
            pattern=str(data.get("pattern", "")),
            why_good=str(data.get("why_good", "")),
            adaptation=str(data.get("adaptation", "")),
            suggested_files=[str(item) for item in suggested[:3]],
            topic=topic,
            evidence=str(data.get("evidence", "")) or evidence[:500],
            created_at=now,
        )

    @staticmethod
    def _fetch_url(url: str) -> str:
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "LengXiaobei/2.1"})
            resp.raise_for_status()
            text = resp.text
            return text[:12000]
        except Exception as exc:
            return f"URL读取失败: {exc}"
