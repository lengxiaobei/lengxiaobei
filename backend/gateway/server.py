"""FastAPI gateway for the YourAgent refactor.

参考来源：
- OpenClaw：Gateway 统一 HTTP/WebSocket/外部渠道入口，再交给 Commander/Dispatcher。
- OpenHuman：Gateway 启动时挂载长期记忆树、向量检索、图谱和同步管理器。
- Hermes：Gateway 挂载 reflector 和 skill_store，形成反思与技能生成闭环。
"""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import autonomy, channels, conversations, evolution, memory, mcp, llm_router, sessions, skills, system
from backend.config import get_settings
from backend.core.runtime_factory import build_runtime


def create_app() -> FastAPI:
    """Create the canonical ASGI app, following OpenClaw's gateway boundary."""
    runtime = build_runtime()
    settings = get_settings()
    app = FastAPI(
        title="LengXiaobei YourAgent Gateway",
        description="Local-first autonomous agent gateway inspired by OpenClaw, Hermes, and OpenHuman.",
        version="3.1.0",
    )
    app.state.runtime = runtime

    @app.on_event("startup")
    async def _start_scheduler() -> None:
        runtime.scheduler.start()
        # Initialize MCP connections
        if runtime.mcp_manager:
            try:
                from backend.tools.mcp_client import init_mcp
                await init_mcp()
            except Exception:
                pass

    @app.on_event("shutdown")
    async def _stop_scheduler() -> None:
        runtime.scheduler.stop()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(system.router, prefix="/api/system", tags=["system"])
    app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
    app.include_router(channels.router, prefix="/api/channels", tags=["channels"])
    app.include_router(evolution.router, prefix="/api/evolution", tags=["evolution"])
    app.include_router(autonomy.router, prefix="/api/autonomy", tags=["autonomy"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(llm_router.router, prefix="/api/llm", tags=["llm-router"])
    app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "lengxiaobei-youragent-gateway",
            "message": "LengXiaobei backend is running. Open /docs for API docs or start the frontend at http://127.0.0.1:5173.",
            "docs": "/docs",
            "health": "/api/health",
            "system_status": "/api/system/status",
            "frontend_dev": "http://127.0.0.1:5173",
        }

    @app.get("/api")
    async def api_index() -> dict[str, Any]:
        return {
            "status": "ok",
            "routes": [
                "/api/health",
                "/api/system/status",
                "/api/conversations",
                "/api/memory",
                "/api/skills",
                "/api/channels",
                "/api/evolution",
                "/api/autonomy",
            ],
        }

    @app.get("/api/status")
    async def legacy_status() -> dict[str, Any]:
        return {
            "status": "running",
            "uptime_seconds": round(time.time() - runtime.started_at, 3),
            "service": "lengxiaobei-youragent-gateway",
            "note": "Use /api/system/status for the canonical status endpoint.",
        }

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "service": "lengxiaobei-youragent-gateway",
            "uptime_seconds": round(time.time() - runtime.started_at, 3),
            "components": {"gateway": "OpenClaw-inspired", "memory": "OpenHuman-inspired", "evolution": "Hermes-inspired"},
        }

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        """WebSocket channel,参考 OpenClaw 多渠道接入。"""
        await ws.accept()
        await ws.send_json({"type": "system.connected", "payload": {"status": "connected"}})
        # Push initial system status so the frontend doesn't need to poll
        try:
            from backend.api.routes.system import _build_status
            status = await _build_status(runtime)
            await ws.send_json({"type": "system.status", "payload": status})
        except Exception:
            pass
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    message = {"type": "chat.message", "payload": {"text": raw}}
                if message.get("type") == "ping":
                    await ws.send_json({"type": "pong", "payload": {"ts": time.time()}})
                    continue
                text = str((message.get("payload") or {}).get("text") or "").strip()
                if not text:
                    await ws.send_json({"type": "error", "payload": {"message": "empty message"}})
                    continue
                runtime.touch_activity(source="websocket")
                runtime.emit("agent.thinking", {"text": "planning", "channel": "websocket"})
                await ws.send_json({"type": "agent.thinking", "payload": {"text": "planning"}})
                result = await runtime.agent_loop.handle(text, channel="websocket")
                await ws.send_json(
                    {
                        "type": "chat.response",
                        "payload": {
                            "text": result.reply,
                            "tool_calls": result.tool_calls,
                            "recall_count": result.recall_count,
                            "goals_updated": result.goals_updated,
                            "elapsed_ms": result.elapsed_ms,
                            "runtime": "agent_loop",
                        },
                    }
                )
        except WebSocketDisconnect:
            runtime.logger.info("websocket disconnected")
        except Exception as exc:
            runtime.logger.exception("websocket failed: %s", exc)
            with contextlib.suppress(Exception):
                await ws.close(code=1011)
    return app


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("backend.main:app", host=settings.backend_host, port=settings.backend_port, reload=True)
