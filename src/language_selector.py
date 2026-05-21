"""
LLM 驱动语言选择器 — 自主 AI Agent 语言选择
=============================================

核心理念：不再使用硬编码的语言评分表和固定评分公式，
而是通过 LLM 提示词让 AI 自行推理选择最合适的语言。

设计原则：
- 语言选择由 LLM 基于任务上下文推理，不是固定评分公式
- 语言属性由 LLM 动态评估，不是预设数值
- 失败率学习由 LLM 评估影响，不是固定 ±1
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from .llm import chat
import json


@dataclass
class LanguageInfo:
    name: str
    strengths: List[str]
    weaknesses: List[str]
    use_cases: List[str]
    success_count: int = 0
    fail_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.5


@dataclass
class TaskInfo:
    type: str
    requirements: List[str]
    constraints: List[str] = field(default_factory=list)
    priority: str = "medium"


@dataclass
class OutcomeInfo:
    success: bool
    error: Optional[str] = None
    performance: Optional[float] = None
    quality: Optional[float] = None
    duration: Optional[float] = None


class LanguageRegistry:
    """语言注册表 - 基础语言信息存储，详细分析由 LLM 完成"""

    def __init__(self):
        self.registry: Dict[str, LanguageInfo] = {}
        self.history: List[Dict] = []
        self._init_base_languages()

    def _init_base_languages(self):
        """初始化基础语言描述（不含硬编码评分）"""
        base_langs = {
            "python": LanguageInfo(name="python", strengths=["AI/ML", "快速开发", "丰富生态"], weaknesses=["性能", "GIL限制"], use_cases=["AI逻辑", "原型", "数据科学", "脚本"]),
            "rust": LanguageInfo(name="rust", strengths=["极致性能", "内存安全", "并发"], weaknesses=["学习曲线陡", "编译慢"], use_cases=["系统编程", "性能关键", "嵌入式"]),
            "go": LanguageInfo(name="go", strengths=["并发", "部署简单", "简洁语法"], weaknesses=["泛型历史问题"], use_cases=["API网关", "微服务", "网络应用"]),
            "typescript": LanguageInfo(name="typescript", strengths=["类型安全", "前端生态", "可维护"], weaknesses=["编译开销"], use_cases=["Web界面", "全栈", "前端应用"]),
            "c": LanguageInfo(name="c", strengths=["极致性能", "硬件访问", "系统编程"], weaknesses=["内存安全", "开发效率"], use_cases=["硬件抽象", "实时系统", "嵌入式"]),
            "zig": LanguageInfo(name="zig", strengths=["性能接近C", "编译速度"], weaknesses=["生态小"], use_cases=["系统编程", "嵌入式"]),
            "elixir": LanguageInfo(name="elixir", strengths=["超高并发", "容错", "分布式"], weaknesses=["小众", "人才难找"], use_cases=["实时应用", "分布式系统"]),
            "julia": LanguageInfo(name="julia", strengths=["科学计算", "高性能"], weaknesses=["生态小"], use_cases=["数值计算", "科学计算"]),
            "r": LanguageInfo(name="r", strengths=["统计分析", "数据可视化"], weaknesses=["通用编程"], use_cases=["数据分析", "统计建模"]),
            "swift": LanguageInfo(name="swift", strengths=["iOS开发", "安全性"], weaknesses=["平台绑定"], use_cases=["iOS应用", "Apple生态"]),
            "kotlin": LanguageInfo(name="kotlin", strengths=["JVM生态", "Android", "空安全"], weaknesses=["JVM开销"], use_cases=["Android开发", "企业应用"]),
        }
        for name, info in base_langs.items():
            self.registry[name] = info

    def register_language(self, name: str, **kwargs):
        self.registry[name] = LanguageInfo(name=name, **kwargs)
        self.history.append({"action": "register", "language": name, "timestamp": time.time()})

    def get_language_info(self, name: str) -> Optional[LanguageInfo]:
        return self.registry.get(name)

    def list_languages(self) -> List[str]:
        return list(self.registry.keys())

    def record_result(self, name: str, success: bool):
        """记录执行结果，供 LLM 分析"""
        if name in self.registry:
            if success:
                self.registry[name].success_count += 1
            else:
                self.registry[name].fail_count += 1


class LanguageSelector:
    """LLM 驱动的语言选择器"""

    def __init__(self, registry: Optional[LanguageRegistry] = None):
        self.registry = registry or LanguageRegistry()
        self.history: List[Dict] = []

    def select_language(self, task: TaskInfo) -> str:
        """通过 LLM 推理选择最合适的语言"""
        scores = self._llm_select(task)
        if not scores:
            return self._fallback_select(task)

        best = max(scores, key=scores.get)
        self.history.append({
            "task": task.type, "selected_language": best,
            "score": scores[best], "timestamp": time.time()
        })
        return best

    def _llm_select(self, task: TaskInfo) -> Dict[str, float]:
        """LLM 推理语言选择"""
        langs_info = []
        for name, info in self.registry.registry.items():
            rate = info.success_rate
            langs_info.append(f"- {name}: 优势={info.strengths}, 劣势={info.weaknesses}, 场景={info.use_cases}, 成功率={rate:.2f}")

        prompt = f"""你是编程语言选择专家。请根据任务需求选择最合适的语言。

任务信息:
- 类型: {task.type}
- 需求: {task.requirements}
- 约束: {task.constraints}
- 优先级: {task.priority}

可选语言及属性:
{chr(10).join(langs_info)}

