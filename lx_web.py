"""
冷小北 Web 界面 — Flask 后端
启动: python3 lx_web.py  (默认端口 5001)
"""

import sys
import os
import json
import time
import queue
import requests
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, Response, jsonify, request, send_from_directory, make_response
from src.utils import extract_json, load_json

# 复用 kairos 已实现的 EventBus（带持久化、历史、统计）
try:
    from src.kairos import events as kairos_events
    _KAIROS_EVENTS_OK = True
except Exception:
    kairos_events = None
    _KAIROS_EVENTS_OK = False

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# SSE 基础设施：把 kairos.events 的回调订阅模式适配到 Queue 模式
# ---------------------------------------------------------------------------

_sse_subscribers: "list[queue.Queue]" = []
_sse_lock = threading.Lock()
_sse_handler_registered = False


def _ensure_event_bus() -> None:
    """确保 EventBus 已初始化并注册了 SSE 转发 handler。"""
    global _sse_handler_registered
    if not _KAIROS_EVENTS_OK:
        return
    try:
        kairos_events.get_event_bus()
    except kairos_events.EventBusNotInitialized:
        kairos_events.init_event_bus(str(PROJECT_ROOT))

    if not _sse_handler_registered:
        def _sse_fanout(record):
            payload = record.to_dict()
            with _sse_lock:
                dead = []
                for q in _sse_subscribers:
                    try:
                        q.put_nowait(payload)
                    except queue.Full:
                        dead.append(q)
                for q in dead:
                    if q in _sse_subscribers:
                        _sse_subscribers.remove(q)
        kairos_events.subscribe("*", _sse_fanout)
        _sse_handler_registered = True


def _emit_event(event_type: str, data: "dict | None" = None, source: str = "web") -> None:
    """安全发布事件。EventBus 未初始化或异常时静默跳过。"""
    if not _KAIROS_EVENTS_OK:
        return
    try:
        _ensure_event_bus()
        kairos_events.emit(event_type, data or {}, source=source)
    except Exception:
        pass


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
    "memory/autonomy_runs.json",
    "memory/autonomy_learning_plan.json",
    "memory/code_change_logs.json",
}

AUTONOMY_RUNS_FILE = PROJECT_ROOT / "memory" / "autonomy_runs.json"
AUTONOMY_LEARNING_PLAN_FILE = PROJECT_ROOT / "memory" / "autonomy_learning_plan.json"
AUTONOMY_DEFAULT_INTERVAL = int(os.environ.get("LX_AUTONOMY_INTERVAL", "300"))
_autonomy_lock = threading.Lock()
_autonomy_state = {
    "enabled": False,
    "running": False,
    "interval_seconds": AUTONOMY_DEFAULT_INTERVAL,
    "thread_alive": False,
    "tick_count": 0,
    "last_tick_at": None,
    "last_result": None,
}
_autonomy_thread = None
_autonomy_tick_lock = threading.Lock()
_restart_lock = threading.Lock()
_restart_state = {
    "pending": False,
    "reason": "",
    "scheduled_at": None,
    "restart_at": None,
}

