"""Shared runtime context for the YourAgent refactor.

参考来源：
- OpenClaw：把入口、会话、工具注册表和调度器收束到一个 runtime boundary。
- OpenHuman：把 memory tree / vector / graph / sync 作为长期记忆血脉挂入上下文。
- Hermes：把 reflector / skill store / evaluator 作为持续学习与技能进化组件挂入上下文。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RuntimeEvent:
    """轻量事件对象，参考 OpenClaw event bus 与 Hermes 轨迹记录。"""

    type: str
    payload: dict[str, Any]
    ts: float


@dataclass(slots=True)
class RuntimeContext:
    """应用级依赖容器。

    这个对象替代散落的全局变量：Gateway/API/Channel 只依赖 RuntimeContext，
    具体实现可替换，符合 OpenClaw 的接入边界和 OpenHuman 的数据边界思想。
    """

    project_root: Path
    data_dir: Path
    sqlite: Any
    memory: Any
    vector_store: Any
    graph_store: Any
    sync_manager: Any
    tools: Any
    dispatcher: Any
    commander: Any
    reflector: Any
    skill_store: Any
    scheduler: Any
    started_at: float
    logger: Any
    events: list[RuntimeEvent] = field(default_factory=list)

    def emit(self, event_type: str, payload: dict[str, Any]) -> RuntimeEvent:
        """记录内部事件，参考 Hermes 执行轨迹与 OpenClaw 网关事件流。"""
        import time

        event = RuntimeEvent(type=event_type, payload=payload, ts=time.time())
        self.events.append(event)
        del self.events[:-500]
        return event
