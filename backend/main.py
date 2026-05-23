"""Canonical ASGI entrypoint for the YourAgent refactor.

参考来源：OpenClaw Gateway 入口模式；应用工厂在 backend.gateway.server:create_app。

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

from backend.gateway.server import create_app

app = create_app()