DEFAULT_LEARNING_TOPICS = [
    {
        "topic": "自主学习 OpenHands 的任务拆解、工作区执行和错误恢复能力，并提炼一个可落地改进",
        "url": "https://github.com/All-Hands-AI/OpenHands",
    },
    {
        "topic": "自主学习 Aider 的 git 感知代码修改、最小补丁和提交前验证能力，并提炼一个可落地改进",
        "url": "https://github.com/Aider-AI/aider",
    },
    {
        "topic": "自主学习 Continue 的 IDE 上下文、代码库索引和开发者交互设计能力，并提炼一个可落地改进",
        "url": "https://github.com/continuedev/continue",
    },
    {
        "topic": "自主学习 AutoGen 的多 Agent 协作、角色分工和任务交接机制，并提炼一个可落地改进",
        "url": "https://github.com/microsoft/autogen",
    },
    {
        "topic": "自主学习 Claude Code 的计划执行、工具调用反馈和长任务汇报体验，并提炼一个可落地改进",
        "url": "",
    },
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


def _atomic_record_list(path: Path, record: dict, max_records: int = 200) -> None:
    from src.utils import atomic_write_json

    path.parent.mkdir(parents=True, exist_ok=True)
    records = load_json(str(path), default=[])
    if not isinstance(records, list):
        records = []
    records.append(record)
    atomic_write_json(str(path), records[-max_records:])
    _emit_event("memory.updated",
                {"file": path.name, "count": len(records[-max_records:]),
                 "latest_id": record.get("id") if isinstance(record, dict) else None},
                source="memory")


def _load_pending_lessons(limit: int = 5) -> list:
    lessons = load_json(str(PROJECT_ROOT / "memory" / "agent_lessons.json"), default=[])
    if not isinstance(lessons, list):
        return []
    return [item for item in lessons if item.get("status") == "pending"][:limit]


def _load_learning_plan() -> list:
    plan = load_json(str(AUTONOMY_LEARNING_PLAN_FILE), default=None)
    if not isinstance(plan, list) or not plan:
        now = time.time()
        plan = []
        for index, item in enumerate(DEFAULT_LEARNING_TOPICS):
            plan.append({
                "id": f"learn_{index + 1}",
                "topic": item["topic"],
                "url": item.get("url", ""),
                "status": "pending",
                "created_at": now,
                "last_attempt_at": None,
                "lesson_id": "",
                "error": "",
            })
        from src.utils import atomic_write_json
        atomic_write_json(str(AUTONOMY_LEARNING_PLAN_FILE), plan)
    return plan


def _save_learning_plan(plan: list) -> None:
    from src.utils import atomic_write_json

    atomic_write_json(str(AUTONOMY_LEARNING_PLAN_FILE), plan)


def _next_learning_topic() -> dict:
    plan = _load_learning_plan()
    pending = [item for item in plan if item.get("status") in ("pending", "failed")]
    if pending:
        pending.sort(key=lambda item: item.get("last_attempt_at") or 0)
        return pending[0]
    plan.sort(key=lambda item: item.get("last_attempt_at") or 0)
    item = dict(plan[0])
    item["status"] = "pending"
    return item


def _mark_learning_topic(topic_id: str, updates: dict) -> None:
    plan = _load_learning_plan()
    found = False
    for item in plan:
        if item.get("id") == topic_id:
            item.update(updates)
            found = True
            break
    if not found:
        item = {"id": topic_id, **updates}
        plan.append(item)
    _save_learning_plan(plan)


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


def _apply_trivial_improvement(record) -> dict:
    issue = getattr(record, "issue", "")
    rel_file = getattr(record, "file", "")
    if "文件末尾缺少换行" not in issue:
        return {"status": "skipped", "reason": "not_trivial"}

    path = (PROJECT_ROOT / rel_file).resolve()
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError:
        return {"status": "failed", "error": "目标文件不存在或路径越界", "file": rel_file}
    if not path.is_file():
        return {"status": "failed", "error": "目标文件不存在或路径越界", "file": rel_file}

    from src.code_change_log import CodeChangeLogger

    logger = CodeChangeLogger(str(PROJECT_ROOT))
    before = logger.snapshot([rel_file])
    original = path.read_bytes()
    if original.endswith(b"\n"):
        return {"status": "skipped", "reason": "already_fixed", "file": rel_file}

    tmp = path.with_name(f".{path.name}.tmp-{int(time.time() * 1000)}")
    tmp.write_bytes(original + b"\n")
    os.replace(tmp, path)
    result = {"status": "success", "file": rel_file, "change": "append_final_newline"}
    logger.record(
        actor="lengxiaobei",
        trigger="autonomy.trivial_improvement",
        summary=f"自动修复 {rel_file}: 文件末尾补换行",
        before=before,
        after_paths=[rel_file],
        result=result,
        metadata={
            "issue": issue,
            "source": getattr(record, "source", "curator"),
            "signature": getattr(record, "signature", ""),
        },
    )
    return result


def _test_failure_text(test_result: dict, limit: int = 3000) -> str:
    outputs = test_result.get("outputs") or []
    chunks = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        if item.get("returncode") == 0:
            continue
        chunks.append(f"$ {item.get('command', '')}")
        if item.get("stdout"):
            chunks.append(str(item["stdout"]))
        if item.get("stderr"):
            chunks.append(str(item["stderr"]))
    return "\n".join(chunks)[-limit:]


def _extract_repair_targets(test_result: dict, limit: int = 3) -> list:
    """从失败输出中提取可自主修复的源码文件。只允许项目内 src/*.py 和 lx_web.py。"""
    import re

    text = _test_failure_text(test_result, limit=6000)
    candidates = []
    patterns = [
        r"['\"]((?:src/[^'\"]+|lx_web)\.py)['\"]",
        r"File \"([^\"]+)\"",
        r"((?:src|tests)/[A-Za-z0-9_./-]+\.py|lx_web\.py)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            raw = str(match).strip()
            path = Path(raw)
            try:
                if path.is_absolute():
                    rel = path.resolve().relative_to(PROJECT_ROOT)
                    raw = str(rel)
            except Exception:
                continue
            raw = raw.replace("\\", "/").strip("./")
            if raw == "lx_web.py" or raw.startswith("src/"):
                if (PROJECT_ROOT / raw).is_file() and raw not in candidates:
                    candidates.append(raw)
            if len(candidates) >= limit:
                return candidates
    return candidates


def _attempt_autonomous_repair(agent, test_result: dict, direction: str = "") -> dict:
    """把失败自检转成真实 bugfix 改进任务，执行后立刻复测。"""
    targets = _extract_repair_targets(test_result)
    failure_text = _test_failure_text(test_result)
    if not targets:
        return {
            "status": "skipped",
            "reason": "未能从测试输出定位到可自主修改的源码文件",
            "failure": failure_text,
        }

    from src.evolution.models import ImprovementRecord

    issue = "\n".join([
        "核心自检失败，需要自主修复当前真实 bug。",
        f"宿主方向: {direction or '持续自主优化'}",
        "要求: 最小改动，修复失败原因，不重写架构，修复后必须通过核心测试。",
        "失败摘要:",
        failure_text,
    ])
    improvements = [
        ImprovementRecord(
            file=target,
            issue=issue,
            priority="high",
            source="autonomy_self_repair",
            type="bug",
            suggestion="根据失败输出定位根因并做最小修复。",
            confidence=0.9,
            severity="major",
            category="bugfix",
        )
        for target in targets
    ]

    result = agent.execute_evolution_tasks(improvements)
    verify = _run_core_tests()
    success = result.get("success_count", 0) > 0 and verify.get("status") == "success"
    return {
        "status": "success" if success else "failed",
        "targets": targets,
        "failure": failure_text,
        "result": _jsonable(result),
        "verification": verify,
    }


def _autonomy_snapshot() -> dict:
    with _autonomy_lock:
        state = dict(_autonomy_state)
        state["thread_alive"] = bool(_autonomy_thread and _autonomy_thread.is_alive())
    state["pending_lessons"] = len(_load_pending_lessons(limit=1000))
    state["runs"] = _records_summary("memory/autonomy_runs.json")
    learning_plan = _load_learning_plan()
    state["learning"] = {
        "plan_count": len(learning_plan),
        "pending_count": sum(1 for item in learning_plan if item.get("status") == "pending"),
        "learned_count": sum(1 for item in learning_plan if item.get("status") == "learned"),
        "latest": max(learning_plan, key=lambda item: item.get("last_attempt_at") or 0) if learning_plan else None,
    }
    return state


def _autonomy_tick(reason: str = "manual", direction: str = "") -> dict:
    if not _autonomy_tick_lock.acquire(blocking=False):
        return {
            "status": "busy",
            "reason": reason,
            "message": "已有一次自主优化正在运行，本次跳过。",
            "started_at": time.time(),
        }

    agent = _get_agent()
    started = time.time()
    _emit_event("autonomy.tick.started", {"reason": reason, "direction": direction}, source="autonomy")
    try:
        record = {
            "id": f"autonomy_{int(started)}",
            "reason": reason,
            "direction": direction or "持续自主优化",
            "started_at": started,
            "actions": [],
            "status": "running",
        }

        if agent is None:
            record["status"] = "failed"
            record["error"] = "Agent 未就绪"
        else:
            initial_check = _run_core_tests()
            record["actions"].append({
                "type": "self_check",
                "phase": "preflight",
                "result": initial_check,
            })
            if initial_check.get("status") == "failed":
                repair = _attempt_autonomous_repair(agent, initial_check, direction)
                record["actions"].append({
                    "type": "autonomous_repair",
                    "result": repair,
                })
                if repair.get("status") != "success":
                    record["status"] = "failed"
                    record["next_step"] = "核心自检失败且自主修复未成功，需要下一轮继续优先修复。"

            if record["status"] == "running":
                pending = _load_pending_lessons()
                if pending:
                    result = agent.evolve_from_lessons()
                    record["actions"].append({
                        "type": "apply_pending_lesson",
                        "lesson_id": pending[0].get("id"),
                        "topic": pending[0].get("topic"),
                        "result": result,
                    })
                    verify = _run_core_tests()
                    record["actions"].append({
                        "type": "post_lesson_verify",
                        "result": verify,
                    })
                    if verify.get("status") == "failed":
                        repair = _attempt_autonomous_repair(agent, verify, direction)
                        record["actions"].append({
                            "type": "autonomous_repair",
                            "phase": "post_lesson",
                            "result": repair,
                        })
                        if repair.get("status") != "success":
                            record["status"] = "failed"
                            record["next_step"] = "应用 lesson 后测试失败，自主修复未成功。"
                else:
                    _autonomy_optimize_or_learn(agent, record, direction)

            if record["status"] == "running":
                record["status"] = "success"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
    finally:
        _autonomy_tick_lock.release()

    record["elapsed_seconds"] = round(time.time() - started, 3)
    record["finished_at"] = time.time()
    _atomic_record_list(AUTONOMY_RUNS_FILE, record)

    with _autonomy_lock:
        _autonomy_state["tick_count"] += 1
        _autonomy_state["last_tick_at"] = record["finished_at"]
        _autonomy_state["last_result"] = record

    _emit_event("autonomy.tick.finished",
                {"record_id": record.get("id"), "status": record.get("status"),
                 "elapsed_seconds": record.get("elapsed_seconds"),
                 "reason": reason},
                source="autonomy")
    _emit_event("evolution.completed",
                {"status": record.get("status"), "run_id": record.get("id")},
                source="autonomy")

    # 反思：从这次 tick 中找出 1 个能力缺口，下次 tick 自动学
    try:
        tick_summary = json.dumps({
            "direction": direction,
            "reason": reason,
            "status": record.get("status"),
            "actions": [a.get("type") for a in (record.get("actions") or [])],
            "elapsed": record.get("elapsed_seconds"),
        }, ensure_ascii=False)
        _run_reflection_async(trigger="autonomy_tick", context_text=tick_summary)
    except Exception:
        pass

    restart = _schedule_restart_if_source_changed(record, "autonomy_tick_source_changed")
    if restart:
        record["restart"] = restart

    return record


def _autonomy_optimize_or_learn(agent, record: dict, direction: str = "") -> None:
    """自检通过后的第二段闭环：继续自主学习或策展优化。"""
    learn_topic = _next_learning_topic()
    should_learn = learn_topic.get("status") in ("pending", "failed")
    if should_learn:
        try:
            lesson = agent.learn_agent(
                learn_topic.get("topic", "自主学习优秀 Agent 的可落地能力"),
                url=learn_topic.get("url", ""),
                kind=learn_topic.get("kind", "external"),
                gap=learn_topic.get("gap", ""),
            )
            _mark_learning_topic(learn_topic.get("id", ""), {
                "status": "learned",
                "last_attempt_at": time.time(),
                "lesson_id": lesson.get("id", ""),
                "error": "",
            })
            record["actions"].append({
                "type": "autonomous_learning",
                "topic": learn_topic.get("topic", ""),
                "url": learn_topic.get("url", ""),
                "lesson": lesson,
                "next_step": "下一轮自主循环会应用该 pending lesson。",
            })
        except Exception as exc:
            _mark_learning_topic(learn_topic.get("id", ""), {
                "status": "failed",
                "last_attempt_at": time.time(),
                "error": str(exc),
            })
            record["actions"].append({
                "type": "autonomous_learning",
                "topic": learn_topic.get("topic", ""),
                "url": learn_topic.get("url", ""),
                "result": {"status": "failed", "error": str(exc)},
            })
            record["status"] = "failed"
        return

    improvements = []
    for level in ("quick", "incremental"):
        improvements = agent.run_curator_check(level)
        _emit_event("autonomy.curator.scanned",
                    {"level": level, "found": len(improvements or [])},
                    source="curator")
        if improvements:
            break

    if improvements:
        from src.evolution.models import ImprovementRecord

        selected = [
            item if hasattr(item, "abspath") else ImprovementRecord.from_curator(item)
            for item in improvements[:3]
        ]
        direct_results = []
        remaining = []
        for item in selected:
            direct = _apply_trivial_improvement(item)
            if direct.get("status") in ("success", "failed"):
                direct_results.append({"improvement": _jsonable(item), "result": direct})
            else:
                remaining.append(item)

        result = {"status": "no_changes", "results": [], "success_count": 0, "total": len(selected)}
        if remaining:
            result = agent.execute_evolution_tasks(remaining)
        if direct_results:
            result = dict(result)
            result["direct_results"] = direct_results
            result["success_count"] = result.get("success_count", 0) + sum(
                1 for item in direct_results
                if item.get("result", {}).get("status") == "success"
            )
            if result["success_count"] > 0:
                result["status"] = "success"

        record["actions"].append({
            "type": "curator_evolution",
            "improvements": _jsonable(selected),
            "result": _jsonable(result),
        })
        verify = _run_core_tests()
        record["actions"].append({
            "type": "post_evolution_verify",
            "result": verify,
        })
        if verify.get("status") == "failed":
            repair = _attempt_autonomous_repair(agent, verify, direction)
            record["actions"].append({
                "type": "autonomous_repair",
                "phase": "post_evolution",
                "result": repair,
            })
            if repair.get("status") != "success":
                record["status"] = "failed"
                record["next_step"] = "自主进化后测试失败，自主修复未成功。"
    else:
        record["actions"].append({
            "type": "self_optimization_scan",
            "result": {"status": "no_improvements", "message": "自检通过，未发现可安全执行的改进点。"},
        })


def _autonomy_loop():
    while True:
        with _autonomy_lock:
            enabled = bool(_autonomy_state["enabled"])
            interval = int(_autonomy_state["interval_seconds"])
            _autonomy_state["running"] = enabled
        if not enabled:
            with _autonomy_lock:
                _autonomy_state["running"] = False
            return

        _autonomy_tick(reason="scheduled")

        slept = 0
        while slept < interval:
            time.sleep(1)
            slept += 1
            with _autonomy_lock:
                if not _autonomy_state["enabled"]:
                    _autonomy_state["running"] = False
                    return


def _autonomy_start(interval_seconds: int = AUTONOMY_DEFAULT_INTERVAL) -> dict:
    global _autonomy_thread
    interval = max(60, min(int(interval_seconds or AUTONOMY_DEFAULT_INTERVAL), 86400))
    with _autonomy_lock:
        _autonomy_state["enabled"] = True
        _autonomy_state["running"] = True
        _autonomy_state["interval_seconds"] = interval
        alive = bool(_autonomy_thread and _autonomy_thread.is_alive())
    if not alive:
        _autonomy_thread = threading.Thread(target=_autonomy_loop, daemon=True, name="lx-autonomy-loop")
        _autonomy_thread.start()
    return _autonomy_snapshot()


def _autonomy_stop() -> dict:
    with _autonomy_lock:
        _autonomy_state["enabled"] = False
        _autonomy_state["running"] = False
    return _autonomy_snapshot()


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
        "autonomy": _autonomy_snapshot(),
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
            "runtime_status": "GET /api/runtime/status",
            "runtime_restart": "POST /api/runtime/restart",
            "autonomy_status": "GET /api/autonomy/status",
            "autonomy_learning_plan": "GET /api/autonomy/learning-plan",
            "code_changes": "GET /api/code-changes",
            "autonomy_start": "POST /api/autonomy/start",
            "autonomy_stop": "POST /api/autonomy/stop",
            "autonomy_tick": "POST /api/autonomy/tick",
            "lessons": "GET /api/lessons",
            "runs": "GET /api/runs",
        }
    })

