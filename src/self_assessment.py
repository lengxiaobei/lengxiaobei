"""
自我评估模块
============
LLM 驱动的能力评估、错误分析和元认知反思。

设计原则：
- 能力评分不再硬编码，由 LLM 根据实际表现评估
- 错误分析由 LLM 做根因推理，而非只统计频率
- 系统性能交给 monitoring.py，此处不做重复
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .llm import chat


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Ability:
    """能力条目"""
    name: str
    description: str
    score: float           # 0–100
    confidence: float      # 0–100，对该评分的信心
    last_assessed: float = field(default_factory=time.time)
    evidence: List[str] = field(default_factory=list)  # 支撑该评分的证据
    history: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "score": self.score, "confidence": self.confidence,
            "last_assessed": self.last_assessed,
            "evidence": self.evidence, "history": self.history,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Ability":
        return cls(
            name=d["name"], description=d["description"],
            score=d.get("score", 50), confidence=d.get("confidence", 50),
            last_assessed=d.get("last_assessed", time.time()),
            evidence=d.get("evidence", []), history=d.get("history", []),
        )


@dataclass
class ErrorRecord:
    """错误记录"""
    id: str
    error_type: str
    message: str
    traceback: str = ""
    context: dict = field(default_factory=dict)
    frequency: int = 1
    root_cause: str = ""           # LLM 分析的根因
    fix_suggestion: str = ""       # LLM 建议的修复方案
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "error_type": self.error_type,
            "message": self.message, "traceback": self.traceback,
            "context": self.context, "frequency": self.frequency,
            "root_cause": self.root_cause, "fix_suggestion": self.fix_suggestion,
            "first_seen": self.first_seen, "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ErrorRecord":
        return cls(
            id=d["id"], error_type=d["error_type"], message=d["message"],
            traceback=d.get("traceback", ""), context=d.get("context", {}),
            frequency=d.get("frequency", 1), root_cause=d.get("root_cause", ""),
            fix_suggestion=d.get("fix_suggestion", ""),
            first_seen=d.get("first_seen", time.time()),
            last_seen=d.get("last_seen", time.time()),
        )


# ---------------------------------------------------------------------------
# LLM Prompt 模板
# ---------------------------------------------------------------------------

ASSESS_ABILITIES_PROMPT = """你是一个能力评估引擎。根据以下信息评估 AI Agent 的各项能力。

近期任务表现摘要：
{task_summary}

当前各能力自评：
{current_abilities}

请以 JSON 返回更新后的能力评估，每项包含：
- name: 能力名称
- score: 评分 0-100（基于实际表现，不是固定值）
- confidence: 对该评分的信心 0-100
- evidence: 支撑该评分的证据（从任务摘要中引用，最多 3 条）

只返回 JSON 数组，不要其他文字。"""

ANALYZE_ERROR_PROMPT = """你是一个错误分析引擎。分析以下系统错误，找出根因和建议修复方案。

错误类型：{error_type}
错误信息：{message}
堆栈跟踪：{traceback}
发生上下文：{context}
已发生次数：{frequency}

请以 JSON 返回分析结果：
{{
  "root_cause": "根因分析（一两句话）",
  "fix_suggestion": "修复建议（具体可操作）",
  "severity": "low/medium/high/critical"
}}

只返回 JSON 对象，不要其他文字。"""

METACOGNITION_PROMPT = """你是一个元认知引擎。基于 Agent 的近期表现，进行深度自我反思。

能力状态：
{abilities_summary}

近期错误：
{errors_summary}

近期经验：
{experiences_summary}

请以 JSON 返回反思结果：
{{
  "overall_assessment": "总体自我评估（2-3句）",
  "strengths": ["当前优势1", "当前优势2"],
  "weaknesses": ["当前短板1", "当前短板2"],
  "learning_priorities": ["最需要提升的方向1", "方向2"],
  "growth_trajectory": "improving/stable/declining"
}}

