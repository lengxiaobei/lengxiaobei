"""System status API.

参考来源：OpenClaw 的 gateway/system routes；同时暴露 OpenHuman 记忆层和 Hermes 反思层状态。
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from backend.config import get_settings
from backend.api.routes import runtime

router = APIRouter()


@router.get("/status")
async def status(rt=Depends(runtime)) -> dict:
    settings = get_settings()
    return {
        "status": "running",
        "uptime_seconds": round(time.time() - rt.started_at, 3),
        "project_root": str(rt.project_root),
        "data_dir": str(rt.data_dir),
        "model": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "base_url": settings.llm_base_url,
            "api_key_configured": bool(settings.llm_api_key),
            "fallback": (
                "ollama_local_fallback"
                if settings.llm_provider.lower() == "ollama"
                else "explicit_adapter_error"
            ),
        },
        "tools": rt.tools.list(),
        "scheduler": rt.scheduler.describe(),
        "references": {"gateway": "OpenClaw", "memory": "OpenHuman", "evolution": "Hermes"},
    }


@router.get("/events")
async def events(limit: int = 100, rt=Depends(runtime)) -> dict:
    return {"items": [event.__dict__ for event in rt.events[-limit:]]}


@router.post("/tools/{name}")
async def run_tool(name: str, payload: dict | None = None, rt=Depends(runtime)) -> dict:
    return await rt.dispatcher.dispatch(name, (payload or {}).get("args") or {})


@router.get("/scheduler")
async def scheduler_status(rt=Depends(runtime)) -> dict:
    return rt.scheduler.describe()


@router.post("/scheduler/{job_id}/run")
async def scheduler_run(job_id: str, rt=Depends(runtime)) -> dict:
    return await rt.scheduler.run_now(job_id)


@router.post("/reflect")
async def reflect(payload: dict, rt=Depends(runtime)) -> dict:
    return rt.reflector.reflect(str(payload.get("topic") or "system"))
