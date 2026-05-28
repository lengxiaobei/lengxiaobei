"""Autonomy API.

This exposes the project-scoped autonomous learning, execution, verification,
and evolution loop.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.routes import runtime

router = APIRouter()


@router.get("/status")
async def status(rt=Depends(runtime)) -> dict:
    return rt.autonomy.status()


@router.post("/tick")
async def tick(payload: dict | None = None, rt=Depends(runtime)) -> dict:
    payload = payload or {}
    return await rt.autonomy.tick(
        str(payload.get("reason") or "manual"),
        force=bool(payload.get("force", True)),
        expensive_checks=bool(payload.get("expensive_checks", False)),
    )


@router.get("/audit")
async def audit(limit: int = 100, rt=Depends(runtime)) -> dict:
    return {"items": rt.autonomy.audit.recent(limit=limit)}
