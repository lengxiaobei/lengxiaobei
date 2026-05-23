"""Channel adapter contract.

参考来源：OpenClaw 的多渠道 adapter：Telegram/WhatsApp/WebSocket 只负责收发，
不承载业务规划或工具调度逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseChannel(ABC):
    """所有渠道适配器的最小协议。"""

    name: str

    @abstractmethod
    async def send_message(self, text: str, **kwargs) -> None:
        raise NotImplementedError
