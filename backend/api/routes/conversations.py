"""Conversation API.

参考来源：OpenClaw 将所有渠道消息规范化为 conversation input，再交由 Commander 处理。
记忆召回由 Commander/AgentLoop 注入系统上下文，不能拼进用户原文。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from backend.api.routes import runtime
from backend.api.schemas import ConversationInput

router = APIRouter()


@router.post("")
async def create_message(payload: ConversationInput, rt=Depends(runtime)) -> dict:
    rt.touch_activity(source=payload.channel)

    # Warm memory recall caches, but never prepend recall text to the user's
    # message. Doing so pollutes intent routing and can leak raw memory results.
    if rt.memory_hooks:
        try:
            await rt.memory_hooks.auto_recall(payload.message.strip())
        except Exception:
            pass

    # Session management
    session_context = ""
    if rt.session_manager:
        try:
            session = rt.session_manager.get_or_create()
            rt.session_manager.add_message(session.id, "user", payload.message.strip())
            history = rt.session_manager.get_messages(session.id, limit=20)
            # Build session context from recent history
            if len(history) > 1:
                session_context = "\n".join(
                    f"[{m['role']}] {m['content'][:200]}" for m in history[-5:-1]
                )
        except Exception:
            pass

    result = await rt.commander.handle_message(payload.message.strip(), channel=payload.channel)

    # Store assistant response in session
    if rt.session_manager:
        try:
            session = rt.session_manager.get_or_create()
            response_text = result.get("text", "")
            rt.session_manager.add_message(session.id, "assistant", response_text)
        except Exception:
            pass

    return {"status": "success", "result": {"text": result.get("text", "没有返回内容")}}


@router.get("/search")
async def search_conversations(q: str = "", limit: int = 10, rt=Depends(runtime)) -> dict:
    """Full-text search across all past conversation messages (FTS5)."""
    if not q.strip():
        return {"results": [], "query": q}
    results = rt.sqlite.search_sessions(q, limit=limit)
    return {"results": results, "query": q, "count": len(results)}
