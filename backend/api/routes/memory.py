"""Memory tree API.

参考来源：OpenHuman 的可编辑记忆树、语义检索、知识图谱和外部同步后的知识节点管理。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.routes import runtime
from backend.api.schemas import MemoryNodeInput

router = APIRouter()


@router.get("")
async def list_memory(limit: int = 100, rt=Depends(runtime)) -> dict:
    return {"items": rt.memory.list_recent(limit=limit)}


@router.post("")
async def add_memory(payload: MemoryNodeInput, rt=Depends(runtime)) -> dict:
    node = rt.memory.add_node(
        content=payload.content,
        node_type=payload.type,
        parent_id=payload.parent_id,
        metadata=payload.metadata or {"reference_agent": "OpenHuman"},
        summary=payload.summary,
    )
    rt.vector_store.index_node(node)
    return {"status": "success", "node": node}


@router.get("/tree")
async def memory_tree(root_id: str | None = None, limit: int = 500, rt=Depends(runtime)) -> dict:
    return {"items": rt.memory.tree(root_id=root_id, limit=limit)}


@router.get("/search")
async def search_memory(q: str = "", limit: int = 10, rt=Depends(runtime)) -> dict:
    return {"items": rt.vector_store.search(q, limit=limit)}


@router.post("/search")
async def search_memory_post(payload: dict, rt=Depends(runtime)) -> dict:
    query = str(payload.get("q") or payload.get("query") or "")
    limit = int(payload.get("limit") or 10)
    return {"items": rt.vector_store.search(query, limit=limit)}


@router.post("/reindex")
async def reindex_memory(limit: int = 1000, rt=Depends(runtime)) -> dict:
    return rt.vector_store.reindex(limit=limit)


@router.patch("/{node_id}")
async def update_memory(node_id: str, payload: dict, rt=Depends(runtime)) -> dict:
    node = rt.memory.update_node(node_id, **payload)
    return {"status": "success" if node else "not_found", "node": node}


@router.delete("/{node_id}")
async def delete_memory(node_id: str, rt=Depends(runtime)) -> dict:
    return {"status": "success" if rt.memory.delete_node(node_id) else "not_found"}


@router.post("/graph/edge")
async def add_edge(payload: dict, rt=Depends(runtime)) -> dict:
    edge = rt.graph_store.add_edge(str(payload["source"]), str(payload.get("relation") or "related_to"), str(payload["target"]), **(payload.get("metadata") or {}))
    return {"status": "success", "edge": edge}


@router.get("/graph/{entity}")
async def neighbors(entity: str, limit: int = 100, rt=Depends(runtime)) -> dict:
    return {"items": rt.graph_store.neighbors(entity, limit=limit)}


@router.post("/sync/import")
async def import_sync(payload: dict, rt=Depends(runtime)) -> dict:
    service = str(payload.get("service") or "manual")
    items = [str(item) for item in payload.get("items") or ([payload.get("content")] if payload.get("content") else [])]
    rt.sync_manager.register_inline(service, items)
    return await rt.sync_manager.run_once(service)


@router.get("/sync/status")
async def sync_status(rt=Depends(runtime)) -> dict:
    return rt.sync_manager.status()
