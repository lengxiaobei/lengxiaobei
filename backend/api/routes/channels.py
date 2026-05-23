"""Channel configuration and webhook API.

参考来源：OpenClaw 多渠道网关；Web、Telegram、WhatsApp、Slack 等渠道共享 Commander/Dispatcher。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from backend.api.routes import runtime
from backend.gateway.channels.telegram import TelegramChannel
from backend.gateway.channels.whatsapp import WhatsAppChannel

router = APIRouter()


@router.get("")
async def list_channels() -> dict:
    return {
        "items": [
            {"name": "web", "status": "enabled", "reference_agent": "OpenClaw"},
            {"name": "telegram", "status": "enabled" if os.getenv("TELEGRAM_BOT_TOKEN") else "needs_config", "reference_agent": "OpenClaw"},
            {"name": "whatsapp", "status": "enabled" if os.getenv("WHATSAPP_BRIDGE_URL") else "needs_config", "reference_agent": "OpenClaw"},
            {"name": "slack", "status": "enabled" if os.getenv("SLACK_BOT_TOKEN") else "needs_config", "reference_agent": "OpenClaw"},
        ]
    }


@router.post("/telegram/webhook")
async def telegram_webhook(payload: dict, rt=Depends(runtime)) -> dict:
    channel = TelegramChannel()
    event = channel.normalize_update(payload)
    if not event["text"]:
        return {"status": "ignored", "reason": "empty text"}
    result = await rt.commander.handle_message(event["text"], channel="telegram")
    return {"status": "processed", "result": result}


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(payload: dict, rt=Depends(runtime)) -> dict:
    channel = WhatsAppChannel()
    event = channel.normalize_update(payload)
    if not event["text"]:
        return {"status": "ignored", "reason": "empty text"}
    result = await rt.commander.handle_message(event["text"], channel="whatsapp")
    return {"status": "processed", "result": result}
