"""
共享工具函数 — 供各 Blueprint 引用。
"""

import os
import sys
import time
import threading
import subprocess
from pathlib import Path

from src.utils import extract_json, load_json

from lx_web.shared.state import (
    PROJECT_ROOT,
    _agent,
    _system_info,
    READABLE_FILES,
    _restart_lock,
    _restart_state,
    _autonomy_lock,
    _autonomy_state,
    _autonomy_thread,
    _autonomy_tick_lock,
    AUTONOMY_RUNS_FILE,
    AUTONOMY_LEARNING_PLAN_FILE,
    AUTONOMY_DEFAULT_INTERVAL,
    DEFAULT_LEARNING_TOPICS,
    _goal_system_lock,
    _goal_system,
    _motivation_system,
)
from lx_web.shared.sse import _emit_event


# ---------------------------------------------------------------------------
# Agent 延迟初始化
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
# 文件读取工具
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 重启相关
# ---------------------------------------------------------------------------

def _restart_snapshot() -> dict:
    with _restart_lock:
        return dict(_restart_state)


def _restart_process() -> None:
    """Start a fresh web process after this one releases its port."""
    import subprocess

    with _restart_lock:
        reason = _restart_state.get("reason") or "source_changed"
    _emit_event("runtime.restarting", {"reason": reason}, source="web")

    host = os.environ.get("LX_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("LX_WEB_PORT", "8088"))
    argv = [sys.executable] + sys.argv
    project_root = str(PROJECT_ROOT)
    code = f"""import os, socket, sys, time, traceback
host={host!r}
port={port!r}
argv={argv!r}
project_root={project_root!r}
log_path=os.path.join(project_root, "memory", "runtime_restart.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
with open(log_path, "a", encoding="utf-8") as log:
    log.write(f"restart child boot {{time.time()}} argv={{argv!r}}\\n")
    log.flush()
    try:
        deadline=time.time()+20
        while time.time()<deadline:
            s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.settimeout(0.2)
                if s.connect_ex((host, port)) != 0:
                    break
            finally:
                s.close()
            time.sleep(0.25)
        os.chdir(project_root)
        log.write(f"exec web {{time.time()}}\\n")
        log.flush()
        os.execv(argv[0], argv)
    except Exception:
        traceback.print_exc(file=log)
        log.flush()
"""
    log_file = (PROJECT_ROOT / "memory" / "runtime_restart.log").open("ab", buffering=0)
    subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        close_fds=True,
        start_new_session=True,
    )
    os._exit(0)


def _schedule_restart(reason: str, delay_seconds: float = 1.5) -> dict:
    """Schedule a reliable process restart after the current response returns."""
    if os.environ.get("LX_DISABLE_AUTO_RESTART") == "1":
        return {"status": "disabled", "reason": reason}

    with _restart_lock:
        if _restart_state["pending"]:
            return {"status": "already_pending", **dict(_restart_state)}
        now = time.time()
        _restart_state.update({
            "pending": True,
            "reason": reason,
            "scheduled_at": now,
            "restart_at": now + delay_seconds,
        })

    _emit_event("runtime.restart_scheduled",
                {"reason": reason, "delay_seconds": delay_seconds},
                source="web")
    timer = threading.Timer(delay_seconds, _restart_process)
    timer.daemon = True
    timer.start()
    return {"status": "scheduled", **_restart_snapshot()}


def _result_changed_source(result) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("changed") is True:
        return True
    if result.get("status") == "success" and (
        result.get("file_path") or result.get("fallback_target") or result.get("changed_files")
    ):
        return True
    for key in ("fallback_result", "primary_result"):
        if _result_changed_source(result.get(key)):
            return True
    for key in ("results", "direct_results"):
        items = result.get(key)
        if isinstance(items, list) and any(_result_changed_source((item or {}).get("result", item)) for item in items):
            return True
    actions = result.get("actions", [])
    if isinstance(actions, list):
        return any(_result_changed_source((action or {}).get("result")) for action in actions)
    return False


def _schedule_restart_if_source_changed(result, reason: str) -> dict | None:
    if _result_changed_source(result):
        return _schedule_restart(reason)
    return None


