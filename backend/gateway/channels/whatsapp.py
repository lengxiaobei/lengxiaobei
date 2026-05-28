"""WhatsApp channel adapter.

参考来源：OpenClaw 多渠道网关。WhatsApp 常通过 Baileys/桥接服务接入；这里实现
HTTP bridge 的 send/normalize 能力，避免把桥接细节泄漏到 Commander。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from backend.gateway.channels.base import BaseChannel


class WhatsAppChannel(BaseChannel):
    name = "whatsapp"

    def __init__(self, bridge_url: str | None = None, token: str | None = None):
        self.bridge_url = (bridge_url or os.getenv("WHATSAPP_BRIDGE_URL") or "").rstrip("/")
        self.token = token or os.getenv("WHATSAPP_BRIDGE_TOKEN")

    async def send_message(self, text: str, **kwargs) -> None:
        if not self.bridge_url:
            raise RuntimeError("WHATSAPP_BRIDGE_URL is not configured")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        payload = {"to": kwargs.get("to") or kwargs.get("chat_id"), "text": text}
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{self.bridge_url}/send", json=payload, headers=headers, timeout=20
                )
            res.raise_for_status()
        except httpx.TimeoutException:
            raise RuntimeError("whatsapp send_message timed out")
        except httpx.HTTPError as exc:
            raise RuntimeError(f"whatsapp send_message failed: {exc}")

    def normalize_update(self, update: dict[str, Any]) -> dict[str, Any]:
        return {"channel": self.name, "chat_id": update.get("from") or update.get("chat_id"), "text": update.get("text") or update.get("body") or "", "raw": update}
