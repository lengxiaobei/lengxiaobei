"""External data sync scheduler boundary.

参考来源：
- OpenHuman：外部数据源同步为清洗后的 Markdown/记忆节点。
- OpenClaw：connector 是边界适配器，调度器只关心 fetch_updates 协议。
"""

from __future__ import annotations

import inspect
import time
from typing import Any

from backend.memory.sync.cleaner import html_to_markdownish


class InlineTextConnector:
    """用于 API 手动导入的最小连接器，等价于 OpenHuman connector 输出文本列表。"""

    def __init__(self, items: list[str]):
        self.items = items

    def fetch_updates(self, last_sync: float | None = None) -> list[str]:
        return self.items


class SyncManager:
    """同步连接器注册与运行器。"""

    def __init__(self, memory: Any | None = None, sqlite: Any | None = None) -> None:
        self.memory = memory
        self.sqlite = sqlite
        self.connectors: dict[str, object] = {}
        self.last_runs: dict[str, dict[str, Any]] = {}

    def register(self, name: str, connector: object) -> None:
        self.connectors[name] = connector

    def register_inline(self, name: str, items: list[str]) -> None:
        self.register(name, InlineTextConnector(items))

    async def run_once(self, name: str) -> dict[str, Any]:
        """执行单个连接器，参考 OpenHuman sync/manager。"""
        connector = self.connectors[name]
        fetch = getattr(connector, "fetch_updates")
        result = fetch(self.last_runs.get(name, {}).get("last_sync"))
        if inspect.isawaitable(result):
            result = await result
        items = [html_to_markdownish(str(item)) for item in list(result or [])]
        nodes = []
        if self.memory:
            for item in items:
                if not item:
                    continue
                nodes.append(self.memory.add_node(
                    content=item,
                    node_type="synced",
                    metadata={"service": name, "reference_agent": "OpenHuman"},
                    summary=item[:180],
                ))
        run = {"status": "ok", "count": len(nodes), "last_sync": time.time(), "service": name}
        self.last_runs[name] = run
        if self.sqlite:
            self.sqlite.set_sync_status(name, "ok", run)
        return run | {"nodes": nodes}

    def status(self) -> dict[str, Any]:
        sqlite_status = self.sqlite.list_sync_status() if self.sqlite else []
        return {
            "connectors": {name: {"registered": True, **self.last_runs.get(name, {})} for name in self.connectors},
            "persisted": sqlite_status,
        }
