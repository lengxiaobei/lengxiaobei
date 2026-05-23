"""Evolution API.

参考来源：Hermes 的反思、轨迹提炼、技能评估闭环。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.routes import runtime
from backend.evolution.evaluator import success_rate

router = APIRouter()


@router.get("/traces")
async def traces(limit: int = 100, rt=Depends(runtime)) -> dict:
    return {"items": rt.dispatcher.recent_traces(limit=limit)}


@router.post("/reflect")
async def reflect(payload: dict, rt=Depends(runtime)) -> dict:
    return rt.reflector.reflect(str(payload.get("topic") or "system"), force_skill=bool(payload.get("force_skill", True)))


@router.get("/stats")
async def stats(rt=Depends(runtime)) -> dict:
    skills = rt.skill_store.list()
    success = sum(int(item.get("success_count") or 0) for item in skills)
    fail = sum(int(item.get("fail_count") or 0) for item in skills)
    by_status: dict[str, int] = {}
    for item in skills:
        by_status[str(item.get("status") or "unknown")] = by_status.get(str(item.get("status") or "unknown"), 0) + 1
    return {
        "skills": {"count": len(skills), "by_status": by_status, "success_rate": success_rate(success, fail)},
        "reflector": rt.reflector.stats(),
        "tools": rt.tools.describe(),
    }
