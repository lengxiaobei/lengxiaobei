"""
SSE 基础设施 — 把 kairos.events 的回调订阅模式适配到 Queue 模式。
"""

import json
import queue
import threading

from lx_web.shared.state import (
    PROJECT_ROOT,
    kairos_events,
    _KAIROS_EVENTS_OK,
)

_sse_subscribers: "list[queue.Queue]" = []
_sse_lock = threading.Lock()
_sse_handler_registered = False


def _ensure_event_bus() -> None:
    """确保 EventBus 已初始化并注册了 SSE 转发 handler。"""
    global _sse_handler_registered
    if not _KAIROS_EVENTS_OK:
        return
    try:
        kairos_events.get_event_bus()
    except kairos_events.EventBusNotInitialized:
        kairos_events.init_event_bus(str(PROJECT_ROOT))

    if not _sse_handler_registered:
        def _sse_fanout(record):
            payload = record.to_dict()
            with _sse_lock:
                dead = []
                for q in _sse_subscribers:
                    try:
                        q.put_nowait(payload)
                    except queue.Full:
                        dead.append(q)
                for q in dead:
                    if q in _sse_subscribers:
                        _sse_subscribers.remove(q)
        kairos_events.subscribe("*", _sse_fanout)
        _sse_handler_registered = True


def _emit_event(event_type: str, data: "dict | None" = None, source: str = "web") -> None:
    """安全发布事件。EventBus 未初始化或异常时静默跳过。"""
    if not _KAIROS_EVENTS_OK:
        return
    try:
        _ensure_event_bus()
        kairos_events.emit(event_type, data or {}, source=source)
    except Exception:
        pass
