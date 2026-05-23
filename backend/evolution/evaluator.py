"""Skill evaluation boundary.

参考来源：Hermes evaluator：技能不是生成即成功，而要通过成功率和语义/集成信号评估。
"""

from __future__ import annotations


def success_rate(success_count: int, fail_count: int) -> float:
    """计算技能成功率，局部参考 Hermes 技能评估指标。"""
    total = success_count + fail_count
    return 0.0 if total == 0 else success_count / total


def staged_quality(**signals: bool) -> dict[str, bool]:
    """质量分层信号，对齐项目 CLAUDE.md 中的自进化验证语义。"""
    keys = ["syntax_ok", "function_exists", "callable_ok", "semantic_ok", "integrated_ok"]
    return {key: bool(signals.get(key, False)) for key in keys}
