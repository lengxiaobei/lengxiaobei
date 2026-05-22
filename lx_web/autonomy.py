"""Autonomy engine — background autonomous optimization loop.

Extracted from lx_web.py for modularity.
"""

import json
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

# These are imported at call time to keep the module self-contained.
# All dependencies on PROJECT_ROOT and _globals come from the caller via function args.


def autonomy_snapshot(project_root: Path, state: dict, state_lock: threading.Lock,
                      thread, pending_lessons_loader, records_summary,
                      learning_plan_loader) -> dict:
    with state_lock:
        snap = dict(state)
        snap["thread_alive"] = bool(thread and thread.is_alive())
    snap["pending_lessons"] = len(pending_lessons_loader(limit=1000))
    snap["runs"] = records_summary("memory/autonomy_runs.json")
    learning_plan = learning_plan_loader()
    snap["learning"] = {
        "plan_count": len(learning_plan),
        "pending_count": sum(1 for item in learning_plan if item.get("status") == "pending"),
        "learned_count": sum(1 for item in learning_plan if item.get("status") == "learned"),
        "latest": max(learning_plan, key=lambda item: item.get("last_attempt_at") or 0) if learning_plan else None,
    }
    return snap


def autonomy_tick(reason: str, direction: str, state: dict, state_lock: threading.Lock,
                  tick_lock: threading.Lock, project_root: Path, get_agent_fn,
                  emit_event_fn, run_core_tests_fn, attempt_repair_fn,
                  load_pending_lessons_fn, evolve_from_lessons_fn,
                  optimize_or_learn_fn, run_reflection_fn,
                  schedule_restart_fn, atomic_record_fn,
                  runs_file: Path, autonomy_state: dict) -> dict:
    if not tick_lock.acquire(blocking=False):
        return {
            "status": "busy",
            "reason": reason,
            "message": "tick already running, skipping",
            "started_at": time.time(),
        }

    agent = get_agent_fn()
    started = time.time()
    emit_event_fn("autonomy.tick.started", {"reason": reason, "direction": direction}, source="autonomy")
    try:
        record = {
            "id": f"autonomy_{int(started)}",
            "reason": reason,
            "direction": direction or "continuous autonomous optimization",
            "started_at": started,
            "actions": [],
            "status": "running",
        }

        if agent is None:
            record["status"] = "failed"
            record["error"] = "Agent not ready"
        else:
            initial_check = run_core_tests_fn()
            record["actions"].append({
                "type": "self_check", "phase": "preflight",
                "result": initial_check,
            })
            if initial_check.get("status") == "failed":
                repair = attempt_repair_fn(agent, initial_check, direction)
                record["actions"].append({
                    "type": "autonomous_repair",
                    "result": repair,
                })
                if repair.get("status") != "success":
                    record["status"] = "failed"
                    record["next_step"] = "core tests failed, repair unsuccessful"

            if record["status"] == "running":
                pending = load_pending_lessons_fn()
                if pending:
                    result = evolve_from_lessons_fn(agent)
                    record["actions"].append({
                        "type": "apply_pending_lesson",
                        "lesson_id": pending[0].get("id"),
                        "topic": pending[0].get("topic"),
                        "result": result,
                    })
                    verify = run_core_tests_fn()
                    record["actions"].append({
                        "type": "post_lesson_verify",
                        "result": verify,
                    })
                    if verify.get("status") == "failed":
                        repair = attempt_repair_fn(agent, verify, direction)
                        record["actions"].append({
                            "type": "autonomous_repair",
                            "phase": "post_lesson",
                            "result": repair,
                        })
                        if repair.get("status") != "success":
                            record["status"] = "failed"
                            record["next_step"] = "post-lesson tests failed, repair unsuccessful"
                else:
                    optimize_or_learn_fn(agent, record, direction)

            if record["status"] == "running":
                record["status"] = "success"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
    finally:
        tick_lock.release()

    record["elapsed_seconds"] = round(time.time() - started, 3)
    record["finished_at"] = time.time()
    atomic_record_fn(runs_file, record)

    with state_lock:
        state["tick_count"] += 1
        state["last_tick_at"] = record["finished_at"]
        state["last_result"] = record

    emit_event_fn("autonomy.tick.finished",
                  {"record_id": record.get("id"), "status": record.get("status"),
                   "elapsed_seconds": record.get("elapsed_seconds"), "reason": reason},
                  source="autonomy")
    emit_event_fn("evolution.completed",
                  {"status": record.get("status"), "run_id": record.get("id")},
                  source="autonomy")

    # Reflect on this tick to find capability gaps
    try:
        tick_summary = json.dumps({
            "direction": direction,
            "reason": reason,
            "status": record.get("status"),
            "actions": [a.get("type") for a in (record.get("actions") or [])],
            "elapsed": record.get("elapsed_seconds"),
        }, ensure_ascii=False)
        run_reflection_fn(trigger="autonomy_tick", context_text=tick_summary)
    except Exception:
        pass

    restart = schedule_restart_fn(record, "autonomy_tick_source_changed")
    if restart:
        record["restart"] = restart

    return record


def autonomy_start(interval_seconds: int, state: dict, state_lock: threading.Lock,
                   thread_ref: list, loop_fn, snapshot_fn) -> dict:
    interval = max(60, min(int(interval_seconds or 300), 86400))
    with state_lock:
        state["enabled"] = True
        state["running"] = True
        state["interval_seconds"] = interval
        alive = bool(thread_ref[0] and thread_ref[0].is_alive())
    if not alive:
        t = threading.Thread(target=loop_fn, daemon=True, name="lx-autonomy-loop")
        thread_ref[0] = t
        t.start()
    return snapshot_fn()


def autonomy_stop(state: dict, state_lock: threading.Lock, snapshot_fn) -> dict:
    with state_lock:
        state["enabled"] = False
        state["running"] = False
    return snapshot_fn()


def autonomy_loop(state: dict, state_lock: threading.Lock, tick_fn):
    while True:
        with state_lock:
            enabled = bool(state["enabled"])
            interval = int(state["interval_seconds"])
            state["running"] = enabled
        if not enabled:
            with state_lock:
                state["running"] = False
            return

        tick_fn(reason="scheduled")

        slept = 0
        while slept < interval:
            time.sleep(1)
            slept += 1
            with state_lock:
                if not state["enabled"]:
                    state["running"] = False
                    return