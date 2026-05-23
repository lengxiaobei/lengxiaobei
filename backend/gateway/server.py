"""FastAPI gateway for the YourAgent refactor.

参考来源：
- OpenClaw：Gateway 统一 HTTP/WebSocket/外部渠道入口，再交给 Commander/Dispatcher。
- OpenHuman：Gateway 启动时挂载长期记忆树、向量检索、图谱和同步管理器。
- Hermes：Gateway 挂载 reflector 和 skill_store，形成反思与技能生成闭环。
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import channels, conversations, evolution, memory, skills, system
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
                runtime.emit("agent.thinking", {"text": "planning", "channel": "websocket"})
                await ws.send_json({"type": "agent.thinking", "payload": {"text": "planning"}})
                result = await runtime.commander.handle_message(text)
                await ws.send_json({"type": "chat.response", "payload": result})
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
