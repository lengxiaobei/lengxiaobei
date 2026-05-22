"""
学习 Blueprint：经验沉淀、运行记录、代码变更、学习看板、能力检查、时间轴。
"""

import sys
import ast
import importlib
import re

from flask import Blueprint, jsonify, request

from src.utils import load_json

from lx_web.shared.state import PROJECT_ROOT
from lx_web.shared.utils import _get_agent, _schedule_restart_if_source_changed

learning_bp = Blueprint('learning', __name__)


def _load_all_lessons_full() -> list:
    """读取 lessons 全字段（agent_lessons.json）。"""
    data = load_json(str(PROJECT_ROOT / "memory" / "agent_lessons.json"), default=[])
    return data if isinstance(data, list) else []


@learning_bp.route("/api/lessons", methods=["GET"])
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


@learning_bp.route("/api/runs", methods=["GET"])
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


@learning_bp.route("/api/code-changes", methods=["GET"])
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


@learning_bp.route("/api/learning/kanban", methods=["GET"])
def api_learning_kanban():
    """Lesson 生命周期看板 — 按状态分组，关联 Run 和时间线。

    重要：'verified' 只表示后端完成了验证链路，不等于业务能力已经端到端生效。
    请查看 card.quality.syntax_ok / function_exists / callable_ok / semantic_ok / integrated_ok。
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

    # 按状态分组 — 区分多级质量信号
    columns = {
        "pending": [],
        "learning": [],          # 有 run 但还没最终状态
        "substantive": [],       # 语法/函数存在/可调用通过，且不是确定性 fallback
        "degraded": [],          # 函数存在且可调用，但属于 fallback 占位或语义未证明
        "metadata_only": [],     # verified 但只追加 dict / 没改函数
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
                "syntax_ok": bool(q.get("syntax_ok")),
                "function_exists": bool(q.get("function_exists")),
                "callable_ok": bool(q.get("callable_ok")),
                "semantic_ok": bool(q.get("semantic_ok")),
                "integrated_ok": bool(q.get("integrated_ok")),
                "changed": bool(result.get("changed")),
                "reason": str(q.get("reason", "")),
                "quality_note": str(q.get("quality_note", "")),
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
            # 把 verified 进一步细分：substantive=True 非 fallback 可调用；'degraded' 占位；其他算元数据完成
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

    # 统计 — 区分质量阶段
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
        "quality_gates": {
            "syntax_ok": "源码编译和核心测试通过",
            "function_exists": "声明的函数/类在目标文件 AST 中存在",
            "callable_ok": "模块导入后可以取得对应 callable",
            "semantic_ok": "不是确定性 fallback；但仍不等同于完整业务语义验证",
            "integrated_ok": "端到端业务链路已证明会调用并受益于该能力（当前默认 false，需专门集成测试证明）",
        },
        "column_meanings": {
            "pending": "未开始",
            "learning": "已发起 run，未拿到最终状态",
            "substantive": "语法通过、函数存在、可调用，且不是确定性 fallback；仍需看 integrated_ok 判断业务链路是否生效",
            "degraded": "函数存在且可调用，但属于 fallback/占位或语义有效性未证明",
            "metadata_only": "后端记录了完成，但只追加了元数据或未新增/修改函数",
            "failed": "apply 或 verify 报错",
            "blocked": "命中安全边界，被拒绝",
        },
    })


@learning_bp.route("/api/learning/capability-check", methods=["GET"])
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


@learning_bp.route("/api/learning/apply-lesson", methods=["POST"])
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


@learning_bp.route("/api/learning/lessons", methods=["GET"])
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


@learning_bp.route("/api/learning/capabilities", methods=["GET"])
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


@learning_bp.route("/api/learning/timeline", methods=["GET"])
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
