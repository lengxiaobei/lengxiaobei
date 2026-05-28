"""Session management API.

参考来源：OpenClaw 的 session 管理 —— 多 session 隔离、history、context pruning。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from backend.api.routes import runtime

router = APIRouter()


class CreateSessionRequest(BaseModel):
    name: str = ""
    agent_id: str = "main"
    max_context_tokens: Optional[int] = None


class AddMessageRequest(BaseModel):
    role: str
    content: str
    token_count: int = 0


@router.post("")
async def create_session(payload: CreateSessionRequest, rt=Depends(runtime)) -> dict:
    """Create a new conversation session."""
    sm = rt.session_manager
    if not sm:
        return {"error": "session manager not available"}
    session = sm.create_session(
        name=payload.name,
        agent_id=payload.agent_id,
        max_context=payload.max_context_tokens,
    )
    return {
        "id": session.id,
        "name": session.name,
        "agent_id": session.agent_id,
        "max_context_tokens": session.max_context_tokens,
    }


@router.get("")
async def list_sessions(agent_id: Optional[str] = None, rt=Depends(runtime)) -> dict:
    """List all sessions."""
    sm = rt.session_manager
    if not sm:
        return {"sessions": []}
    return {"sessions": sm.list_sessions(agent_id=agent_id)}


@router.get("/{session_id}")
async def get_session(session_id: str, rt=Depends(runtime)) -> dict:
    """Get session details."""
    sm = rt.session_manager
    if not sm:
        return {"error": "session manager not available"}
    session = sm.get_session(session_id)
    if not session:
        return {"error": "session not found"}
    return {
        "id": session.id,
        "name": session.name,
        "agent_id": session.agent_id,
        "message_count": session.message_count,
        "context_tokens": session.context_tokens,
        "max_context_tokens": session.max_context_tokens,
        "compaction_count": session.compaction_count,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str, rt=Depends(runtime)) -> dict:
    """Delete a session."""
    sm = rt.session_manager
    if not sm:
        return {"error": "session manager not available"}
    ok = sm.delete_session(session_id)
    return {"ok": ok}


@router.get("/{session_id}/history")
async def get_history(session_id: str, limit: int = 50, rt=Depends(runtime)) -> dict:
    """Get session message history."""
    sm = rt.session_manager
    if not sm:
        return {"messages": []}
    return {"messages": sm.get_history(session_id, limit=limit)}


@router.post("/{session_id}/messages")
async def add_message(session_id: str, payload: AddMessageRequest, rt=Depends(runtime)) -> dict:
    """Add a message to a session."""
    sm = rt.session_manager
    if not sm:
        return {"error": "session manager not available"}
    msg = sm.add_message(
        session_id=session_id,
        role=payload.role,
        content=payload.content,
        token_count=payload.token_count,
    )
    if not msg:
        return {"error": "session not found"}
    return {"ok": True, "message_count": sm.get_session(session_id).message_count}


@router.post("/{session_id}/active")
async def set_active(session_id: str, rt=Depends(runtime)) -> dict:
    """Set a session as the active session."""
    sm = rt.session_manager
    if not sm:
        return {"error": "session manager not available"}
    ok = sm.set_active(session_id)
    return {"ok": ok}


@router.get("/stats/overview")
async def session_stats(rt=Depends(runtime)) -> dict:
    """Get session manager statistics."""
    sm = rt.session_manager
    if not sm:
        return {"error": "session manager not available"}
    return sm.get_stats()
