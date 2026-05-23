"""Skill review API.

参考来源：Hermes 的技能生成、存储、审核、执行和成功率评估流程。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.routes import runtime
from backend.api.schemas import SkillDraftInput
from backend.evolution.skill_gen import draft_skill

router = APIRouter()


@router.get("")
async def list_skills(status: str | None = None, rt=Depends(runtime)) -> dict:
    return {"items": rt.skill_store.list(status=status)}


@router.post("/draft")
async def create_skill_draft(payload: SkillDraftInput, rt=Depends(runtime)) -> dict:
    steps = payload.steps
    if isinstance(steps, str):
        steps = [line.strip() for line in steps.splitlines() if line.strip()]
    skill = draft_skill(name=payload.name, trigger=payload.trigger, steps=list(steps))
    path = rt.skill_store.save(skill)
    return {"status": "pending", "path": str(path), "skill": skill}


@router.post("/{name}/approve")
async def approve_skill(name: str, rt=Depends(runtime)) -> dict:
    return {"skill": rt.skill_store.set_status(name, "approved")}


@router.post("/{name}/reject")
async def reject_skill(name: str, rt=Depends(runtime)) -> dict:
    return {"skill": rt.skill_store.set_status(name, "rejected")}


@router.post("/{name}/execute")
async def execute_skill(name: str, payload: dict | None = None, rt=Depends(runtime)) -> dict:
    return rt.tools.get("skill_execute")(name=name, inputs=(payload or {}).get("inputs") or {})
