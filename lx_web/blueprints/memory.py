"""
记忆系统 Blueprint — memory / curator / summarize / dream 相关路由。
"""

import time

from flask import Blueprint, jsonify, request

from lx_web.shared.state import PROJECT_ROOT
from lx_web.shared.utils import (
    _get_agent,
    _jsonable,
    _safe_attr,
)

memory_bp = Blueprint('memory', __name__)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _get_memory_tree(agent):
    """获取或创建 MemoryTree 实例"""
    if agent is None:
        return None
    try:
        from src.memory_tree import MemoryTree
        backend = agent.memory_facade.hybrid_memory if agent.memory_facade else None
        return MemoryTree(str(PROJECT_ROOT), memory_backend=backend)
    except Exception as e:
        print(f"[lx_web] MemoryTree 初始化失败: {e}")
        return None


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@memory_bp.route("/api/memory/layers", methods=["GET"])
def api_memory_layers():
    """获取四层记忆的统计数据和摘要"""
    agent = _get_agent()
    tree = _get_memory_tree(agent)
    if tree is None:
        return jsonify({"error": "记忆系统未就绪"}), 503

    try:
        stats = tree.stats()
        # 每层取最近几条作为摘要预览
        layers_preview = {}
        for layer_name in ["raw_event", "episode", "knowledge", "profile"]:
            items = tree.get_layer(layer_name, limit=5)
            layers_preview[layer_name] = {
                "count": stats["layers"].get(layer_name, 0),
                "preview": [
                    {"content": item.get("content", "")[:200], "role": item.get("role", ""), "created_at": item.get("created_at")}
                    for item in items
                ],
            }
        profile = tree.get_profile()
        return jsonify({
            "status": "ok",
            "stats": stats,
            "layers": layers_preview,
            "profile": profile,
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


@memory_bp.route("/api/memory/refine", methods=["POST"])
def api_memory_refine():
    """执行记忆提炼：raw_event → episode → knowledge → profile"""
    agent = _get_agent()
    tree = _get_memory_tree(agent)
    if tree is None:
        return jsonify({"error": "记忆系统未就绪"}), 503

    data = request.get_json(silent=True) or {}
    direction = data.get("direction", "all")  # raw_to_episode | episode_to_knowledge | knowledge_to_profile | all

    results = {}
    try:
        if direction in ("raw_to_episode", "all"):
            result = tree.refine_raw_to_episode()
            results["raw_to_episode"] = result or {"status": "skipped", "reason": "无原始事件可提炼"}

        if direction in ("episode_to_knowledge", "all"):
            items = tree.refine_episode_to_knowledge()
            results["episode_to_knowledge"] = {"new_knowledge_count": len(items), "items": items[:5]}

        if direction in ("knowledge_to_profile", "all"):
            result = tree.refine_knowledge_to_profile()
            results["knowledge_to_profile"] = result or {"status": "skipped", "reason": "无知识可提炼"}

        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed", "partial_results": results}), 500


@memory_bp.route("/api/memory/search", methods=["POST"])
def api_memory_search():
    """语义检索 hybrid_memory。"""
    agent = _get_agent()
    if agent is None:
        return jsonify({"status": "failed", "error": "Agent 未就绪"}), 503
    data = request.get_json(silent=True) or {}
    query = str(data.get("query", "")).strip()
    if not query:
        return jsonify({"status": "failed", "error": "query 为空"}), 400
    try:
        limit = max(1, min(int(data.get("limit", 5)), 50))
    except Exception:
        limit = 5
    mem_type = data.get("mem_type") or None

    try:
        results = agent.recall(query, limit=limit, mem_type=mem_type)
        return jsonify({
            "status": "ok",
            "query": query,
            "count": len(results or []),
            "results": _jsonable(results or []),
        })
    except Exception as exc:
        return jsonify({"status": "failed", "error": str(exc)}), 500


@memory_bp.route("/api/memory/index", methods=["GET"])
def api_memory_index():
    """记忆索引摘要。"""
    agent = _get_agent()
    if agent is None:
        return jsonify({"status": "failed", "error": "Agent 未就绪"}), 503
    try:
        mf = getattr(agent, "memory_facade", None)
        hm = _safe_attr(mf, "hybrid_memory") if mf else None
        if hm is None:
            return jsonify({"status": "ok", "index": "", "note": "hybrid_memory 未就绪"})
        content = hm.get_memory_index_content() if hasattr(hm, "get_memory_index_content") else ""
        return jsonify({"status": "ok", "index": content or "", "size": len(content or "")})
    except Exception as exc:
        return jsonify({"status": "failed", "error": str(exc)}), 500


@memory_bp.route("/api/curator/run", methods=["POST"])
def api_curator_run():
    """运行知识策展：LLM 驱动的模式提取 + 伞形合并"""
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    try:
        curator = agent.memory_facade.knowledge_curator
        dry_run = request.get_json(silent=True) or {}.get("dry_run", False)
        result = curator.run_curation(dry_run=dry_run)
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


@memory_bp.route("/api/curator/patterns", methods=["GET"])
def api_curator_patterns():
    """获取策展知识模式列表"""
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    try:
        curator = agent.memory_facade.knowledge_curator
        query = request.args.get("q", "").strip()
        limit = min(max(int(request.args.get("limit", 20)), 1), 100)

        if query:
            patterns = curator.find_relevant_patterns(query, limit=limit)
        else:
            # 返回所有 active 模式
            patterns = [
                p.to_dict() for p in curator.patterns.values()
                if p.state.value == "active"
            ][:limit]

        return jsonify({"status": "ok", "patterns": patterns, "count": len(patterns)})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


@memory_bp.route("/api/summarize", methods=["POST"])
def api_summarize():
    """智能摘要：对任意文本或工具输出做 LLM 摘要，替代硬截断"""
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    max_length = min(max(int(data.get("max_length", 500)), 100), 4000)
    focus = data.get("focus", "").strip()  # 摘要聚焦方向

    if not content:
        return jsonify({"error": "content 为空"}), 400

    # 如果内容本身就不长，直接返回
    if len(content) <= max_length:
        return jsonify({"status": "ok", "summary": content, "original_length": len(content), "compressed": False})

    try:
        from src import llm
        focus_hint = f"\n聚焦方向：{focus}" if focus else ""
        prompt = f"""请将以下内容压缩为不超过{max_length}字的摘要，保留关键信息、数据点和结论，去除冗余细节。{focus_hint}

原始内容：
{content[:12000]}"""

        summary = llm.chat(
            prompt,
            system="你是一个精确的摘要引擎。只输出摘要，不加评论。",
            temperature=0.1,
            use_cache=False,
        )
        return jsonify({
            "status": "ok",
            "summary": summary.strip(),
            "original_length": len(content),
            "summary_length": len(summary.strip()),
            "compressed": True,
        })
    except Exception as e:
        # LLM 不可用时回退到尾部截断（保留开头 + 截断标记）
        half = max_length // 2
        fallback = content[:half] + f"\n\n...[原始内容过长，LLM 摘要失败({e})，已截断]...\n\n" + content[-half:]
        return jsonify({
            "status": "fallback",
            "summary": fallback[:max_length],
            "original_length": len(content),
            "error": str(e),
            "compressed": True,
        })


@memory_bp.route("/api/dream", methods=["POST"])
def api_dream():
    """触发 AutoDream 记忆整理（4 阶段：Orient → Gather → Consolidate → Prune）"""
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    try:
        dream = agent.memory_facade.auto_dream
        # AutoDreamV2.execute() 是异步的，在同步 Flask 中需要用 asyncio
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已有事件循环（不太可能在 Flask 中），用线程跑
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, dream.execute()).result(timeout=120)
            else:
                result = loop.run_until_complete(dream.execute())
        except RuntimeError:
            result = asyncio.run(dream.execute())

        return jsonify({"status": "ok", "result": str(result)})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500
