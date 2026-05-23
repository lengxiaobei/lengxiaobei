"""Skill generation boundary.

参考来源：Hermes 的闭环学习：从任务轨迹、触发条件和可重复步骤生成技能草稿，
默认进入 pending 审核队列，避免未经审核的自动执行。
"""

from __future__ import annotations

from typing import Any


def draft_skill(name: str, trigger: str, steps: list[str], source_trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """生成 Hermes 风格技能草稿。"""
    return {
        "name": name,
        "trigger": trigger,
        "steps": steps,
        "status": "pending",
        "reference_agent": "Hermes",
        "source_trace": source_trace or [],
    }


def draft_from_trace(name: str, trigger: str, trace: list[dict[str, Any]]) -> dict[str, Any]:
    """从 Dispatcher 轨迹提炼步骤，局部参考 Hermes skill_gen。"""
    steps = [f"调用工具 {item.get('tool')}，参数 {item.get('args', {})}" for item in trace if item.get("ok")]
    return draft_skill(name=name, trigger=trigger, steps=steps or ["人工补充技能步骤"], source_trace=trace)