只返回 JSON 对象，不要其他文字。"""


# ---------------------------------------------------------------------------
# SelfAssessmentSystem
# ---------------------------------------------------------------------------

class SelfAssessmentSystem:
    """LLM 驱动的自我评估系统"""

    def __init__(self, project_root: str):
        self.assessment_dir = os.path.join(project_root, "assessment")
        os.makedirs(self.assessment_dir, exist_ok=True)
        self.abilities_file = os.path.join(self.assessment_dir, "abilities.json")
        self.errors_file = os.path.join(self.assessment_dir, "errors.json")

        self.abilities: Dict[str, Ability] = {}
        self.errors: Dict[str, ErrorRecord] = {}
        self._error_id_counter = 0
        self._load()

    # ---- 持久化 ----

    def _load(self):
        for path, target, cls in [
            (self.abilities_file, self.abilities, Ability),
            (self.errors_file, self.errors, ErrorRecord),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    if cls == ErrorRecord:
                        for item in data:
                            obj = cls.from_dict(item)
                            target[obj.id] = obj
                            if obj.id.isdigit():
                                self._error_id_counter = max(
                                    self._error_id_counter, int(obj.id))
                    else:
                        for item in data:
                            obj = cls.from_dict(item)
                            target[obj.name] = obj
                except Exception as e:
                    print(f"[SelfAssessment] 加载失败: {path} - {e}")

    def _save(self):
        for path, data in [
            (self.abilities_file, [v.to_dict() for v in self.abilities.values()]),
            (self.errors_file, [v.to_dict() for v in self.errors.values()]),
        ]:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[SelfAssessment] 保存失败: {path} - {e}")

    def _next_error_id(self) -> str:
        self._error_id_counter += 1
        return str(self._error_id_counter)

    # ---- 能力评估 ----

    def init_ability(self, name: str, description: str):
        """注册一项新能力（初始评分由 LLM 评估时确定）"""
        if name not in self.abilities:
            self.abilities[name] = Ability(name=name, description=description)
            self._save()

    def assess(self, task_summary: str = "") -> List[Ability]:
        """LLM 驱动的能力评估"""
        if not self.abilities:
            return []

        current = "\n".join(
            f"- {a.name} (score={a.score:.0f}, conf={a.confidence:.0f}): {a.description}"
            for a in self.abilities.values()
        )

        prompt = ASSESS_ABILITIES_PROMPT.format(
            task_summary=task_summary or "尚无任务数据，请基于初始状态评估",
            current_abilities=current,
        )
        try:
            result = chat(prompt, system="你是一个能力评估引擎，只返回 JSON。")
            updates = json.loads(self._extract_json(result))
            for item in updates:
                name = item["name"]
                if name in self.abilities:
                    a = self.abilities[name]
                    old_score = a.score
                    a.history.append({"score": old_score, "time": time.time()})
                    a.score = min(max(item["score"], 0), 100)
                    a.confidence = min(max(item["confidence"], 0), 100)
                    a.evidence = item.get("evidence", [])
                    a.last_assessed = time.time()
            self._save()
            return list(self.abilities.values())
        except Exception as e:
            print(f"[SelfAssessment] LLM 评估失败: {e}")
            return list(self.abilities.values())

    def get_abilities(self) -> List[Ability]:
        return sorted(self.abilities.values(), key=lambda a: a.score, reverse=True)

    # ---- 错误分析 ----

    def record_error(self, error_type: str, message: str,
                     traceback: str = "", context: dict = None) -> ErrorRecord:
        """记录错误，对首次出现的错误用 LLM 分析根因"""
        # 查找是否已存在同类错误
        for err in self.errors.values():
            if err.error_type == error_type and err.message == message:
                err.frequency += 1
                err.last_seen = time.time()
                self._save()
                return err

        # 新错误：LLM 做根因分析
        err = ErrorRecord(
            id=self._next_error_id(), error_type=error_type,
            message=message, traceback=traceback,
            context=context or {},
        )
        self._analyze_error(err)
        self.errors[err.id] = err
        self._save()
        return err

    def _analyze_error(self, err: ErrorRecord):
        """LLM 驱动的错误根因分析"""
        prompt = ANALYZE_ERROR_PROMPT.format(
            error_type=err.error_type, message=err.message,
            traceback=err.traceback[:2000], context=json.dumps(err.context, ensure_ascii=False),
            frequency=err.frequency,
        )
        try:
            result = chat(prompt, system="你是一个错误分析引擎，只返回 JSON。")
            analysis = json.loads(self._extract_json(result))
            err.root_cause = analysis.get("root_cause", "")
            err.fix_suggestion = analysis.get("fix_suggestion", "")
        except Exception as e:
            print(f"[SelfAssessment] LLM 错误分析失败: {e}")
            err.root_cause = "LLM 分析暂不可用"

    def get_errors(self, severity: str = None) -> List[ErrorRecord]:
        result = list(self.errors.values())
        result.sort(key=lambda e: (e.frequency, e.last_seen), reverse=True)
        return result

    # ---- 元认知 ----

    def reflect(self, experiences: List[dict] = None) -> dict:
        """LLM 驱动的元认知反思"""
        # 能力摘要
        ab_summary = "\n".join(
            f"- {a.name}: score={a.score:.0f}, {a.description}"
            for a in self.abilities.values()
        ) or "未初始化"

        # 错误摘要
        top_errors = sorted(
            self.errors.values(), key=lambda e: e.frequency, reverse=True
        )[:5]
        err_summary = "\n".join(
            f"- [{e.error_type}] {e.message[:100]} (×{e.frequency})"
            for e in top_errors
        ) or "无近期错误"

        # 经验摘要
        if experiences:
            recent = experiences[-5:]
            exp_summary = "\n".join(
                f"- {e.get('description', '')}: {e.get('outcome', '')[:100]}"
                for e in recent
            )
        else:
            exp_summary = "无近期经验"

        prompt = METACOGNITION_PROMPT.format(
            abilities_summary=ab_summary,
            errors_summary=err_summary,
            experiences_summary=exp_summary,
        )
        try:
            result = chat(prompt, system="你是一个元认知引擎，只返回 JSON。")
            return json.loads(self._extract_json(result))
        except Exception as e:
            print(f"[SelfAssessment] 元认知反思失败: {e}")
            return {
                "overall_assessment": "无法完成反思",
                "strengths": [], "weaknesses": [],
                "learning_priorities": [], "growth_trajectory": "stable",
            }

    # ---- 工具方法 ----

    def _extract_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return text

    def get_statistics(self) -> dict:
        abilities = list(self.abilities.values())
        total = len(abilities)
        if total == 0:
            return {"total_abilities": 0, "avg_score": 0, "strengths": 0, "weaknesses": 0}

        avg_score = sum(a.score for a in abilities) / total
        strengths = sum(1 for a in abilities if a.score >= 75)
        weaknesses = sum(1 for a in abilities if a.score < 60)
        total_errors = sum(e.frequency for e in self.errors.values())

        return {
            "total_abilities": total, "avg_score": round(avg_score, 1),
            "strengths": strengths, "weaknesses": weaknesses,
            "total_errors": total_errors, "unique_error_types": len(self.errors),
        }


def create_self_assessment_system(project_root: str) -> SelfAssessmentSystem:
    return SelfAssessmentSystem(project_root)