# ---------------------------------------------------------------------------
# 反思
# ---------------------------------------------------------------------------

def _run_reflection_async(trigger: str, context_text: str) -> None:
    """异步触发一次自我反思，把发现的能力缺口写入 learning plan。
    失败完全不影响主流程。"""
    def _worker():
        try:
            from src.self_reflection import reflect, enqueue_to_learning_plan
            reflection = reflect(str(PROJECT_ROOT), trigger=trigger, context_text=context_text)
            if reflection:
                added = enqueue_to_learning_plan(str(PROJECT_ROOT), reflection)
                if added:
                    _emit_event("learning.gap.discovered", {
                        "gap": reflection.get("gap"),
                        "suggested_topic": reflection.get("suggested_topic"),
                        "priority": reflection.get("priority"),
                        "kind": reflection.get("kind"),
                        "trigger": trigger,
                    }, source="reflection")
        except Exception as exc:
            print(f"[reflection] 失败: {exc}")

    threading.Thread(target=_worker, daemon=True, name="lx-reflection").start()


# ---------------------------------------------------------------------------
# JSON 序列化
# ---------------------------------------------------------------------------

def _jsonable(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if hasattr(value, "__dict__"):
        return _jsonable(value.__dict__)
    return str(value)


# ---------------------------------------------------------------------------
# 核心测试
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 模型配置
# ---------------------------------------------------------------------------

def _safe_public_model_config() -> dict:
    try:
        import yaml
        default_config = yaml.safe_load((PROJECT_ROOT / "config/default.yaml").read_text()) or {}
    except Exception:
        default_config = {}

    from lx_web.shared.state import MODEL_CONFIG_FILES

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
    import json as _json
    import requests as _requests

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
            "model": cfg.get("api_model", model_id.split("/")[-1]),
            "messages": [{"role": "user", "content": "ping，只回复 pong"}],
            "temperature": 0,
            "max_tokens": 128,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        started = time.time()
        try:
            resp = _requests.post(url, headers=headers, json=payload, timeout=timeout)
            elapsed = round(time.time() - started, 3)
            content = ""
            error = ""
            try:
                data = resp.json()
                if data.get("choices"):
                    content = data["choices"][0].get("message", {}).get("content", "")
                elif resp.status_code >= 400:
                    error = _json.dumps(data, ensure_ascii=False)[:500]
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


# ---------------------------------------------------------------------------
# Agent 上下文
# ---------------------------------------------------------------------------

def _agent_context(agent=None) -> dict:
    from lx_web.shared.state import IDENTITY_DOCS

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
            {"name": "源码变更后自动重启", "status": "active", "endpoint": "POST /api/runtime/restart"},
            {"name": "后台自主优化循环", "status": "active", "endpoint": "POST /api/autonomy/start"},
            {"name": "源码改动日志", "status": "active", "endpoint": "GET /api/code-changes"},
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
            "autonomy_runs": _records_summary("memory/autonomy_runs.json"),
            "code_changes": _records_summary("memory/code_change_logs.json"),
        },
        "autonomy": None,  # 由调用方填充
        "models": _safe_public_model_config(),
        "docs": docs,
    }


# ---------------------------------------------------------------------------
# 安全属性访问
# ---------------------------------------------------------------------------

def _safe_attr(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# 目标 / 动机系统
# ---------------------------------------------------------------------------

def _get_goal_system():
    """懒加载 GoalSystem（agent 没挂载它，这里独立维护）。"""
    global _goal_system
    with _goal_system_lock:
        if _goal_system is None:
            try:
                from src.goal_system import create_goal_system
                _goal_system = create_goal_system(str(PROJECT_ROOT))
            except Exception as exc:
                print(f"[lx_web] goal_system 初始化失败: {exc}")
                _goal_system = False  # 标记尝试过失败
    return _goal_system if _goal_system else None


def _get_motivation_system():
    global _motivation_system
    with _goal_system_lock:
        if _motivation_system is None:
            try:
                from src.motivation_system import create_motivation_system
                _motivation_system = create_motivation_system(str(PROJECT_ROOT))
            except Exception as exc:
                print(f"[lx_web] motivation_system 初始化失败: {exc}")
                _motivation_system = False
    return _motivation_system if _motivation_system else None
