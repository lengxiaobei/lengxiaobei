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
        "kernels": await rt.capability_registry.kernels(),
        "capabilities": await rt.capability_registry.capabilities(),
        "kernel_tasks": await rt.capability_registry.tasks(),
        "burn": rt.burn.status() if hasattr(rt, "burn") else None,
        "controlled_agents": rt.tools.get("controlled_agent_list")(),
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
    }


@router.get("/status")
async def status(rt=Depends(runtime)) -> dict:
    return await _build_status(rt)


@router.get("/events")
async def events(limit: int = 100, rt=Depends(runtime)) -> dict:
    return {"items": [event.__dict__ for event in rt.events[-limit:]]}


@router.get("/kernels")
async def kernels(rt=Depends(runtime)) -> dict:
    return {"items": await rt.capability_registry.kernels()}


@router.get("/capabilities")
async def capabilities(rt=Depends(runtime)) -> dict:
    return {"items": await rt.capability_registry.capabilities()}


@router.get("/kernel-tasks")
async def kernel_tasks(limit: int = 12, rt=Depends(runtime)) -> dict:
    return {"items": await rt.capability_registry.tasks(limit=limit)}


@router.post("/capabilities/submit")
async def submit_capability(payload: dict, rt=Depends(runtime)) -> dict:
    return await rt.capability_registry.submit(payload)


@router.get("/execution-monitor")
async def execution_monitor(limit: int = 80, rt=Depends(runtime)) -> dict:
    """Aggregated execution monitor for LengXiaobei native capability lanes."""
    controlled_status = rt.tools.get("controlled_agent_status")("all")
    controlled_agents = rt.tools.get("controlled_agent_list")()
    task_payload = rt.tools.get("controlled_agent_tasks")(limit=limit)
    tasks = task_payload.get("tasks", []) if isinstance(task_payload, dict) else []
    events = [event.__dict__ for event in rt.events[-limit:]]
    autonomy_status = rt.autonomy.status()
    autonomy_audit = autonomy_status.get("audit") or []

    agent_ids = ["openclaw", "hermes", "openhuman"]
    stats = {agent_id: _agent_execution_stats(agent_id, tasks, controlled_status) for agent_id in agent_ids}
    alerts = _execution_alerts(controlled_agents, stats, tasks, controlled_status)
    trend = _execution_trend(tasks)

    return {
        "status": "ok",
        "generated_at": time.time(),
        "agents": controlled_agents,
        "agent_status": controlled_status,
        "stats": stats,
        "tasks": tasks,
        "events": events,
        "autonomy": {
            "run_count": autonomy_status.get("run_count", 0),
            "last_run": autonomy_status.get("last_run"),
            "audit": autonomy_audit[-limit:] if isinstance(autonomy_audit, list) else [],
        },
        "alerts": alerts,
        "trend": trend,
    }


def _agent_execution_stats(agent_id: str, tasks: list[dict], controlled_status: dict) -> dict:
    agent_tasks = [task for task in tasks if task.get("agent_id") == agent_id]
    succeeded = sum(1 for task in agent_tasks if (task.get("result") or {}).get("ok") is True)
    failed = sum(1 for task in agent_tasks if (task.get("result") or {}).get("ok") is False)
    latest = max((float(task.get("created_at") or 0) for task in agent_tasks), default=None)
    status_items = controlled_status.get("items") if isinstance(controlled_status, dict) else None
    raw_status = status_items.get(agent_id) if isinstance(status_items, dict) else None
    return {
        "total": len(agent_tasks),
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": round((succeeded / len(agent_tasks)) * 100, 1) if agent_tasks else None,
        "latest_task_at": latest,
        "raw_ok": bool(raw_status.get("ok")) if isinstance(raw_status, dict) else None,
        "mode": raw_status.get("mode") if isinstance(raw_status, dict) else None,
    }


def _execution_alerts(agents: list[dict], stats: dict[str, dict], tasks: list[dict], controlled_status: dict) -> list[dict]:
    alerts: list[dict] = []
    now = time.time()
    status_items = controlled_status.get("items") if isinstance(controlled_status, dict) else {}
    for agent in agents:
        agent_id = str(agent.get("id"))
        health = agent.get("health") or {}
        if not health.get("ok"):
            severity = "critical" if agent_id == "openclaw" and not health.get("gateway_online", True) else "warning"
            alerts.append({
                "severity": severity,
                "agent_id": agent_id,
                "title": f"{agent.get('name') or agent_id} 不可调度",
                "message": health.get("error") or _health_message(agent_id, health),
                "ts": now,
            })
        agent_stats = stats.get(agent_id) or {}
        if int(agent_stats.get("failed") or 0) > 0:
            alerts.append({
                "severity": "warning",
                "agent_id": agent_id,
                "title": f"{agent.get('name') or agent_id} 存在失败执行",
                "message": f"最近 {agent_stats.get('total', 0)} 次记录中失败 {agent_stats.get('failed', 0)} 次。",
                "ts": agent_stats.get("latest_task_at") or now,
            })
        raw_status = status_items.get(agent_id) if isinstance(status_items, dict) else None
        if isinstance(raw_status, dict) and raw_status.get("error"):
            alerts.append({
                "severity": "warning",
                "agent_id": agent_id,
                "title": f"{agent.get('name') or agent_id} 状态异常",
                "message": str(raw_status.get("error")),
                "ts": now,
            })
    if not tasks:
        alerts.append({
            "severity": "info",
            "agent_id": "all",
            "title": "暂无执行记录",
            "message": "当前没有可用于统计的原生能力执行任务记录。",
            "ts": now,
        })
    return alerts[:20]


def _health_message(agent_id: str, health: dict) -> str:
    if agent_id == "openclaw" and not health.get("gateway_online", True):
        return "本地网关未在线，通道、插件和多代理分发可能不可用。"
    if agent_id == "openclaw" and not health.get("gateway_compatible", True):
        return "网关协议检查未通过，请确认本地网关版本。"
    if not health.get("installed", True):
        return "本地兼容边界未发现，原生能力仍可继续运行。"
    return "健康检查未通过。"


def _execution_trend(tasks: list[dict]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for task in tasks:
        created_at = float(task.get("created_at") or 0)
        if created_at <= 0:
            continue
        label = time.strftime("%H:%M", time.localtime(created_at))
        bucket = buckets.setdefault(label, {"time": label, "total": 0, "succeeded": 0, "failed": 0})
        bucket["total"] += 1
        ok = (task.get("result") or {}).get("ok")
        if ok is True:
            bucket["succeeded"] += 1
        elif ok is False:
            bucket["failed"] += 1
    return [buckets[key] for key in sorted(buckets.keys())][-24:]


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
