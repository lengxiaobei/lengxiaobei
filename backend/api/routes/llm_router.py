"""LLM Router management API.

参考来源：OpenClaw 的 models.providers 路由管理 —— 查看 provider 状态、健康检查、切换 primary。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.routes import runtime

router = APIRouter()


@router.get("/status")
async def router_status(rt=Depends(runtime)) -> dict:
    """Get LLM router status including all providers and their health."""
    if not rt.llm_router:
        return {"error": "LLM router not available"}
    return rt.llm_router.get_status()


@router.get("/providers")
async def list_providers(rt=Depends(runtime)) -> dict:
    """List all registered providers."""
    if not rt.llm_router:
        return {"providers": []}
    status = rt.llm_router.get_status()
    return {"providers": status.get("providers", {})}


@router.post("/health-check")
async def health_check(provider: str | None = None, rt=Depends(runtime)) -> dict:
    """Run health check on a specific or all providers."""
    if not rt.llm_router:
        return {"error": "LLM router not available"}
    results = await rt.llm_router.health_check(provider)
    return {"results": results}


@router.post("/test")
async def test_chat(
    prompt: str = "say hi",
    model: str | None = None,
    rt=Depends(runtime),
) -> dict:
    """Test the LLM router with a simple message."""
    if not rt.llm_router:
        return {"error": "LLM router not available"}
    result = await rt.llm_router.chat(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        max_tokens=50,
    )
    return result
