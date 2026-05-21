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

IDENTITY_DOCS = [
    "docs/SOUL.md",
    "docs/IDENTITY.md",
    "docs/USER.md",
    "docs/AUTONOMY.md",
    "docs/CONSTITUTION.md",
]

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


def _read_excerpt(rel_path: str, limit: int = 900) -> str:
    path = PROJECT_ROOT / rel_path
    if not path.exists() or not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""
    if len(content) <= limit:
        return content
    return content[:limit].rstrip() + "\n..."


def _records_summary(rel_path: str) -> dict:
    path = PROJECT_ROOT / rel_path
    data = load_json(str(path), default=[])
    if isinstance(data, list):
        latest = data[-1] if data else None
        return {"path": rel_path, "count": len(data), "latest": latest}
    if isinstance(data, dict):
        return {"path": rel_path, "count": len(data), "latest": None}
    return {"path": rel_path, "count": 0, "latest": None}


def _agent_context(agent=None) -> dict:
    docs = []
    for rel_path in IDENTITY_DOCS:
        excerpt = _read_excerpt(rel_path)
        docs.append({
            "path": rel_path,
            "exists": bool(excerpt),
            "excerpt": excerpt,
        })

    top_dirs = []
    try:
        ignored = {".git", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
        top_dirs = sorted(
            p.name for p in PROJECT_ROOT.iterdir()
            if p.is_dir() and p.name not in ignored and not p.name.startswith(".")
        )
    except Exception:
        top_dirs = []

    key_files = [
        "src/core.py",
        "src/llm.py",
        "src/self_evolution.py",
        "src/agent_learning.py",
        "lx_web.py",
        "lx-desktop/renderer/index.html",
        "lx-desktop/renderer/app.js",
        "scripts/lx_self_evolve.py",
    ]

    degraded = bool(getattr(agent, "degraded", False)) if agent else False
    degraded_reason = getattr(agent, "degraded_reason", "") if agent else ""

    return {
        "identity": {
            "name": "冷小北",
            "host": "潘豪",
            "role": "本地自主进化 Agent / 数字共生体",
            "version": _system_info["version"],
        },
        "runtime": {
            "project_root": str(PROJECT_ROOT),
            "memory_dir": str(PROJECT_ROOT / "memory"),
            "web_entry": "lx_web.py",
            "chat_route": "POST /api/chat",
            "self_evolution_entry": "src/self_evolution.py",
            "degraded": degraded,
            "degraded_reason": degraded_reason,
        },
        "capabilities": [
            {"name": "对话", "status": "active", "endpoint": "POST /api/chat"},
            {"name": "学习 Agent 长处", "status": "active", "endpoint": "POST /api/learn-agent"},
            {"name": "自进化源码改进", "status": "active", "endpoint": "POST /api/self-evolve"},
            {"name": "经验沉淀", "status": "active", "endpoint": "GET /api/lessons"},
            {"name": "运行记录", "status": "active", "endpoint": "GET /api/runs"},
        ],
        "boundaries": [
            "不自主修改 docs/SOUL.md / docs/CONSTITUTION.md 的安全底线",
            "产生费用、采购、开通云服务、使用宿主身份必须先获授权",
            "不删除、篡改、泄露核心记忆",
            "自进化应保留验证记录与回滚路径",
        ],
        "key_files": [
            {"path": path, "exists": (PROJECT_ROOT / path).exists()}
            for path in key_files
        ],
        "top_dirs": top_dirs[:64],
        "memory": {
            "lessons": _records_summary("memory/agent_lessons.json"),
            "runs": _records_summary("memory/self_evolution_runs.json"),
        },
        "docs": docs,
    }


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
            "agent_context": "GET /api/agent-context",
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


@app.route("/api/agent-context", methods=["GET"])
def api_agent_context():
    agent = _get_agent()
    health = "healthy" if agent is not None else "unhealthy"
    context = _agent_context(agent)
    context["health"] = {
        "status": health,
        "components": {
            "web": "healthy",
            "core": health,
        },
        "uptime": int(time.time() - _system_info["start_time"]),
    }
    code = 200 if agent is not None else 503
    return jsonify({"status": "ok" if agent is not None else "failed", "context": context}), code


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
