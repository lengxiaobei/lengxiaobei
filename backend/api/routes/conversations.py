"""Conversation API.

参考来源：OpenClaw 将所有渠道消息规范化为 conversation input，再交由 Commander 处理。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.routes import runtime
from backend.api.schemas import ConversationInput

router = APIRouter()


@router.post("")
async def create_message(payload: ConversationInput, rt=Depends(runtime)) -> dict:
    result = await rt.commander.handle_message(payload.message.strip(), channel=payload.channel)
    return {"status": "success", "result": result}