@app.route("/<path:path>")
def static_files(path):
    # API 前缀绝不交给静态文件处理（防止未注册的 /api/* 落到 catch-all 返回 HTML）
    if path.startswith("api/") or path == "api":
        return jsonify({"error": f"未知 API: /{path}", "status": "not_found"}), 404
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
    info["restart"] = _restart_snapshot()

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


@app.route("/api/runtime/status", methods=["GET"])
def api_runtime_status():
    return jsonify({
        "status": "ok",
        "pid": os.getpid(),
        "argv": sys.argv,
        "python": sys.executable,
        "start_time": _system_info["start_time"],
        "uptime": int(time.time() - _system_info["start_time"]),
        "restart": _restart_snapshot(),
    })


@app.route("/api/runtime/restart", methods=["POST"])
def api_runtime_restart():
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "manual_restart").strip()
    delay = float(data.get("delay_seconds") or 0.8)
    delay = max(0.2, min(delay, 10.0))
    restart = _schedule_restart(reason, delay)
    return jsonify({"status": "ok", "restart": restart})


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
                "autonomy": _autonomy_snapshot(),
            },
        })

    if action == "ping_models":
        max_models = int(data.get("max_models") or 5)
        timeout = int(data.get("timeout") or 20)
        return jsonify({
            "status": "ok",
            "action": action,
            "title": "真实模型连通性测试",
            "result": _ping_enabled_models(max_models=max(1, min(max_models, 5)), timeout=max(5, min(timeout, 30))),
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
        "available_actions": ["model_config", "health", "ping_models", "read_file"],
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
9. autonomy_start: 启动后台自主优化循环。args={{"interval_seconds": 300}}
10. autonomy_stop: 停止后台自主优化循环。args={{}}
11. autonomy_status: 查看后台自主优化状态。args={{}}
12. autonomy_tick: 立刻执行一次后台自主优化循环。args={{"direction": "方向"}}
13. reload_modules: 热加载指定 Python 模块（不需要重启 lx_web）。args={{"modules": ["src.self_evolution", "src.self_reflection"]}}。先 compileall 验证语法，再 importlib.reload。失败不影响主流程。

硬边界：
- 不修改 docs/SOUL.md / docs/CONSTITUTION.md / docs/AUTONOMY.md。
- 不做支付、采购、发布、推送、外部账号操作。
- 不删除核心记忆。
- 需要这些高风险动作时，返回 final 说明需要宿主确认。

判断规则：
- 如果宿主是在下命令、要求检查、测试、读取、应用、优化、修复，就优先调用工具。
- 如果宿主说“系统不会自主优化/开始自己优化/后台运行/不用我催”，优先调用 autonomy_start 或 autonomy_tick。
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

    # 反思：扫这次对话+工具调用，找冷小北自己的能力缺口
    try:
        chat_summary = json.dumps({
            "user_message": message,
            "agent_reply": reply[:600] if isinstance(reply, str) else str(reply)[:600],
            "tools_called": [obs.get("tool") for obs in observations],
            "tool_failures": [obs for obs in observations if not obs.get("ok")],
        }, ensure_ascii=False)
        _run_reflection_async(trigger="chat", context_text=chat_summary)
    except Exception:
        pass

    return {
        "reply": reply,
        "source": "agentic_tools",
        "tool_calls": calls[:3],
        "tool_results": observations,
    }


def _execute_agent_tool(agent, name: str, args: dict, original_message: str) -> dict:
    started = time.time()
    _emit_event("chat.tool.started", {"tool": name, "args": args}, source="chat")
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
            restart = _schedule_restart_if_source_changed(result, "chat_apply_pending_source_changed")
            if restart:
                result = {**result, "restart": restart}
        elif name == "self_evolve":
            topic = str(args.get("topic") or original_message).strip()
            url = str(args.get("url") or "").strip()
            result = agent.self_evolve(topic, url=url)
            restart = _schedule_restart_if_source_changed(result, "chat_self_evolve_source_changed")
            if restart:
                result = {**result, "restart": restart}
        elif name == "run_tests":
            result = _run_core_tests()
        elif name == "autonomy_run":
            direction = str(args.get("direction") or original_message).strip()
            result = {"report": agent.run_autonomously(direction)}
        elif name == "autonomy_start":
            interval = int(args.get("interval_seconds") or AUTONOMY_DEFAULT_INTERVAL)
            result = _autonomy_start(interval)
        elif name == "autonomy_stop":
            result = _autonomy_stop()
        elif name == "autonomy_status":
            result = _autonomy_snapshot()
        elif name == "autonomy_tick":
            direction = str(args.get("direction") or original_message).strip()
            result = _autonomy_tick(reason="manual", direction=direction)
        elif name == "reload_modules":
            # 热加载已修改的源码模块，不需要重启 lx_web
            modules = args.get("modules") or ["src.self_evolution", "src.self_reflection",
                                              "src.agent_learning", "src.code_change_log"]
            result = _reload_modules(agent, modules)
        else:
            result = {"status": "failed", "error": f"未知工具: {name}"}
        ok = not (isinstance(result, dict) and result.get("status") == "failed")
        elapsed = round(time.time() - started, 3)
        _emit_event(
            "chat.tool.finished" if ok else "tool.failed",
            {"tool": name, "ok": ok, "elapsed_seconds": elapsed},
            source="chat",
        )
        return {
            "tool": name,
            "ok": ok,
            "elapsed_seconds": elapsed,
            "result": result,
        }
    except Exception as exc:
        _emit_event("tool.failed",
                    {"tool": name, "ok": False, "error": str(exc),
                     "elapsed_seconds": round(time.time() - started, 3)},
                    source="chat")
        return {
            "tool": name,
            "ok": False,
            "elapsed_seconds": round(time.time() - started, 3),
            "error": str(exc),
        }


def _reload_modules(agent, modules: list) -> dict:
    """热加载已修改的 Python 模块，重新挂载到 agent。

    高风险操作：失败可能导致 agent 进入半坏状态。
    总是先用 compileall 验证语法，再 reload。
    """
    import importlib
    import subprocess

    if not isinstance(modules, list) or not modules:
        return {"status": "failed", "error": "modules 为空或格式错误"}

    # 1. 先 compileall 验证语法
    compile_proc = subprocess.run(
        ["python3", "-m", "compileall", "-q", "src"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if compile_proc.returncode != 0:
        return {
            "status": "failed",
            "error": "语法检查失败，拒绝热加载",
            "stderr": compile_proc.stderr[-500:],
        }

    reloaded: list = []
    errors: list = []
    for mod_name in modules:
        try:
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
            reloaded.append(mod_name)
        except Exception as exc:
            errors.append({"module": mod_name, "error": str(exc)})

    # 2. 重新挂载关键对象到 agent（仅 self_evolution）
    rebind_info = {}
    if "src.self_evolution" in reloaded and agent is not None:
        try:
            from src.self_evolution import SelfEvolutionCore
            agent.self_evolution = SelfEvolutionCore(str(PROJECT_ROOT))
            rebind_info["self_evolution"] = "rebound to agent"
        except Exception as exc:
            errors.append({"module": "rebind self_evolution", "error": str(exc)})

    _emit_event("modules.reloaded", {"reloaded": reloaded, "errors": errors}, source="web")

    return {
        "status": "success" if not errors else "partial",
        "reloaded": reloaded,
        "errors": errors,
        "rebind": rebind_info,
        "message": (
            f"已热加载 {len(reloaded)} 个模块" +
            (f"，{len(errors)} 个失败" if errors else "")
        ),
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
        restart = _schedule_restart_if_source_changed(result, "self_evolve_source_changed")
        return jsonify({"result": result, "restart": restart, "status": "ok"})
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

    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    offset = max(int(request.args.get("offset", 0)), 0)

    total = len(lessons)
    # 返回最新优先，按 offset/limit 切片
    reversed_lessons = list(reversed(lessons))
    page = reversed_lessons[offset:offset + limit]

    return jsonify({
        "lessons": page,
        "count": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        "status": "ok",
    })


@app.route("/api/runs", methods=["GET"])
def api_runs():
    runs_file = PROJECT_ROOT / "memory" / "self_evolution_runs.json"
    runs = load_json(str(runs_file), default=[])
    if not isinstance(runs, list):
        runs = []

    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    offset = max(int(request.args.get("offset", 0)), 0)

    total = len(runs)
    reversed_runs = list(reversed(runs))
    page = reversed_runs[offset:offset + limit]

    return jsonify({
        "runs": page,
        "count": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        "status": "ok",
    })


@app.route("/api/code-changes", methods=["GET"])
def api_code_changes():
    records = load_json(str(PROJECT_ROOT / "memory" / "code_change_logs.json"), default=[])
    if not isinstance(records, list):
        records = []

    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    offset = max(int(request.args.get("offset", 0)), 0)
    total = len(records)
    reversed_records = list(reversed(records))
    page = reversed_records[offset:offset + limit]

    return jsonify({
        "changes": page,
        "count": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        "status": "ok",
    })


@app.route("/api/autonomy/status", methods=["GET"])
def api_autonomy_status():
    return jsonify({"status": "ok", "autonomy": _autonomy_snapshot()})


@app.route("/api/autonomy/runs", methods=["GET"])
def api_autonomy_runs():
    limit = min(max(int(request.args.get("limit", 20)), 1), 200)
    runs = load_json(str(AUTONOMY_RUNS_FILE), default=[])
    if not isinstance(runs, list):
        runs = []
    return jsonify({
        "status": "ok",
        "count": len(runs),
        "runs": runs[-limit:],
    })


@app.route("/api/autonomy/learning-plan", methods=["GET"])
def api_autonomy_learning_plan():
    plan = _load_learning_plan()
    return jsonify({
        "status": "ok",
        "count": len(plan),
        "plan": plan,
    })


@app.route("/api/autonomy/start", methods=["POST"])
def api_autonomy_start():
    data = request.get_json(silent=True) or {}
    interval = int(data.get("interval_seconds") or AUTONOMY_DEFAULT_INTERVAL)
    return jsonify({"status": "ok", "autonomy": _autonomy_start(interval)})


@app.route("/api/autonomy/stop", methods=["POST"])
def api_autonomy_stop():
    return jsonify({"status": "ok", "autonomy": _autonomy_stop()})


@app.route("/api/autonomy/tick", methods=["POST"])
def api_autonomy_tick():
    data = request.get_json(silent=True) or {}
    direction = str(data.get("direction") or "持续自主优化").strip()
    return jsonify({"status": "ok", "result": _autonomy_tick(reason="manual", direction=direction)})


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


# ---------------------------------------------------------------------------
# 智能摘要 — 集成 MemoryTree + KnowledgeCurator + AutoDream
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


@app.route("/api/memory/layers", methods=["GET"])
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


@app.route("/api/memory/refine", methods=["POST"])
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


@app.route("/api/curator/run", methods=["POST"])
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


@app.route("/api/curator/patterns", methods=["GET"])
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


@app.route("/api/summarize", methods=["POST"])
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


@app.route("/api/dream", methods=["POST"])
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


@app.route("/api/learning/kanban", methods=["GET"])
def api_learning_kanban():
    """Lesson 生命周期看板 — 按状态分组，关联 Run 和时间线。

    重要：'verified' 列表示后端宣称成功，但不等于真的新增了能力。
    需要看 card.quality.substantive 才知道是否真改了函数。
    """
    lessons_file = PROJECT_ROOT / "memory" / "agent_lessons.json"
    runs_file = PROJECT_ROOT / "memory" / "self_evolution_runs.json"
    lessons = load_json(str(lessons_file), default=[])
    runs = load_json(str(runs_file), default=[])
    if not isinstance(lessons, list):
        lessons = []
    if not isinstance(runs, list):
        runs = []

    # 构建 lesson_id → [run] 索引
    runs_by_lesson = {}
    for run in runs:
        lid = run.get("lesson_id", "")
        if lid:
            runs_by_lesson.setdefault(lid, []).append(run)

    # 按状态分组 — 区分三档完成质量
    columns = {
        "pending": [],
        "learning": [],          # 有 run 但还没最终状态
        "substantive": [],       # ✅ 真完成 — 新增了真智能函数
        "degraded": [],          # 🟡 降级完成 — 新增了函数但是 fallback 占位
        "metadata_only": [],     # ⚠️ 假完成 — verified 但只追加 dict / 没改函数
        "failed": [],
        "blocked": [],
    }

    def _lesson_quality(lesson: dict) -> dict:
        """从 lesson.result 中提取质量信号，给前端用。"""
        result = lesson.get("result") or {}
        if not isinstance(result, dict):
            return {"substantive": False, "changed": False, "reason": "no result dict"}

        # 直接看 self_evolution._assess_change_quality 写入的 quality 字段
        q = result.get("quality") or {}
        if isinstance(q, dict) and "substantive" in q:
            raw_sub = q.get("substantive")
            # 保留 True/False/"degraded" 三态
            if raw_sub == "degraded":
                normalized_sub = "degraded"
            elif raw_sub is True:
                normalized_sub = True
            else:
                normalized_sub = False
            return {
                "substantive": normalized_sub,
                "changed": bool(result.get("changed")),
                "reason": str(q.get("reason", "")),
                "added": q.get("added") or [],
                "real_funcs": q.get("real_funcs") or [],
                "fallback_funcs": q.get("fallback_funcs") or [],
                "fallback_count": q.get("fallback_count", 0),
                "changed_funcs": q.get("changed_funcs") or [],
                "removed": q.get("removed") or [],
                "before_def_count": q.get("before_def_count"),
                "after_def_count": q.get("after_def_count"),
            }

        # 旧版 lesson 没有 quality 字段 — 用 fallback 规则推断
        fallback = result.get("fallback_result") or {}
        if (fallback.get("file_path") or "").endswith("learned_capabilities.py"):
            return {
                "substantive": False,
                "changed": bool(result.get("changed")),
                "reason": "fallback to learned_capabilities — only metadata appended (legacy)",
            }
        if (result.get("file_path") or "").endswith("learned_capabilities.py"):
            return {
                "substantive": False,
                "changed": bool(result.get("changed")),
                "reason": "only metadata appended to learned_capabilities.py (legacy)",
            }

        return {
            "substantive": None,  # 未知 — 旧 lesson 没记录质量信号
            "changed": bool(result.get("changed")),
            "reason": "legacy lesson — no quality signal recorded",
        }

    for lesson in lessons:
        status = lesson.get("status", "pending")
        related_runs = runs_by_lesson.get(lesson.get("id", ""), [])
        quality = _lesson_quality(lesson)

        # 构建时间线
        timeline = []
        created = lesson.get("created_at")
        if created:
            timeline.append({"event": "created", "time": created,
                             "detail": f"从 {lesson.get('source', 'unknown')} 学习"})

        for run in related_runs:
            run_time = run.get("created_at", 0)
            run_status = run.get("status", "unknown")
            timeline.append({
                "event": "run",
                "time": run_time,
                "status": run_status,
                "detail": f"目标: {run.get('target_file', '?')} | {run.get('goal', '?')[:60]}",
            })

        applied = lesson.get("applied_at")
        if applied:
            timeline.append({"event": "applied", "time": applied,
                             "detail": f"状态变更为 {status}"})

        timeline.sort(key=lambda x: x.get("time", 0))

        target_file = ((lesson.get("result") or {}).get("file_path") or "").replace(
            str(PROJECT_ROOT) + "/", "")

        card = {
            "id": lesson.get("id", ""),
            "capability": lesson.get("capability", ""),
            "source": lesson.get("source", ""),
            "pattern": lesson.get("pattern", ""),
            "adaptation": lesson.get("adaptation", ""),
            "suggested_files": lesson.get("suggested_files", []),
            "topic": lesson.get("topic", ""),
            "evidence": lesson.get("evidence", ""),
            "status": status,
            "created_at": created,
            "applied_at": applied,
            "run_count": len(related_runs),
            "timeline": timeline,
            "last_run_status": related_runs[-1].get("status") if related_runs else None,
            "target_file": target_file,
            "quality": quality,
        }

        # 分配到列
        if status == "blocked":
            columns["blocked"].append(card)
        elif status == "failed":
            columns["failed"].append(card)
        elif status == "verified_degraded":
            columns["degraded"].append(card)
        elif status == "verified":
            # 把 verified 进一步细分：substantive=True 真完成；'degraded' 占位；其他算假完成
            sub = quality.get("substantive")
            if sub is True:
                columns["substantive"].append(card)
            elif sub == "degraded":
                columns["degraded"].append(card)
            else:
                columns["metadata_only"].append(card)
        elif status == "applied_metadata_only":
            columns["metadata_only"].append(card)
        elif status == "pending" and related_runs:
            columns["learning"].append(card)
        else:
            columns["pending"].append(card)

    # 统计 — 区分三档完成
    substantive_n = len(columns["substantive"])
    degraded_n = len(columns["degraded"])
    metadata_n = len(columns["metadata_only"])
    total_claims = substantive_n + degraded_n + metadata_n

    # 向后兼容：保留 "verified" key（旧测试 / 旧前端可能依赖它）— 包含真+降级+假
    columns["verified"] = columns["substantive"] + columns["degraded"] + columns["metadata_only"]

    stats = {
        "total": len(lessons),
        "by_status": {k: len(v) for k, v in columns.items()},
        "runs_total": len(runs),
        # 真实质量指标
        "real_completion_rate": (
            round(substantive_n / total_claims, 3)
            if total_claims else 0
        ),
        "verified_and_real": substantive_n,
        "verified_degraded": degraded_n,
        "verified_but_fake": metadata_n,
    }

    return jsonify({
        "status": "ok",
        "columns": columns,
        "stats": stats,
        "column_meanings": {
            "pending": "未开始",
            "learning": "已发起 run，未拿到最终状态",
            "substantive": "✅ 真完成 — 新增/修改了函数，能力真的多了",
            "degraded": "🟡 降级完成 — 加了函数但是 fallback 占位（LLM 真智能未能生成）",
            "metadata_only": "⚠️ 假完成 — 后端报 verified 但只追加了元数据/未改函数",
            "failed": "❌ 失败 — apply 或 verify 报错",
            "blocked": "🚫 命中安全边界，被拒绝",
        },
    })


@app.route("/api/learning/capability-check", methods=["GET"])
def api_learning_capability_check():
    """对每条 verified lesson，验证 goal 里声称新增的函数**是否真的可被调用**。

    检查链路：
      1. 找到 lesson 的目标文件
      2. 用 AST 解析该文件，列出真实定义的函数/类名
      3. 从 goal 文本中启发式提取 agent 声称要加的函数名
      4. 比对：声称的函数是否真的存在；进一步 import 验证是否可调用

    返回每条 lesson 一个 callable_check 报告。
    real_capability_rate = 真能调用的能力数 / verified lesson 数 — 这才是真实进化率。
    """
    import ast
    import importlib
    import re

    lessons = load_json(str(PROJECT_ROOT / "memory" / "agent_lessons.json"), default=[])
    if not isinstance(lessons, list):
        lessons = []

    results = []
    counters = {
        "total": 0,
        "verified": 0,
        "callable": 0,
        "not_callable": 0,
        "no_function_named": 0,
        "file_missing": 0,
        "import_error": 0,
    }

    func_patterns = [
        re.compile(r"函数\s*[`\"']?([a-zA-Z_][\w]+)\(?", re.UNICODE),
        re.compile(r"添加(?:一个)?函数\s*[`\"']?([a-zA-Z_][\w]+)", re.UNICODE),
        re.compile(r"\b(?:def\s+)?([a-zA-Z_][\w]+)\s*\(", re.UNICODE),
    ]
    reserved = {"if", "for", "in", "is", "and", "or", "not", "return", "from",
                "import", "as", "def", "class", "args", "kwargs", "self", "True",
                "False", "None", "str", "int", "list", "dict", "tuple", "set"}

    def _extract_function_names(text: str) -> "list[str]":
        names = []
        for p in func_patterns:
            for m in p.findall(text or ""):
                name = m[-1] if isinstance(m, tuple) else m
                if name and name not in names and not name.startswith("_") and name not in reserved:
                    names.append(name)
        return names[:5]

    for lesson in lessons:
        counters["total"] += 1
        if lesson.get("status") != "verified":
            continue
        counters["verified"] += 1

        result = lesson.get("result") or {}
        rel_file = (
            result.get("file_path")
            or (result.get("fallback_result") or {}).get("file_path")
            or ""
        ).replace(str(PROJECT_ROOT) + "/", "")
        goal_text = (
            result.get("goal")
            or (result.get("metadata") or {}).get("goal")
            or lesson.get("topic", "")
        )

        func_names = _extract_function_names(goal_text)
        report = {
            "lesson_id": lesson.get("id"),
            "capability": lesson.get("capability"),
            "target_file": rel_file,
            "goal_snippet": (goal_text or "")[:200],
            "claimed_functions": func_names,
            "found_functions": [],
            "missing_functions": [],
            "callable": False,
            "callable_errors": [],
            "reason": "",
        }

        if not rel_file or not (PROJECT_ROOT / rel_file).is_file():
            report["reason"] = "目标文件缺失"
            counters["file_missing"] += 1
            results.append(report)
            continue

        if not func_names:
            report["reason"] = "goal 中未明确写出函数名"
            counters["no_function_named"] += 1
            results.append(report)
            continue

        try:
            src = (PROJECT_ROOT / rel_file).read_text(encoding="utf-8")
            tree = ast.parse(src)
            defined: "set[str]" = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    defined.add(node.name)
        except Exception as exc:
            report["reason"] = f"AST 解析失败: {exc}"
            counters["import_error"] += 1
            results.append(report)
            continue

        found = [n for n in func_names if n in defined]
        missing = [n for n in func_names if n not in defined]
        report["found_functions"] = found
        report["missing_functions"] = missing

        # 进一步：尝试 import 模块、获取属性、检查可调用
        callable_in_runtime = False
        if found:
            try:
                mod_name = rel_file.replace("/", ".").rsplit(".py", 1)[0]
                if mod_name in sys.modules:
                    module = importlib.reload(sys.modules[mod_name])
                else:
                    module = importlib.import_module(mod_name)
                for fn_name in found:
                    obj = getattr(module, fn_name, None)
                    if obj is None:
                        report["callable_errors"].append(
                            f"{fn_name}: 模块层找不到（可能被 class 包裹或是方法）")
                    elif not callable(obj):
                        report["callable_errors"].append(
                            f"{fn_name}: 存在但不可调用 (type={type(obj).__name__})")
                callable_in_runtime = (not report["callable_errors"]) and bool(found)
            except Exception as exc:
                report["callable_errors"].append(f"import 失败: {exc}")
                callable_in_runtime = False

        report["callable"] = callable_in_runtime
        if callable_in_runtime:
            report["reason"] = "✓ 声称的函数真实存在且可调用"
            counters["callable"] += 1
        else:
            report["reason"] = "✗ 声称的函数缺失或不可调用 — 没有真的实现这个能力"
            counters["not_callable"] += 1

        results.append(report)

    return jsonify({
        "status": "ok",
        "summary": counters,
        "real_capability_rate": (
            round(counters["callable"] / counters["verified"], 3)
            if counters["verified"] else 0
        ),
        "reports": results,
        "note": (
            "real_capability_rate = 真能调用的能力数 / 声称verified的lesson数。"
            "这个数字才是冷小北真实的'进化成功率'。"
        ),
    })


@app.route("/api/learning/apply-lesson", methods=["POST"])
def api_apply_lesson():
    """应用指定 Lesson — 推动生命周期从 pending → verified/failed"""
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    data = request.get_json(silent=True) or {}
    lesson_id = data.get("lesson_id", "").strip()
    if not lesson_id:
        return jsonify({"error": "lesson_id 为空"}), 400

    try:
        from src.self_evolution import SelfEvolutionCore
        from src.agent_learning import AgentLesson
        evo_core = SelfEvolutionCore(str(PROJECT_ROOT))

        # 找到指定 lesson（JSON 加载的是 dict，需转为 AgentLesson 对象）
        lessons = load_json(str(PROJECT_ROOT / "memory" / "agent_lessons.json"), default=[])
        target = None
        for lesson in lessons:
            if lesson.get("id") == lesson_id:
                target = AgentLesson.from_dict(lesson)
                break

        if target is None:
            return jsonify({"error": f"Lesson {lesson_id} 不存在"}), 404

        # 应用 lesson
        result = evo_core.apply_lesson(target)
        restart = _schedule_restart_if_source_changed(result, "learning_apply_lesson_source_changed")
        return jsonify({"status": "ok", "result": result, "restart": restart})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500


# ============================================================================
# Phase 2 升级：SSE 实时事件流 + 12 个新 API
# ============================================================================

# 在模块加载时就确保 EventBus 就绪，让早期事件不会丢
_ensure_event_bus()


@app.route("/api/events")
def api_events():
    """SSE 长连接：把 kairos.events 的事件实时推给前端。"""
    _ensure_event_bus()

    if not _KAIROS_EVENTS_OK:
        return jsonify({"error": "EventBus 未加载"}), 503

    q: queue.Queue = queue.Queue(maxsize=200)
    with _sse_lock:
        _sse_subscribers.append(q)

    def stream():
        try:
            yield ": connected\n\n"
            # 入场推最近 20 条历史，让前端有上下文
            try:
                for record in kairos_events.recent(limit=20):
                    payload = record.to_dict()
                    yield f"event: {payload['event_type']}\n"
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception:
                pass
            while True:
                try:
                    payload = q.get(timeout=15)
                    yield f"event: {payload['event_type']}\n"
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _sse_lock:
                if q in _sse_subscribers:
                    _sse_subscribers.remove(q)

    response = Response(stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


# ---------------------------------------------------------------------------
# 学习进度模块 API
# ---------------------------------------------------------------------------

def _load_all_lessons_full() -> list:
    """读取 lessons 全字段（agent_lessons.json）。"""
    data = load_json(str(PROJECT_ROOT / "memory" / "agent_lessons.json"), default=[])
    return data if isinstance(data, list) else []


@app.route("/api/learning/lessons", methods=["GET"])
def api_learning_lessons():
    """返回完整字段的 lessons（替代精简版 /api/lessons）。"""
    lessons = _load_all_lessons_full()
    by_status = {"pending": 0, "applying": 0, "verifying": 0, "applied": 0, "failed": 0, "other": 0}
    for item in lessons:
        s = str((item or {}).get("status", "")).strip().lower() or "pending"
        bucket = s if s in by_status else "other"
        by_status[bucket] += 1
    return jsonify({
        "status": "ok",
        "count": len(lessons),
        "by_status": by_status,
        "lessons": lessons,
    })


@app.route("/api/learning/capabilities", methods=["GET"])
def api_learning_capabilities():
    """能力分布：按 capability 字段聚合 lesson 数。"""
    lessons = _load_all_lessons_full()
    distribution: dict = {}
    for item in lessons:
        cap = str((item or {}).get("capability", "未分类")).strip() or "未分类"
        distribution[cap] = distribution.get(cap, 0) + 1

    # 同时返回 learned_capabilities.py 模块静态注册的能力
    static_list: list = []
    try:
        from src.learned_capabilities import list_learned_capabilities
        static_list = list_learned_capabilities()
    except Exception:
        static_list = []

    return jsonify({
        "status": "ok",
        "distribution": [{"capability": k, "count": v} for k, v in
                         sorted(distribution.items(), key=lambda kv: kv[1], reverse=True)],
        "total_lessons": len(lessons),
        "static_capabilities": static_list,
    })


@app.route("/api/learning/timeline", methods=["GET"])
def api_learning_timeline():
    """学习时间轴：按 created_at desc 排序。"""
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 500))
    except Exception:
        limit = 50
    lessons = _load_all_lessons_full()
    timeline = sorted(
        lessons,
        key=lambda x: float((x or {}).get("created_at") or 0.0),
        reverse=True,
    )[:limit]
    return jsonify({
        "status": "ok",
        "count": len(timeline),
        "timeline": timeline,
    })


# ---------------------------------------------------------------------------
# 自进化模块 API
# ---------------------------------------------------------------------------

@app.route("/api/evolve/improvements", methods=["GET"])
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


@app.route("/api/evolve/progress", methods=["GET"])
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


# ---------------------------------------------------------------------------
# 执行情况模块 API
# ---------------------------------------------------------------------------

def _autonomy_next_tick_eta() -> "float | None":
    """估算下一次 tick 距离现在的秒数。"""
    with _autonomy_lock:
        if not _autonomy_state.get("enabled"):
            return None
        interval = int(_autonomy_state.get("interval_seconds") or AUTONOMY_DEFAULT_INTERVAL)
        last = _autonomy_state.get("last_tick_at")
    if not last:
        return float(interval)
    remaining = float(last) + interval - time.time()
    return max(0.0, remaining)


@app.route("/api/execution/autonomy", methods=["GET"])
def api_execution_autonomy():
    """后台自主循环状态 + 下次 tick 倒计时。"""
    snap = _autonomy_snapshot()
    snap["next_tick_eta_seconds"] = _autonomy_next_tick_eta()
    return jsonify({"status": "ok", "autonomy": snap})


def _safe_attr(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


@app.route("/api/execution/facades", methods=["GET"])
def api_execution_facades():
    """4 个 facade 的子组件运行状态。"""
    agent = _get_agent()
    facades: dict = {
        "guardian": {"loaded": False},
        "memory": {"loaded": False},
        "evolution": {"loaded": False},
        "reasoning": {"loaded": False},
    }

    if agent is None:
        return jsonify({"status": "ok", "facades": facades, "agent": "unavailable"})

    try:
        gf = getattr(agent, "guardian_facade", None)
        if gf is not None:
            kairos = _safe_attr(gf, "kairos")
            facades["guardian"] = {
                "loaded": True,
                "kairos_running": bool(getattr(kairos, "_running", False)) if kairos else False,
                "has_lock_manager": _safe_attr(gf, "lock_manager") is not None,
                "has_permission_manager": _safe_attr(gf, "permission_manager") is not None,
                "has_budget_tracker": _safe_attr(gf, "budget_tracker") is not None,
                "has_performance_monitor": _safe_attr(gf, "performance_monitor") is not None,
            }
    except Exception as exc:
        facades["guardian"] = {"loaded": True, "error": str(exc)}

    try:
        mf = getattr(agent, "memory_facade", None)
        if mf is not None:
            hm = _safe_attr(mf, "hybrid_memory")
            facades["memory"] = {
                "loaded": True,
                "has_hybrid_memory": hm is not None,
                "has_memory": _safe_attr(mf, "memory") is not None,
                "has_knowledge_curator": _safe_attr(mf, "knowledge_curator") is not None,
                "has_auto_dream": _safe_attr(mf, "auto_dream") is not None,
                "embedding_ready": bool(getattr(hm, "embedding_model", None)) if hm else False,
            }
    except Exception as exc:
        facades["memory"] = {"loaded": True, "error": str(exc)}

    try:
        ef = getattr(agent, "evolution_facade", None)
        if ef is not None:
            facades["evolution"] = {
                "loaded": True,
                "has_autonomous_evolution": _safe_attr(ef, "autonomous_evolution") is not None,
                "has_curator": _safe_attr(ef, "curator") is not None,
                "has_constitution": _safe_attr(ef, "constitution") is not None,
                "has_circuit_breaker": _safe_attr(ef, "circuit_breaker") is not None,
            }
    except Exception as exc:
        facades["evolution"] = {"loaded": True, "error": str(exc)}

    try:
        rf = getattr(agent, "reasoning_facade", None)
        if rf is not None:
            facades["reasoning"] = {
                "loaded": True,
                "has_integration_manager": _safe_attr(rf, "integration_manager") is not None,
            }
    except Exception as exc:
        facades["reasoning"] = {"loaded": True, "error": str(exc)}

    return jsonify({"status": "ok", "facades": facades})


@app.route("/api/execution/events", methods=["GET"])
def api_execution_events():
    """最近事件历史（从 kairos.events.recent 取）。"""
    if not _KAIROS_EVENTS_OK:
        return jsonify({"status": "ok", "events": [], "stats": {}})
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 500))
    except Exception:
        limit = 100
    event_type = request.args.get("type") or None
    _ensure_event_bus()
    try:
        records = kairos_events.recent(event_type=event_type, limit=limit)
        events = [r.to_dict() for r in records]
        return jsonify({
            "status": "ok",
            "count": len(events),
            "events": events,
            "stats": kairos_events.stats(),
        })
    except Exception as exc:
        return jsonify({"status": "failed", "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# 系统模块 API：记忆检索 / 目标 / 动机
# ---------------------------------------------------------------------------

@app.route("/api/memory/search", methods=["POST"])
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


@app.route("/api/memory/index", methods=["GET"])
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


_goal_system = None
_motivation_system = None
_goal_system_lock = threading.Lock()


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


@app.route("/api/goals", methods=["GET"])
def api_goals():
    gs = _get_goal_system()
    if gs is None:
        return jsonify({"status": "ok", "goals": [], "note": "goal_system 未就绪"})
    try:
        goals = gs.list_goals()
        return jsonify({
            "status": "ok",
            "count": len(goals or []),
            "goals": [_jsonable(g) for g in (goals or [])],
        })
    except Exception as exc:
        return jsonify({"status": "failed", "error": str(exc)}), 500


@app.route("/api/motivations", methods=["GET"])
def api_motivations():
    ms = _get_motivation_system()
    if ms is None:
        return jsonify({"status": "ok", "motivations": [], "note": "motivation_system 未就绪"})
    try:
        items = ms.list_motivations()
        return jsonify({
            "status": "ok",
            "count": len(items or []),
            "motivations": [_jsonable(m) for m in (items or [])],
        })
    except Exception as exc:
        return jsonify({"status": "failed", "error": str(exc)}), 500


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
