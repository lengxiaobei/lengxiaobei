"""Slack channel adapter."""

from __future__ import annotations

import os
from typing import Any

import httpx

from backend.gateway.channels.base import BaseChannel


class SlackChannel(BaseChannel):
    name = "slack"

    def __init__(self, token: str | None = None, default_channel_id: str | None = None):
        self.token = token or os.getenv("SLACK_BOT_TOKEN")
        self.default_channel_id = default_channel_id or os.getenv("SLACK_CHANNEL_ID")

    async def send_message(self, text: str, **kwargs) -> None:
        if not self.token:
            raise RuntimeError("SLACK_BOT_TOKEN is not configured")
        channel = kwargs.get("channel") or kwargs.get("channel_id") or self.default_channel_id
        if not channel:
            raise RuntimeError("slack channel_id is required")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json={"channel": channel, "text": text},
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=20,
                )
            res.raise_for_status()
            payload = res.json()
            if not payload.get("ok"):
                raise RuntimeError(payload.get("error") or "slack send failed")
        except httpx.TimeoutException:
            raise RuntimeError("slack sendMessage timed out")
        except httpx.HTTPError as exc:
            raise RuntimeError(f"slack sendMessage failed: {exc}")

    def normalize_update(self, update: dict[str, Any]) -> dict[str, Any]:
        event = update.get("event") or update
        return {
            "channel": self.name,
            "chat_id": event.get("channel"),
            "text": event.get("text") or "",
            "raw": update,
        }
