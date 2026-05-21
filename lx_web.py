"""
冷小北 Web 界面 — Flask 后端
启动: python3 lx_web.py  (默认端口 5001)
"""

import sys
import os
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify, request, send_from_directory, make_response
from src.utils import load_json

app = Flask(__name__, static_folder=None)


@app.after_request
def _add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.before_request
def _handle_options():
    if request.method == "OPTIONS":
        return make_response("", 200)

_agent = None
_system_info = {
    "platform": sys.platform,
    "python_version": sys.version,
    "start_time": time.time(),
    "version": "Phase 2.1",
}

# ---------------------------------------------------------------------------
# 延迟初始化 Agent（避免启动时加载所有模块）
# ---------------------------------------------------------------------------

def _get_agent():
    global _agent
    if _agent is None:
        try:
            from src.core import LengXiaobei
            _agent = LengXiaobei()
            _agent.start()
        except Exception as e:
            print(f"[lx_web] Agent 初始化失败: {e}")
            _agent = None
    return _agent


# ---------------------------------------------------------------------------
# 静态文件 — 复用 lx-desktop 前端
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    desktop_dir = PROJECT_ROOT / "lx-desktop" / "renderer"
    if desktop_dir.exists() and (desktop_dir / "index.html").exists():
        return send_from_directory(str(desktop_dir), "index.html")
    return jsonify({
        "name": "冷小北 · 数字生命体",
        "version": _system_info["version"],
        "status": "running",
        "endpoints": {
            "chat": "POST /api/chat",
            "status": "GET /api/status",
            "health": "GET /api/health",
            "evolution": "POST /api/evolution",
            "self_evolve": "POST /api/self-evolve",
            "lessons": "GET /api/lessons",
            "runs": "GET /api/runs",
        }
    })

@app.route("/<path:path>")
def static_files(path):
    desktop_dir = PROJECT_ROOT / "lx-desktop" / "renderer"
    if desktop_dir.exists():
        return send_from_directory(str(desktop_dir), path)
    return jsonify({"error": "not found"}), 404


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------

@app.route("/api/status", methods=["GET"])
def api_status():
    agent = _get_agent()
    info = dict(_system_info)
    info["uptime"] = int(time.time() - _system_info["start_time"])

    if agent:
        try:
            if hasattr(agent, "guardian_facade") and agent.guardian_facade:
                info["kairos_active"] = getattr(
                    getattr(agent.guardian_facade, "kairos", None),
                    "is_running", lambda: False
                )()
            if hasattr(agent, "memory_facade"):
                info["memory_ok"] = agent.memory_facade is not None
            if hasattr(agent, "evolution_facade"):
                info["evolution_ok"] = agent.evolution_facade is not None
        except Exception:
            pass

    return jsonify(info)

@app.route("/api/health", methods=["GET"])
def api_health():
    components = {"web": "healthy"}
    agent = _get_agent()
    if agent is None:
        components["core"] = "unhealthy"
        return jsonify({"status": "unhealthy", "components": components}), 503
    components["core"] = "healthy"
    return jsonify({"status": "healthy", "components": components})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "message 为空"}), 400

    try:
        response = agent.chat(message)
        return jsonify({"reply": response, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500

@app.route("/api/evolution", methods=["POST"])
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


@app.route("/api/self-evolve", methods=["POST"])
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
        return jsonify({"result": result, "status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


@app.route("/api/learn-agent", methods=["POST"])
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


@app.route("/api/lessons", methods=["GET"])
def api_lessons():
    lessons_file = PROJECT_ROOT / "memory" / "agent_lessons.json"
    lessons = load_json(str(lessons_file), default=[])
    if not isinstance(lessons, list):
        lessons = []
    return jsonify({"lessons": lessons, "count": len(lessons), "status": "ok"})


@app.route("/api/runs", methods=["GET"])
def api_runs():
    runs_file = PROJECT_ROOT / "memory" / "self_evolution_runs.json"
    runs = load_json(str(runs_file), default=[])
    if not isinstance(runs, list):
        runs = []
    return jsonify({"runs": runs, "count": len(runs), "status": "ok"})

@app.route("/api/discover", methods=["POST"])
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

# ============================================================================
# 入口
# ============================================================================

def main():
    port = int(os.environ.get("LX_WEB_PORT", 8088))
    host = os.environ.get("LX_WEB_HOST", "0.0.0.0")

    print(f"\n{'='*50}")
    print(f"  冷小北 Web 界面")
    print(f"  地址: http://{host}:{port}")
    print(f"{'='*50}\n")

    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n[lx_web] 退出")

if __name__ == "__main__":
    main()
