"""
SSE Blueprint — SSE 实时事件流路由。
"""

import json
import queue

from flask import Blueprint, Response, jsonify

from lx_web.shared.state import (
    _KAIROS_EVENTS_OK,
    kairos_events,
)
from lx_web.shared.sse import (
    _sse_subscribers,
    _sse_lock,
    _ensure_event_bus,
)

sse_bp = Blueprint('sse', __name__)


@sse_bp.route("/api/events")
def api_events():
    """SSE 长连接：把 kairos.events 的事件实时推给前端。"""
    _ensure_event_bus()

    if not _KAIROS_EVENTS_OK:
        return jsonify({"error": "EventBus 未加载"}), 503

    q: queue.Queue = queue.Queue(maxsize=200)
    with _sse_lock:
        _sse_subscribers.append(q)

    def stream():
        try:
            yield ": connected\n\n"
            # 入场推最近 20 条历史，让前端有上下文
            try:
                for record in kairos_events.recent(limit=20):
                    payload = record.to_dict()
                    yield f"event: {payload['event_type']}\n"
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception:
                pass
            while True:
                try:
                    payload = q.get(timeout=15)
                    yield f"event: {payload['event_type']}\n"
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _sse_lock:
                if q in _sse_subscribers:
                    _sse_subscribers.remove(q)

    response = Response(stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response
