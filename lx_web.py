"""
冷小北 Web 界面 — Flask 后端
启动: python3 lx_web.py  (默认端口 5001)
"""

import sys
import os
import json
import time
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify, request, send_from_directory, make_response
from src.utils import extract_json, load_json

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

MODEL_CONFIG_FILES = [
    "config/default.yaml",
    "config/development.yaml",
    "config/production.yaml",
    "config/config.json",
]

READABLE_FILES = {
    "config/default.yaml",
    "config/development.yaml",
    "config/production.yaml",
    "config/config.json",
    "src/llm.py",
    "src/core.py",
    "src/self_evolution.py",
    "src/learned_capabilities.py",
    "memory/agent_lessons.json",
    "memory/self_evolution_runs.json",
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


def _read_allowed_file(rel_path: str, limit: int = 12000) -> dict:
    normalized = rel_path.replace("\\", "/").lstrip("./")
    if normalized not in READABLE_FILES:
        return {
            "status": "blocked",
            "path": normalized,
            "error": "该文件未在前端可读白名单中",
            "allowed": sorted(READABLE_FILES),
        }

    path = (PROJECT_ROOT / normalized).resolve()
    if not str(path).startswith(str(PROJECT_ROOT)):
        return {"status": "blocked", "path": normalized, "error": "路径越界"}
    if not path.exists() or not path.is_file():
        return {"status": "missing", "path": normalized, "error": "文件不存在"}

    content = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(content) > limit
    return {
        "status": "ok",
        "path": normalized,
        "size": path.stat().st_size,
        "modified_at": path.stat().st_mtime,
        "truncated": truncated,
        "content": content[:limit],
    }


def _records_summary(rel_path: str) -> dict:
    path = PROJECT_ROOT / rel_path
    data = load_json(str(path), default=[])
    if isinstance(data, list):
        latest = data[-1] if data else None
        return {"path": rel_path, "count": len(data), "latest": latest}
    if isinstance(data, dict):
        return {"path": rel_path, "count": len(data), "latest": None}
    return {"path": rel_path, "count": 0, "latest": None}


def _safe_public_model_config() -> dict:
    try:
        import yaml
        default_config = yaml.safe_load((PROJECT_ROOT / "config/default.yaml").read_text()) or {}
    except Exception:
        default_config = {}

    model_cfg = default_config.get("models", {}) if isinstance(default_config, dict) else {}
    enabled = model_cfg.get("enabled") or []
    public = {
        "config_files": [
            {"path": rel, "exists": (PROJECT_ROOT / rel).exists()}
            for rel in MODEL_CONFIG_FILES
        ],
        "configured_default": model_cfg.get("default", ""),
        "enabled": enabled,
        "temperature": model_cfg.get("temperature"),
        "max_tokens": model_cfg.get("max_tokens"),
        "timeout": model_cfg.get("timeout"),
        "max_retries": model_cfg.get("max_retries"),
        "key_sources": [
            "环境变量 LLM_API_KEY + LLM_PROVIDER",
            "config/default.yaml models.providers",
            "~/.openclaw/openclaw.json",
        ],
        "providers": {},
        "status_text": "",
        "performance_text": "",
    }

    try:
        from src import llm
        for model_id in enabled:
            cfg = llm.MODELS.get(model_id, {})
            provider = cfg.get("provider", "unknown")
            public["providers"].setdefault(provider, {
                "has_key": bool(llm._get_key(provider)),
                "models": [],
            })
            public["providers"][provider]["models"].append({
                "id": model_id,
                "base_url": cfg.get("base_url", ""),
                "context_window": cfg.get("context_window"),
                "max_output": cfg.get("max_output"),
                "strengths": cfg.get("strengths", []),
                "cost_tier": cfg.get("cost_tier"),
            })
        public["status_text"] = llm.model_status()
        public["performance_text"] = llm.get_performance_report()
    except Exception as exc:
        public["error"] = str(exc)

    return public


def _ping_enabled_models(max_models: int = 5, timeout: int = 20) -> dict:
    config = _safe_public_model_config()
    enabled = list(config.get("enabled") or [])[:max_models]
    results = []

    try:
        from src import llm
    except Exception as exc:
        return {
            "status": "failed",
            "error": f"LLM 模块加载失败: {exc}",
            "results": results,
        }

    for model_id in enabled:
        cfg = llm.MODELS.get(model_id)
        if not cfg:
            results.append({
                "model": model_id,
                "ok": False,
                "error": "模型未在 src/llm.py MODELS 中定义",
            })
            continue

        provider = cfg.get("provider", "")
        api_key = llm._get_key(provider)
        if not api_key:
            results.append({
                "model": model_id,
                "provider": provider,
                "ok": False,
                "error": "provider 未配置 API Key",
            })
            continue

        url = f"{cfg['base_url']}/chat/completions"
        payload = {
            "model": model_id.split("/")[-1],
            "messages": [{"role": "user", "content": "ping，只回复 pong"}],
            "temperature": 0,
            "max_tokens": 32,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        started = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            elapsed = round(time.time() - started, 3)
            content = ""
            error = ""
            try:
                data = resp.json()
                if data.get("choices"):
                    content = data["choices"][0].get("message", {}).get("content", "")
                elif resp.status_code >= 400:
                    error = json.dumps(data, ensure_ascii=False)[:500]
            except Exception:
                error = resp.text[:500]

            ok = resp.status_code == 200 and bool(content.strip())
            results.append({
                "model": model_id,
                "provider": provider,
                "ok": ok,
                "status_code": resp.status_code,
                "elapsed_seconds": elapsed,
                "reply": content.strip()[:200],
                "error": "" if ok else error,
            })
        except Exception as exc:
            results.append({
                "model": model_id,
                "provider": provider,
                "ok": False,
                "elapsed_seconds": round(time.time() - started, 3),
                "error": str(exc),
            })

    return {
        "status": "ok",
        "tested_at": time.time(),
        "count": len(results),
        "success_count": sum(1 for item in results if item.get("ok")),
        "results": results,
    }


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
            {"name": "模型配置检查", "status": "active", "endpoint": "GET /api/model-config"},
            {"name": "实时读取白名单文件", "status": "active", "endpoint": "GET /api/file-excerpt"},
            {"name": "前端本地动作", "status": "active", "endpoint": "POST /api/local-action"},
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
        "models": _safe_public_model_config(),
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
            "model_config": "GET /api/model-config",
            "file_excerpt": "GET /api/file-excerpt?path=config/default.yaml",
            "local_action": "POST /api/local-action",
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


@app.route("/api/model-config", methods=["GET"])
def api_model_config():
    _get_agent()
    return jsonify({"status": "ok", "model_config": _safe_public_model_config()})


@app.route("/api/file-excerpt", methods=["GET"])
def api_file_excerpt():
    rel_path = request.args.get("path", "").strip()
    limit = min(max(int(request.args.get("limit", 12000)), 1000), 50000)
    result = _read_allowed_file(rel_path, limit=limit)
    code = 200 if result.get("status") == "ok" else 400
    return jsonify(result), code


@app.route("/api/local-action", methods=["POST"])
def api_local_action():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()

    if action == "model_config":
        return jsonify({
            "status": "ok",
            "action": action,
            "title": "实时模型配置",
            "result": _safe_public_model_config(),
        })

    if action == "health":
        agent = _get_agent()
        core = "healthy" if agent is not None else "unhealthy"
        return jsonify({
            "status": "ok",
            "action": action,
            "title": "实时健康检查",
            "result": {
                "status": "healthy" if agent is not None else "unhealthy",
                "components": {"web": "healthy", "core": core},
                "uptime": int(time.time() - _system_info["start_time"]),
            },
        })

    if action == "read_file":
        rel_path = str(data.get("path", "")).strip()
        result = _read_allowed_file(rel_path)
        code = 200 if result.get("status") == "ok" else 400
        return jsonify({
            "status": "ok" if code == 200 else "failed",
            "action": action,
            "title": f"读取文件: {rel_path}",
            "result": result,
        }), code

    return jsonify({
        "status": "failed",
        "error": f"未知本地动作: {action}",
        "available_actions": ["model_config", "health", "read_file"],
    }), 400


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
        result = _agentic_chat(agent, message)
        return jsonify({"status": "ok", **result})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


def _agentic_chat(agent, message: str) -> dict:
    """Let the model decide whether to use local tools, then execute allowed tools."""
    try:
        from src import llm

        decision_prompt = f"""你是冷小北的本地指令调度层。宿主刚发来一条指令。

你拥有以下后端工具权限，应该自主判断是否调用工具，而不是让宿主手动贴文件或自己执行命令。

可用工具：
1. model_config: 读取脱敏后的真实模型配置和 provider key 状态。args={{}}
2. ping_models: 对启用模型发起真实 ping 测试。args={{"max_models": 1-5, "timeout": 秒数}}
3. read_file: 读取白名单文件。args={{"path": "config/default.yaml|src/llm.py|src/core.py|src/self_evolution.py|src/learned_capabilities.py|memory/agent_lessons.json|memory/self_evolution_runs.json"}}
4. health: 读取实时健康状态。args={{}}
5. apply_pending: 应用下一条 pending lesson，真实修改源码并验证。args={{}}
6. self_evolve: 学习方向并自进化。args={{"topic": "学习方向", "url": "可选URL"}}
7. run_tests: 运行本地编译和核心测试。args={{}}
8. autonomy_run: 按宿主方向自主扫描、计划、执行、验证。args={{"direction": "方向"}}

硬边界：
- 不修改 docs/SOUL.md / docs/CONSTITUTION.md / docs/AUTONOMY.md。
- 不做支付、采购、发布、推送、外部账号操作。
- 不删除核心记忆。
- 需要这些高风险动作时，返回 final 说明需要宿主确认。

判断规则：
- 如果宿主是在下命令、要求检查、测试、读取、应用、优化、修复，就优先调用工具。
- 如果只是闲聊或概念讨论，可以不调用工具。
- 不要说“我没有文件读取工具/你贴给我”，因为你有上述后端工具。

只返回 JSON，不要 Markdown：
{{
  "mode": "tool" 或 "chat",
  "tool_calls": [{{"name": "工具名", "args": {{...}}}}],
  "final": "如果不需要工具，直接回复；如果需要工具，这里留空"
}}

宿主指令：{message}
"""
        raw = llm.chat(
            decision_prompt,
            system="你是冷小北的工具调度器。只返回JSON。",
            temperature=0.1,
            use_cache=False,
        )
        decision = extract_json(raw)
    except Exception as exc:
        return {"reply": agent.chat(message), "source": "fallback_chat", "planner_error": str(exc)}

    calls = decision.get("tool_calls") or []
    if decision.get("mode") != "tool" or not calls:
        final = decision.get("final") or agent.chat(message)
        return {"reply": final, "source": "plain_chat"}

    observations = []
    for call in calls[:3]:
        if not isinstance(call, dict):
            continue
        observations.append(_execute_agent_tool(agent, call.get("name", ""), call.get("args") or {}, message))

    try:
        from src import llm

        final_prompt = f"""宿主指令：{message}

你刚刚自主调用了以下后端工具，得到真实结果：
{json.dumps(observations, ensure_ascii=False, indent=2)[:12000]}

请用中文简洁汇报：
- 实际执行了什么
- 真实结果是什么
- 如果失败，下一步该怎么处理
不要声称没有工具。不要把默认统计值说成真实测试。"""
        reply = llm.chat(
            final_prompt,
            system="你是冷小北，基于真实工具结果向宿主汇报。",
            temperature=0.2,
            use_cache=False,
        )
    except Exception:
        reply = _format_tool_observations(observations)

    return {
        "reply": reply,
        "source": "agentic_tools",
        "tool_calls": calls[:3],
        "tool_results": observations,
    }


def _execute_agent_tool(agent, name: str, args: dict, original_message: str) -> dict:
    started = time.time()
    try:
        if name == "model_config":
            result = _safe_public_model_config()
        elif name == "ping_models":
            max_models = int(args.get("max_models") or 5)
            timeout = int(args.get("timeout") or 20)
            result = _ping_enabled_models(max_models=max(1, min(max_models, 5)), timeout=max(5, min(timeout, 30)))
        elif name == "read_file":
            result = _read_allowed_file(str(args.get("path", "")).strip())
        elif name == "health":
            result = {
                "status": "healthy" if agent is not None else "unhealthy",
                "components": {"web": "healthy", "core": "healthy" if agent is not None else "unhealthy"},
                "uptime": int(time.time() - _system_info["start_time"]),
            }
        elif name == "apply_pending":
            result = agent.evolve_from_lessons()
        elif name == "self_evolve":
            topic = str(args.get("topic") or original_message).strip()
            url = str(args.get("url") or "").strip()
            result = agent.self_evolve(topic, url=url)
        elif name == "run_tests":
            result = _run_core_tests()
        elif name == "autonomy_run":
            direction = str(args.get("direction") or original_message).strip()
            result = {"report": agent.run_autonomously(direction)}
        else:
            result = {"status": "failed", "error": f"未知工具: {name}"}
        return {
            "tool": name,
            "ok": not (isinstance(result, dict) and result.get("status") == "failed"),
            "elapsed_seconds": round(time.time() - started, 3),
            "result": result,
        }
    except Exception as exc:
        return {
            "tool": name,
            "ok": False,
            "elapsed_seconds": round(time.time() - started, 3),
            "error": str(exc),
        }


def _run_core_tests() -> dict:
    import subprocess

    commands = [
        ["python3", "-m", "compileall", "-q", "src", "lx_web.py"],
        ["pytest", "tests/test_core_modules.py", "-q"],
    ]
    outputs = []
    for cmd in commands:
        started = time.time()
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        outputs.append({
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "elapsed_seconds": round(time.time() - started, 3),
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        })
        if proc.returncode != 0:
            return {"status": "failed", "outputs": outputs}
    return {"status": "success", "outputs": outputs}


def _format_tool_observations(observations: list) -> str:
    lines = ["已按指令自主调用后端工具："]
    for obs in observations:
        lines.append(f"- {obs.get('tool')}: {'成功' if obs.get('ok') else '失败'}，耗时 {obs.get('elapsed_seconds')}s")
        if "error" in obs:
            lines.append(f"  错误: {obs['error']}")
    return "\n".join(lines)


def _format_model_config_reply(model_config: dict) -> str:
    lines = [
        "我可以直接读取本地模型配置，不需要你贴文件。",
        "",
        f"- 配置文件: config/default.yaml",
        f"- 默认模型: {model_config.get('configured_default') or '未配置'}",
        f"- 启用模型: {', '.join(model_config.get('enabled') or [])}",
        f"- temperature: {model_config.get('temperature')}",
        f"- max_tokens: {model_config.get('max_tokens')}",
        f"- timeout: {model_config.get('timeout')} 秒",
        f"- max_retries: {model_config.get('max_retries')}",
        "",
        "Provider 状态:",
    ]
    providers = model_config.get("providers") or {}
    for name, info in providers.items():
        key_state = "有 key" if info.get("has_key") else "无 key"
        model_ids = [item.get("id", "") for item in info.get("models", [])]
        lines.append(f"- {name}: {key_state}; {', '.join(model_ids)}")

    status_text = model_config.get("status_text")
    if status_text:
        lines.extend(["", "模型状态:", status_text])
    return "\n".join(lines)

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
