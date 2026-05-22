"""
进化 Blueprint：自进化、学习 Agent、发现改进、进化进度。
"""

from flask import Blueprint, jsonify, request

from lx_web.shared.utils import (
    _get_agent,
    _jsonable,
    _schedule_restart_if_source_changed,
)

evolution_bp = Blueprint('evolution', __name__)


@evolution_bp.route("/api/evolution", methods=["POST"])
def api_evolution():
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    evo = getattr(agent, "autonomous_evolution", None)
    if evo is None:
        return jsonify({"error": "进化引擎未就绪"}), 503

    try:
        result = evo.evolve_autonomously()
        return jsonify({"result": result, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


@evolution_bp.route("/api/self-evolve", methods=["POST"])
def api_self_evolve():
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    data = request.get_json(silent=True) or {}
    topic = data.get("topic", "").strip()
    url = data.get("url", "").strip()
    apply_pending = bool(data.get("apply_pending", False))

    if not topic and not apply_pending:
        return jsonify({"error": "topic 为空"}), 400

    try:
        if apply_pending:
            result = agent.evolve_from_lessons()
        else:
            result = agent.self_evolve(topic, url=url)
        restart = _schedule_restart_if_source_changed(result, "self_evolve_source_changed")
        return jsonify({"result": result, "restart": restart, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


@evolution_bp.route("/api/learn-agent", methods=["POST"])
def api_learn_agent():
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    data = request.get_json(silent=True) or {}
    topic = data.get("topic", "").strip()
    url = data.get("url", "").strip()
    if not topic:
        return jsonify({"error": "topic 为空"}), 400

    try:
        lesson = agent.learn_agent(topic, url=url)
        return jsonify({"lesson": lesson, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


@evolution_bp.route("/api/discover", methods=["POST"])
def api_discover():
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    evo = getattr(agent, "autonomous_evolution", None)
    if evo is None:
        return jsonify({"error": "进化引擎未就绪"}), 503

    try:
        improvements = evo.discover_improvements()
        return jsonify({"improvements": improvements, "count": len(improvements), "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


@evolution_bp.route("/api/evolve/improvements", methods=["GET"])
def api_evolve_improvements():
    """预览待应用的进化改进（不真正应用）。"""
    agent = _get_agent()
    if agent is None:
        return jsonify({"status": "failed", "error": "Agent 未就绪"}), 503
    evo = getattr(agent, "evolution_facade", None)
    if evo is None:
        return jsonify({"status": "failed", "error": "进化门面未就绪"}), 503
    try:
        engine = evo.autonomous_evolution
        improvements = engine.discover_improvements()
        return jsonify({
            "status": "ok",
            "count": len(improvements or []),
            "improvements": _jsonable(improvements or []),
        })
    except Exception as exc:
        return jsonify({"status": "failed", "error": str(exc)}), 500


@evolution_bp.route("/api/evolve/progress", methods=["GET"])
def api_evolve_progress():
    """当前 self_evolve / auto_dream 的步骤进度（如有）。"""
    progress: dict = {"self_evolve": None, "auto_dream": None}
    agent = _get_agent()
    if agent is None:
        return jsonify({"status": "ok", "progress": progress})
    try:
        mf = getattr(agent, "memory_facade", None)
        ad = getattr(mf, "auto_dream", None) if mf else None
        if ad is not None:
            tracker = getattr(ad, "progress_tracker", None) or getattr(ad, "_progress", None)
            if tracker is not None:
                progress["auto_dream"] = _jsonable(getattr(tracker, "snapshot", lambda: tracker)())
    except Exception:
        pass
    return jsonify({"status": "ok", "progress": progress})
