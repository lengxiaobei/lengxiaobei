"""System status API for LengXiaobei native runtime capabilities."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from backend.config import get_settings
from backend.api.routes import runtime

router = APIRouter()


def _model_fallback_label(provider: str) -> str:
    normalized = provider.lower().replace("_", "-")
    if normalized == "ollama":
        return "ollama_local_fallback"
    if normalized in {"openai", "openai-compatible", "token-plan"}:
        return "openai_compatible_fallback"
    return "explicit_adapter_error"


async def _build_status(rt) -> dict:
    """Build system status dict from runtime. Reusable by WebSocket and HTTP handlers."""
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
            "fallback": _model_fallback_label(settings.llm_provider),
        },
        "tools": rt.tools.list(),
        "burn": rt.burn.status() if hasattr(rt, "burn") else None,
        "local_agents": rt.tools.get("local_agent_list")(),
        "scheduler": rt.scheduler.describe(),
        "autonomy": {
            "run_count": rt.autonomy.status().get("run_count"),
            "last_goal": (rt.autonomy.status().get("last_run") or {}).get("goal", {}).get("id"),
        },
        "references": {
            "gateway": "LengXiaobei native channels",
            "memory": "LengXiaobei native memory",
            "evolution": "LengXiaobei native reflection",
        },
        "brain_hooks": {
            "active": bool(rt.brain_hooks),
            "insights_count": len(rt.brain_hooks.insights) if rt.brain_hooks else 0,
            "recoveries_count": len(rt.brain_hooks.recoveries) if rt.brain_hooks else 0,
            "injected_skills": len(rt.brain_hooks._injected_skills) if rt.brain_hooks else 0,
        } if rt.brain_hooks else None,
    }


@router.get("/status")
async def status(rt=Depends(runtime)) -> dict:
    return await _build_status(rt)


@router.get("/events")
async def events(limit: int = 100, rt=Depends(runtime)) -> dict:
    return {"items": [event.__dict__ for event in rt.events[-limit:]]}


@router.get("/capabilities")
async def capabilities(rt=Depends(runtime)) -> dict:
    return {
        "items": [
            {"id": name, "owner": "lengxiaobei", "title": name, "description": "runtime tool", "enabled": True}
            for name in rt.tools.list()
        ]
    }


@router.get("/execution-monitor")
async def execution_monitor(limit: int = 80, rt=Depends(runtime)) -> dict:
    """Aggregated execution monitor for LengXiaobei's own runtime."""
    events = [event.__dict__ for event in rt.events[-limit:]]
    autonomy_status = rt.autonomy.status()
    autonomy_audit = autonomy_status.get("audit") or []

    return {
        "status": "ok",
        "generated_at": time.time(),
        "tools": rt.tools.list(),
        "events": events,
        "autonomy": {
            "run_count": autonomy_status.get("run_count", 0),
            "last_run": autonomy_status.get("last_run"),
            "audit": autonomy_audit[-limit:] if isinstance(autonomy_audit, list) else [],
        },
        "alerts": [],
        "trend": [],
    }


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


@router.post("/burn")
async def burn_sprint(payload: dict | None = None, rt=Depends(runtime)) -> dict:
    payload = payload or {}
    cycles = max(1, min(12, int(payload.get("cycles") or 3)))
    force = bool(payload.get("force", True))
    return await rt.burn.sprint(cycles=cycles, force=force)


@router.get("/burn")
async def burn_status(rt=Depends(runtime)) -> dict:
    return rt.burn.status()
