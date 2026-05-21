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

    def learn(self, topic: str, url: str = "") -> AgentLesson:
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
