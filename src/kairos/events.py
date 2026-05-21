"""
KAIROS 事件总线
================
事件驱动补充现有心跳轮询，让 KAIROS 响应真实系统变化而非盲目定时巡检。

事件类型:
- memory.updated     — 记忆系统有写入
- code.changed       — 代码文件被修改
- test.failed        — 测试未通过
- evolution.completed — 进化流程结束（成功/失败）
- budget.warning     — 预算接近上限
- user.idle          — 用户长时间无交互
- tool.failed        — 工具执行失败
- error.escalated    — 错误升级（频率超过阈值）

用法:
    from . import events
    events.emit("code.changed", {"file": "src/core.py", "lines": 5})
    events.emit("evolution.completed", {"status": "success", "run_id": "ev-123"})
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# 事件定义
# ---------------------------------------------------------------------------

KNOWN_EVENTS = {
    "memory.updated":     "记忆系统有写入",
    "code.changed":       "代码文件被修改",
    "test.failed":        "测试未通过",
    "evolution.completed": "进化流程结束",
    "budget.warning":     "预算接近上限",
    "user.idle":          "用户长时间无交互",
    "tool.failed":        "工具执行失败",
    "error.escalated":    "错误升级（频率超过阈值）",
    "health.degraded":    "系统健康度下降",
    "kairos.awake":       "KAIROS 主动唤醒",
}


@dataclass
class EventRecord:
    """事件记录"""
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: str = "system"

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class EventBus:
    """轻量发布/订阅事件总线"""

    def __init__(self, project_root: Optional[str] = None):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()
        self._history: List[EventRecord] = []
        self._max_history = 500
        self._log_path = Path(project_root) / "kairos_events.jsonl" if project_root else None
        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def subscribe(self, event_type: str, handler: Callable[[EventRecord], None]):
        """订阅事件"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable):
        """取消订阅"""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                except ValueError:
                    pass

    def emit(self, event_type: str, data: Dict[str, Any] = None,
             source: str = "system") -> EventRecord:
        """发布事件"""
        record = EventRecord(
            event_type=event_type,
            data=data or {},
            source=source,
        )

        with self._lock:
            self._history.append(record)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        # 持久化（非阻塞）
        self._persist(record)

        # 通知订阅者
        handlers = []
        with self._lock:
            # 精确匹配 + 通配符 *
            for pattern in [event_type, "*"]:
                handlers.extend(self._subscribers.get(pattern, []))

        for handler in handlers:
            try:
                handler(record)
            except Exception as e:
                print(f"[EventBus] handler error for {event_type}: {e}")

        return record

    def _persist(self, record: EventRecord):
        if not self._log_path:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def recent(self, event_type: Optional[str] = None, limit: int = 50) -> List[EventRecord]:
        """获取最近事件"""
        with self._lock:
            records = self._history
            if event_type:
                records = [r for r in records if r.event_type == event_type]
            return records[-limit:]

    def count(self, event_type: Optional[str] = None, since: float = 0) -> int:
        """统计事件数"""
        with self._lock:
            records = self._history
            if event_type:
                records = [r for r in records if r.event_type == event_type]
            if since:
                records = [r for r in records if r.timestamp >= since]
            return len(records)

    def stats(self) -> dict:
        """事件统计摘要"""
        with self._lock:
            counts: Dict[str, int] = {}
            for r in self._history[-1000:]:
                counts[r.event_type] = counts.get(r.event_type, 0) + 1
            return {
                "total_events": len(self._history),
                "recent_24h": self.count(since=time.time() - 86400),
                "by_type": counts,
            }


# ---------------------------------------------------------------------------
# 全局单例 (每个进程一个)
# ---------------------------------------------------------------------------

_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus(project_root: Optional[str] = None) -> EventBus:
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus(project_root)
    return _bus


def emit(event_type: str, data: Dict[str, Any] = None, source: str = "system") -> EventRecord:
    """便捷发布"""
    return get_event_bus().emit(event_type, data, source)


def subscribe(event_type: str, handler: Callable[[EventRecord], None]):
    """便捷订阅"""
    get_event_bus().subscribe(event_type, handler)


def recent(event_type: str = None, limit: int = 50) -> List[EventRecord]:
    """便捷查询"""
    return get_event_bus().recent(event_type, limit)


def stats() -> dict:
    """便捷统计"""
    return get_event_bus().stats()