"""Skill review API.

参考来源：Hermes 的技能生成、存储、审核、执行和成功率评估流程。
Phase 4: 增加成功率统计、自动降权、失败模式库。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.routes import runtime
from backend.api.schemas import SkillDraftInput, SkillReviewInput
from backend.evolution.skill_gen import draft_skill

router = APIRouter()


@router.get("")
async def list_skills(status: str | None = None, rt=Depends(runtime)) -> dict:
    """List skills with success rate stats."""
    return {"items": rt.skill_store.list_with_stats(status=status)}


@router.get("/{name}/stats")
async def get_skill_stats(name: str, rt=Depends(runtime)) -> dict:
    """Get detailed skill stats including success rate."""
    stats = rt.skill_store.get_stats(name)
    if not stats:
        return {"error": "skill not found"}
    return {"skill": stats}


@router.post("/draft")
async def create_skill_draft(payload: SkillDraftInput, rt=Depends(runtime)) -> dict:
    steps = payload.steps
    if isinstance(steps, str):
        steps = [line.strip() for line in steps.splitlines() if line.strip()]
    skill = draft_skill(name=payload.name, trigger=payload.trigger, steps=list(steps))
    path = rt.skill_store.save(skill)
    return {"status": "pending", "path": str(path), "skill": skill}


@router.post("/{name}/approve")
async def approve_skill(name: str, payload: SkillReviewInput | None = None, rt=Depends(runtime)) -> dict:
    review = payload or SkillReviewInput()
    return {
        "skill": rt.skill_store.review(
            name,
            "approved",
            reviewer=review.reviewer,
            notes=review.notes,
            evidence=review.evidence,
            checks=review.checks,
            rollback_plan=review.rollback_plan,
        )
    }


@router.post("/{name}/reject")
async def reject_skill(name: str, payload: SkillReviewInput | None = None, rt=Depends(runtime)) -> dict:
    review = payload or SkillReviewInput()
    return {
        "skill": rt.skill_store.review(
            name,
            "rejected",
            reviewer=review.reviewer,
            notes=review.notes,
            evidence=review.evidence,
            checks=review.checks,
            rollback_plan=review.rollback_plan,
        )
    }


@router.post("/{name}/upgrade")
async def upgrade_skill_version(name: str, rt=Depends(runtime)) -> dict:
    """Increment skill version after successful use."""
    new_version = rt.skill_store.upgrade_version(name)
    return {"name": name, "version": new_version}


@router.post("/auto-demote")
async def auto_demote_skills(
    min_uses: int = 5,
    min_success_rate: float = 30.0,
    rt=Depends(runtime),
) -> dict:
    """Auto-demote skills with low success rate."""
    demoted = rt.skill_store.auto_demote(min_uses=min_uses, min_success_rate=min_success_rate)
    return {"demoted": demoted, "count": len(demoted)}


@router.get("/failure-patterns")
async def list_failure_patterns(
    tool: str | None = None,
    min_occurrences: int = 2,
    rt=Depends(runtime),
) -> dict:
    """List failure patterns for learning."""
    if not rt.sqlite:
        return {"items": [], "error": "sqlite not available"}
    patterns = rt.sqlite.get_failure_patterns(tool=tool, min_occurrences=min_occurrences)
    return {"items": patterns}


@router.post("/failure-patterns/{pattern_id}/resolve")
async def resolve_failure_pattern(pattern_id: str, resolution: str = "", rt=Depends(runtime)) -> dict:
    """Mark a failure pattern as resolved."""
    if not rt.sqlite:
        return {"error": "sqlite not available"}
    rt.sqlite.resolve_failure_pattern(pattern_id, resolution)
    return {"status": "resolved", "pattern_id": pattern_id}


@router.post("/{name}/execute")
async def execute_skill(name: str, payload: dict | None = None, rt=Depends(runtime)) -> dict:
    return rt.tools.get("skill_execute")(name=name, inputs=(payload or {}).get("inputs") or {})
