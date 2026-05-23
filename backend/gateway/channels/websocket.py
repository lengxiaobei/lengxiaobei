"""WebSocket channel adapter."""

from __future__ import annotations

from backend.gateway.channels.base import BaseChannel


class WebSocketChannel(BaseChannel):
    name = "websocket"

    def __init__(self, websocket):
        self.websocket = websocket

    async def send_message(self, text: str, **kwargs) -> None:
        await self.websocket.send_json({"type": "chat.response", "payload": {"text": text, **kwargs}})
