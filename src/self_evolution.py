"""Fast self-evolution MVP.

The loop is intentionally small:
learn other agents -> store lesson -> turn lesson into one source edit -> test -> remember.
"""

import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agent_learning import AgentLearner, AgentLearningStore, AgentLesson
from .llm import chat
from .utils import atomic_write_json, extract_json, load_json


BLOCKED_FILES = {
    "docs/SOUL.md",
    "docs/CONSTITUTION.md",
    "SOUL.md",
    "CONSTITUTION.md",
    ".env",
}

CONFIRM_FILES = {
    "src/core.py",
    "src/executor.py",
    "src/permission.py",
    "src/evolution/engine.py",
    "src/evolution/executor.py",
    "src/autonomy.py",
}


@dataclass
class SelfEvolutionRun:
    id: str
    topic: str
    lesson_id: str
    target_file: str
    goal: str
    status: str
    result: Dict[str, Any]
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SelfEvolutionCore:
    def __init__(self, project_root: str, evolution_engine=None):
        self.project_root = Path(project_root)
        self.learner = AgentLearner(str(self.project_root))
        self.lesson_store = AgentLearningStore(str(self.project_root))
        self.evolution_engine = evolution_engine
        self.runs_path = self.project_root / "memory" / "self_evolution_runs.json"
        self.runs_path.parent.mkdir(exist_ok=True)

    def learn(self, topic: str, url: str = "") -> AgentLesson:
        return self.learner.learn(topic, url=url)

    def evolve_from_lessons(self) -> Dict[str, Any]:
        lesson = self.lesson_store.next_pending()
        if lesson is None:
            return {"status": "no_lesson", "message": "没有 pending lesson"}
        return self.apply_lesson(lesson)

    def self_evolve(self, topic: str, url: str = "") -> Dict[str, Any]:
        lesson = self.learn(topic, url=url)
        return self.apply_lesson(lesson)

    def apply_lesson(self, lesson: AgentLesson) -> Dict[str, Any]:
        target_file = self._choose_target_file(lesson)
        boundary = self._check_boundary(target_file)
        if boundary != "allow":
            lesson.status = "blocked"
            lesson.result = {
                "status": "blocked",
                "reason": boundary,
                "target_file": target_file,
            }
            self.lesson_store.update(lesson)
            self._record_run(lesson, target_file, "", "blocked", lesson.result)
            return lesson.result

        goal = self._build_goal(lesson, target_file)
        if self.evolution_engine is None:
            result = {"status": "failed", "error": "进化引擎未配置"}
        else:
            result = self.evolution_engine.evolve(target_file, goal)

        if result.get("status") == "success":
            verify = self._verify()
            if verify["success"]:
                lesson.status = "verified"
                result["verification"] = verify
            else:
                lesson.status = "failed"
                result["status"] = "failed"
                result["verification"] = verify
        else:
            lesson.status = "failed"

        lesson.applied_at = time.time()
        lesson.result = result
        self.lesson_store.update(lesson)
        self._record_run(lesson, target_file, goal, lesson.status, result)
        return result

    def _choose_target_file(self, lesson: AgentLesson) -> str:
        candidates = lesson.suggested_files or ["src/self_evolution.py"]
        for candidate in candidates:
            if self._check_boundary(candidate) == "allow":
                path = self.project_root / candidate
                if path.exists() and path.is_file():
                    return candidate
        return "src/self_evolution.py"

    def _build_goal(self, lesson: AgentLesson, target_file: str) -> str:
        prompt = f"""把以下 Agent 学习经验转成冷小北对指定源码文件的一次小步改进目标。

目标文件: {target_file}
来源: {lesson.source}
能力: {lesson.capability}
模式: {lesson.pattern}
价值: {lesson.why_good}
适配方式: {lesson.adaptation}

要求:
- 只做一个可以快速落地的小改进
- 不重写架构
- 不添加外部依赖
- 不修改安全底线

只返回 JSON: {{"goal": "一句具体源码改进目标"}}"""
        try:
            data = extract_json(chat(prompt, system="你是冷小北自进化规划器。只返回JSON。", temperature=0.2))
            return str(data.get("goal") or lesson.adaptation or lesson.pattern)
        except Exception:
            return lesson.adaptation or lesson.pattern or f"吸收 {lesson.source} 的 {lesson.capability} 能力"

    def _verify(self) -> Dict[str, Any]:
        commands = [
            ["python3", "-m", "compileall", "-q", "src"],
            ["pytest", "tests/test_core_modules.py", "-q"],
        ]
        outputs = []
        for cmd in commands:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                outputs.append({
                    "command": " ".join(cmd),
                    "returncode": proc.returncode,
                    "stdout": proc.stdout[-1000:],
                    "stderr": proc.stderr[-1000:],
                })
                if proc.returncode != 0:
                    return {"success": False, "outputs": outputs}
            except Exception as exc:
                outputs.append({"command": " ".join(cmd), "error": str(exc)})
                return {"success": False, "outputs": outputs}
        return {"success": True, "outputs": outputs}

    def _record_run(
        self,
        lesson: AgentLesson,
        target_file: str,
        goal: str,
        status: str,
        result: Dict[str, Any],
    ) -> None:
        runs = load_json(str(self.runs_path), default=[])
        if not isinstance(runs, list):
            runs = []
        run = SelfEvolutionRun(
            id=f"run_{int(time.time())}",
            topic=lesson.topic,
            lesson_id=lesson.id,
            target_file=target_file,
            goal=goal,
            status=status,
            result=result,
            created_at=time.time(),
        )
        runs.append(run.to_dict())
        atomic_write_json(str(self.runs_path), runs)

    @staticmethod
    def _check_boundary(file_path: str) -> str:
        normalized = file_path.replace("\\", "/").lstrip("./")
        basename = normalized.rsplit("/", 1)[-1]
        for blocked in BLOCKED_FILES:
            if normalized.endswith(blocked) or basename == blocked:
                return f"禁止修改核心文件: {file_path}"
        for confirm in CONFIRM_FILES:
            if normalized.endswith(confirm):
                return f"需要宿主确认: {file_path}"
        if normalized.startswith("memory/") and "agent_lessons" not in normalized:
            return f"需要宿主确认: {file_path}"
        return "allow"
