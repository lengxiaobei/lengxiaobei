"""Trace API — agent run observability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.routes import runtime

router = APIRouter()


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    rt=Depends(runtime),
):
    """List recent agent runs with summary info."""
    runs = rt.sqlite.trace_list_runs(limit=limit, status=status)
    return {"runs": runs, "count": len(runs)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, rt=Depends(runtime)):
    """Get full run details including steps, tool calls, and reflections."""
    run = rt.sqlite.trace_get_full_run(run_id)
    if not run:
        return {"error": "run not found"}
    return run


@router.get("/runs/{run_id}/steps")
async def get_steps(run_id: str, rt=Depends(runtime)):
    """Get steps for a specific run."""
    steps = rt.sqlite.trace_get_steps(run_id)
    return {"steps": steps, "count": len(steps)}


@router.get("/runs/{run_id}/tools")
async def get_tool_calls(run_id: str, rt=Depends(runtime)):
    """Get tool calls for a specific run."""
    calls = rt.sqlite.trace_get_tool_calls(run_id)
    return {"tool_calls": calls, "count": len(calls)}


@router.get("/runs/{run_id}/reflections")
async def get_reflections(run_id: str, rt=Depends(runtime)):
    """Get reflections for a specific run."""
    refs = rt.sqlite.trace_get_reflections(run_id)
    return {"reflections": refs, "count": len(refs)}


@router.get("/stats")
async def get_stats(rt=Depends(runtime)):
    """Get trace statistics."""
    all_runs = rt.sqlite.trace_list_runs(limit=1000)
    total = len(all_runs)
    completed = sum(1 for r in all_runs if r.get("status") == "completed")
    with_errors = sum(1 for r in all_runs if r.get("status") == "completed_with_errors")
    running = sum(1 for r in all_runs if r.get("status") == "running")
    total_tools = sum(r.get("total_tool_calls", 0) for r in all_runs)
    avg_tools = total_tools / total if total else 0
    return {
        "total_runs": total,
        "completed": completed,
        "with_errors": with_errors,
        "running": running,
        "total_tool_calls": total_tools,
        "avg_tool_calls_per_run": round(avg_tools, 1),
    }
