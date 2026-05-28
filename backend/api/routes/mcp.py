"""MCP (Model Context Protocol) management API.

参考来源：OpenClaw 的 MCP server 管理 —— 查看已连接 server、工具列表、重连。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.routes import runtime

router = APIRouter()


@router.get("/status")
async def mcp_status(rt=Depends(runtime)) -> dict:
    """Get MCP manager status including connected servers and tools."""
    if not rt.mcp_manager:
        return {"error": "MCP manager not available", "available": False}
    manager = rt.mcp_manager
    return {
        "available": True,
        "servers": {
            name: {
                "connected": manager.is_connected(name),
                "url": config.url,
                "command": config.command,
                "transport": config.transport,
            }
            for name, config in manager._servers.items()
        },
        "tools": manager.get_tool_descriptors(),
        "total_tools": len(manager._tools),
    }


@router.get("/tools")
async def list_mcp_tools(rt=Depends(runtime)) -> dict:
    """List all MCP tools."""
    if not rt.mcp_manager:
        return {"tools": []}
    return {"tools": rt.mcp_manager.get_tool_descriptors()}


@router.post("/connect")
async def connect_server(name: str, rt=Depends(runtime)) -> dict:
    """Connect to a specific MCP server."""
    if not rt.mcp_manager:
        return {"error": "MCP manager not available"}
    ok = await rt.mcp_manager.connect_server(name)
    return {"ok": ok, "server": name}


@router.post("/connect-all")
async def connect_all(rt=Depends(runtime)) -> dict:
    """Connect to all registered MCP servers."""
    if not rt.mcp_manager:
        return {"error": "MCP manager not available"}
    results = await rt.mcp_manager.connect_all()
    return {"results": results}


@router.post("/call-tool")
async def call_mcp_tool(tool_name: str, arguments: dict | None = None, rt=Depends(runtime)) -> dict:
    """Call an MCP tool directly."""
    if not rt.mcp_manager:
        return {"error": "MCP manager not available"}
    result = await rt.mcp_manager.call_tool(tool_name, arguments or {})
    return result
