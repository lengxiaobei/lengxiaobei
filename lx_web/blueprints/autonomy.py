"""
自主循环 Blueprint — autonomy 相关路由和辅助函数。
"""

import json
import os
import re
import time
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

from src.utils import load_json

from lx_web.shared.state import (
    PROJECT_ROOT,
    _KAIROS_EVENTS_OK,
    kairos_events,
    AUTONOMY_RUNS_FILE,
    AUTONOMY_LEARNING_PLAN_FILE,
    AUTONOMY_DEFAULT_INTERVAL,
    _autonomy_lock,
    _autonomy_state,
    _autonomy_thread,
    _autonomy_tick_lock,
    DEFAULT_LEARNING_TOPICS,
)
from lx_web.shared.sse import _emit_event, _ensure_event_bus
from lx_web.shared.utils import (
    _get_agent,
    _jsonable,
    _records_summary,
    _run_core_tests,
    _schedule_restart_if_source_changed,
    _run_reflection_async,
    _safe_attr,
)

autonomy_bp = Blueprint('autonomy', __name__)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@autonomy_bp.route("/api/autonomy/status", methods=["GET"])
def api_autonomy_status():
    return jsonify({"status": "ok", "autonomy": _autonomy_snapshot()})


@autonomy_bp.route("/api/autonomy/runs", methods=["GET"])
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


@autonomy_bp.route("/api/autonomy/learning-plan", methods=["GET"])
def api_autonomy_learning_plan():
    plan = _load_learning_plan()
    return jsonify({
        "status": "ok",
        "count": len(plan),
        "plan": plan,
    })


@autonomy_bp.route("/api/autonomy/start", methods=["POST"])
def api_autonomy_start():
    data = request.get_json(silent=True) or {}
    interval = int(data.get("interval_seconds") or AUTONOMY_DEFAULT_INTERVAL)
    return jsonify({"status": "ok", "autonomy": _autonomy_start(interval)})


@autonomy_bp.route("/api/autonomy/stop", methods=["POST"])
def api_autonomy_stop():
    return jsonify({"status": "ok", "autonomy": _autonomy_stop()})


@autonomy_bp.route("/api/autonomy/tick", methods=["POST"])
def api_autonomy_tick():
    data = request.get_json(silent=True) or {}
    direction = str(data.get("direction") or "持续自主优化").strip()
    return jsonify({"status": "ok", "result": _autonomy_tick(reason="manual", direction=direction)})


@autonomy_bp.route("/api/execution/autonomy", methods=["GET"])
def api_execution_autonomy():
    """后台自主循环状态 + 下次 tick 倒计时。"""
    snap = _autonomy_snapshot()
    snap["next_tick_eta_seconds"] = _autonomy_next_tick_eta()
    return jsonify({"status": "ok", "autonomy": snap})


@autonomy_bp.route("/api/execution/facades", methods=["GET"])
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


@autonomy_bp.route("/api/execution/events", methods=["GET"])
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
