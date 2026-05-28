"""Telegram channel adapter.

参考来源：OpenClaw 多渠道网关。这里实现 Bot API sendMessage 的真实 HTTP 调用，
接收 webhook 可由 gateway 层把 update 规范化后交给 Commander。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from backend.gateway.channels.base import BaseChannel


class TelegramChannel(BaseChannel):
    name = "telegram"

    def __init__(self, token: str | None = None, default_chat_id: str | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.default_chat_id = default_chat_id or os.getenv("TELEGRAM_CHAT_ID")

    async def send_message(self, text: str, **kwargs) -> None:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        chat_id = kwargs.get("chat_id") or self.default_chat_id
        if not chat_id:
            raise RuntimeError("telegram chat_id is required")
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
            res.raise_for_status()
        except httpx.TimeoutException:
            raise RuntimeError("telegram sendMessage timed out")
        except httpx.HTTPError as exc:
            raise RuntimeError(f"telegram sendMessage failed: {exc}")

    def normalize_update(self, update: dict[str, Any]) -> dict[str, Any]:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        return {"channel": self.name, "chat_id": chat.get("id"), "text": message.get("text") or "", "raw": update}
