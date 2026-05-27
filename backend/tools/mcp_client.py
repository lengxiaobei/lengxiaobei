"""MCP (Model Context Protocol) client for lengxiaobei.

参考来源：Hermes 的 tools/mcp_tool.py —— 连接外部 MCP server，发现工具，
注册到 ToolRegistry。

植入目标：让 lengxiaobei 能连接 OpenClaw gateway 或任意 MCP server，
获得 OpenClaw 工具生态能力。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# MCP SDK is optional
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.debug("MCP SDK not installed. Install with: pip install mcp")


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    # Stdio transport
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # HTTP/SSE transport
    url: str | None = None
    transport: str = "auto"  # auto | stdio | sse | http
    headers: dict[str, str] = field(default_factory=dict)
    # Common
    timeout: float = 120.0
    connect_timeout: float = 60.0
    enabled: bool = True


@dataclass
class MCPTool:
    """A tool discovered from an MCP server."""
    name: str
    server_name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    _session: Any = None  # MCP ClientSession reference


class MCPManager:
    """Manages connections to MCP servers and exposes their tools.

    Usage:
        manager = MCPManager()
        manager.load_from_config()  # reads mcp_servers from settings/env
        await manager.connect_all()
        tools = manager.get_tools()
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._sessions: dict[str, Any] = {}  # name -> ClientSession
        self._tools: dict[str, MCPTool] = {}  # tool_name -> MCPTool
        self._connected: set[str] = set()

    def register_server(self, config: MCPServerConfig) -> None:
        self._servers[config.name] = config

    def load_from_config(self) -> None:
        """Load MCP servers from environment / config.

        Reads MCP_SERVERS_JSON env var (JSON array of server configs).
        Also supports individual env vars:
          MCP_<NAME>_COMMAND, MCP_<NAME>_URL, MCP_<NAME>_TRANSPORT
        """
        import json as _json

        # Method 1: JSON config
        servers_json = os.getenv("MCP_SERVERS_JSON", "")
        if servers_json:
            try:
                servers = _json.loads(servers_json)
                for srv in servers:
                    config = MCPServerConfig(
                        name=srv["name"],
                        command=srv.get("command"),
                        args=srv.get("args", []),
                        env=srv.get("env", {}),
                        url=srv.get("url"),
                        transport=srv.get("transport", "auto"),
                        headers=srv.get("headers", {}),
                        timeout=srv.get("timeout", 120),
                        connect_timeout=srv.get("connect_timeout", 60),
                    )
                    self.register_server(config)
            except Exception as exc:
                logger.warning("Failed to parse MCP_SERVERS_JSON: %s", exc)

        # Method 2: Auto-register OpenClaw gateway if available
        openclaw_url = os.getenv("OPENCLAW_MCP_URL", "http://localhost:18789")
        if openclaw_url and "openclaw" not in self._servers:
            self.register_server(MCPServerConfig(
                name="openclaw",
                url=f"{openclaw_url}/mcp",
                transport="sse",
                timeout=120,
            ))

    async def connect_server(self, name: str) -> bool:
        """Connect to a single MCP server and discover its tools."""
        if not MCP_AVAILABLE:
            logger.warning("MCP SDK not available, cannot connect to %s", name)
            return False

        config = self._servers.get(name)
        if not config or not config.enabled:
            return False

        try:
            if config.command:
                # Stdio transport
                return await self._connect_stdio(config)
            elif config.url:
                # SSE/HTTP transport
                return await self._connect_sse(config)
            else:
                logger.warning("MCP server %s has no command or url", name)
                return False
        except Exception as exc:
            logger.error("Failed to connect MCP server %s: %s", name, exc)
            return False

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all registered MCP servers."""
        results = {}
        for name in self._servers:
            results[name] = await self.connect_server(name)
        return results

    async def _connect_stdio(self, config: MCPServerConfig) -> bool:
        """Connect via stdio transport."""
        if not MCP_AVAILABLE:
            return False

        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env={**os.environ, **config.env} if config.env else None,
        )

        try:
            read_stream, write_stream = await asyncio.wait_for(
                stdio_client(server_params).__aenter__(),
                timeout=config.connect_timeout,
            )
            session = ClientSession(read_stream, write_stream)
            await asyncio.wait_for(session.__aenter__(), timeout=config.connect_timeout)

            # Discover tools
            tools_result = await asyncio.wait_for(
                session.list_tools(),
                timeout=config.timeout,
            )

            self._sessions[config.name] = session
            for tool in tools_result.tools:
                mcp_tool = MCPTool(
                    name=tool.name,
                    server_name=config.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    _session=session,
                )
                # Prefix with server name to avoid collisions
                full_name = f"mcp_{config.name}_{tool.name}"
                self._tools[full_name] = mcp_tool

            self._connected.add(config.name)
            logger.info("Connected MCP server %s: %d tools", config.name, len(tools_result.tools))
            return True

        except asyncio.TimeoutError:
            logger.warning("MCP server %s connection timed out", config.name)
            return False
        except Exception as exc:
            logger.error("MCP stdio connection failed for %s: %s", config.name, exc)
            return False

    async def _connect_sse(self, config: MCPServerConfig) -> bool:
        """Connect via SSE transport."""
        if not MCP_AVAILABLE:
            return False

        try:
            read_stream, write_stream = await asyncio.wait_for(
                sse_client(config.url, headers=config.headers).__aenter__(),
                timeout=config.connect_timeout,
            )
            session = ClientSession(read_stream, write_stream)
            await asyncio.wait_for(session.__aenter__(), timeout=config.connect_timeout)

            tools_result = await asyncio.wait_for(
                session.list_tools(),
                timeout=config.timeout,
            )

            self._sessions[config.name] = session
            for tool in tools_result.tools:
                mcp_tool = MCPTool(
                    name=tool.name,
                    server_name=config.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    _session=session,
                )
                full_name = f"mcp_{config.name}_{tool.name}"
                self._tools[full_name] = mcp_tool

            self._connected.add(config.name)
            logger.info("Connected MCP server %s via SSE: %d tools", config.name, len(tools_result.tools))
            return True

        except asyncio.TimeoutError:
            logger.warning("MCP server %s SSE connection timed out", config.name)
            return False
        except Exception as exc:
            logger.error("MCP SSE connection failed for %s: %s", config.name, exc)
            return False

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool by name."""
        tool = self._tools.get(tool_name)
        if not tool:
            return {"error": f"MCP tool not found: {tool_name}"}

        session = tool._session
        if not session:
            return {"error": f"MCP session not available for {tool_name}"}

        try:
            result = await asyncio.wait_for(
                session.call_tool(tool.name, arguments=arguments),
                timeout=120,
            )
            # Extract text content
            if hasattr(result, 'content'):
                texts = []
                for block in result.content:
                    if hasattr(block, 'text'):
                        texts.append(block.text)
                return {"ok": True, "content": "\n".join(texts)}
            return {"ok": True, "result": str(result)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_tools(self) -> dict[str, MCPTool]:
        """Return all discovered MCP tools."""
        return dict(self._tools)

    def get_tool_descriptors(self) -> list[dict[str, Any]]:
        """Return tool descriptors for registration into ToolRegistry."""
        return [
            {
                "name": name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "server": tool.server_name,
            }
            for name, tool in self._tools.items()
        ]

    def get_status(self) -> dict[str, Any]:
        """Return status suitable for API route."""
        return {
            "available": True,
            "servers": {
                name: {
                    "connected": self.is_connected(name),
                    "url": config.url,
                    "command": config.command,
                    "transport": config.transport,
                }
                for name, config in self._servers.items()
            },
            "tools": self.get_tool_descriptors(),
            "total_tools": len(self._tools),
        }

    def is_connected(self, server_name: str) -> bool:
        return server_name in self._connected

    async def disconnect_all(self) -> None:
        """Close all MCP sessions."""
        for name, session in self._sessions.items():
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                pass
        self._sessions.clear()
        self._connected.clear()
        self._tools.clear()


# ── Singleton ───────────────────────────────────────────────────────

_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
        _manager.load_from_config()
    return _manager


async def init_mcp() -> dict[str, bool]:
    """Initialize MCP connections. Call at startup."""
    manager = get_mcp_manager()
    return await manager.connect_all()