请为每种语言根据以下原则打分 (0-100):
- 任务需求与语言优势的匹配度
- 语言劣势是否被任务约束规避
- 使用场景是否匹配
- 历史成功率 (反映实际使用效果)
- 通用性: 如果没有明确需求偏向特定语言，优先选择Python

返回JSON格式:
{{
    "selections": [
        {{"language": "python", "score": 85, "reasoning": "..."}},
        {{"language": "rust", "score": 40, "reasoning": "..."}}
    ],
    "top_pick": "python",
    "reasoning": "综合评估理由"
}}

只返回JSON。"""

        try:
            response = chat(prompt, system="你是编程语言选择专家。只返回JSON。", temperature=0.3)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                result = {}
                for s in data.get("selections", []):
                    result[s["language"]] = float(s.get("score", 50))
                return result
        except Exception as e:
            print(f"[LanguageSelector] LLM选择失败: {e}")

        return {}

    def _fallback_select(self, task: TaskInfo) -> str:
        """简洁的回退选择"""
        task_lower = task.type.lower()
        if any(kw in task_lower for kw in ["ai", "ml", "脚本", "原型", "数据"]):
            return "python"
        if any(kw in task_lower for kw in ["性能", "系统", "嵌入式", "硬件"]):
            return "rust"
        if any(kw in task_lower for kw in ["并发", "api", "微服务", "网络"]):
            return "go"
        if any(kw in task_lower for kw in ["web", "前端", "界面"]):
            return "typescript"
        return "python"

    def get_selection_history(self) -> List[Dict]:
        return self.history

    def get_best_languages(self, task_type: str, limit: int = 3) -> List[str]:
        task = TaskInfo(type=task_type, requirements=[])
        scores = self._llm_select(task)
        if scores:
            return sorted(scores, key=scores.get, reverse=True)[:limit]
        return self._fallback_best(task_type, limit)

    def _fallback_best(self, task_type: str, limit: int) -> List[str]:
        candidates = list(self.registry.registry.keys())
        return sorted(candidates, key=lambda n: self.registry.registry[n].success_rate, reverse=True)[:limit]


class LanguageMetacognition:
    """LLM 驱动的语言元认知"""

    def __init__(self, selector: LanguageSelector):
        self.selector = selector
        self.improvement_history: List[Dict] = []
        self.suggestions: List[Dict] = []

    def evaluate_choice(self, task: TaskInfo, language_used: str, outcome: OutcomeInfo):
        self.selector.registry.record_result(language_used, outcome.success)

        record = {
            "task": task.type, "language": language_used,
            "success": outcome.success, "performance": outcome.performance,
            "quality": outcome.quality, "duration": outcome.duration,
            "timestamp": time.time()
        }
        self.improvement_history.append(record)

        if not outcome.success:
            self._generate_improvement_suggestion(task, language_used, outcome)

    def _generate_improvement_suggestion(self, task: TaskInfo, language_used: str, outcome: OutcomeInfo):
        """通过 LLM 生成改进建议"""
        prompt = f"""分析语言选择失败的原因并给出改进建议。

任务: {task.type}
使用的语言: {language_used}
失败原因: {outcome.error or "未知"}

返回JSON:
{{
    "root_cause": "失败根因分析",
    "alternative_languages": ["alt1", "alt2"],
    "improvement_advice": "改进建议"
}}

只返回JSON。"""

        try:
            response = chat(prompt, system="你是编程语言选择分析专家。只返回JSON。", temperature=0.3)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                suggestion = json.loads(response[json_start:json_end])
                suggestion["task"] = task.type
                suggestion["current_language"] = language_used
                suggestion["timestamp"] = time.time()
                self.suggestions.append(suggestion)
                return
        except Exception:
            pass

        self.suggestions.append({
            "task": task.type, "current_language": language_used,
            "failure_reason": outcome.error or "未知错误",
            "alternative_languages": self.selector.get_best_languages(task.type, 3),
            "timestamp": time.time()
        })

    def suggest_improvement(self) -> Optional[Dict]:
        return self.suggestions[-1] if self.suggestions else None

    def analyze_language_performance(self) -> Dict:
        perf = {}
        for lang in self.selector.registry.list_languages():
            entries = [h for h in self.improvement_history if h["language"] == lang]
            if entries:
                perf[lang] = {
                    "success_rate": sum(1 for h in entries if h["success"]) / len(entries),
                    "avg_performance": sum(h.get("performance", 0) or 0 for h in entries) / len(entries),
                    "avg_duration": sum(h.get("duration", 0) or 0 for h in entries) / len(entries),
                    "total_tasks": len(entries)
                }
        return perf

    def get_improvement_suggestions(self) -> List[Dict]:
        return self.suggestions


language_registry = LanguageRegistry()
language_selector = LanguageSelector(language_registry)
language_metacognition = LanguageMetacognition(language_selector)


def get_language_selector() -> LanguageSelector:
    return language_selector


def get_language_metacognition() -> LanguageMetacognition:
    return language_metacognition


def get_language_registry() -> LanguageRegistry:
    return language_registry


def select_language(task_type: str, requirements: List[str], constraints=None) -> str:
    task = TaskInfo(type=task_type, requirements=requirements, constraints=constraints or [])
    return language_selector.select_language(task)


def evaluate_language_choice(task_type: str, language_used: str, success: bool, error=None) -> None:
    task = TaskInfo(type=task_type, requirements=[])
    outcome = OutcomeInfo(success=success, error=error)
    language_metacognition.evaluate_choice(task, language_used, outcome)