"""Fast self-evolution MVP.

The loop is intentionally small:
learn other agents -> store lesson -> turn lesson into one source edit -> test -> remember.
"""

import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agent_learning import AgentLearner, AgentLearningStore, AgentLesson
from .code_change_log import CodeChangeLogger
from .llm import chat
from .utils import atomic_write_json, extract_json, load_json


BLOCKED_FILES = {
    "docs/SOUL.md",
    "docs/CONSTITUTION.md",
    "SOUL.md",
    "CONSTITUTION.md",
    ".env",
}

CONFIRM_FILES = {
    "src/core.py",
    "src/executor.py",
    "src/permission.py",
    "src/evolution/engine.py",
    "src/evolution/executor.py",
    "src/autonomy.py",
}

# 兜底安全目标 — 当无法选定时落到这里。保留原值以维持向后兼容。
SAFE_LESSON_TARGET = "src/learned_capabilities.py"

# 自进化扩展白名单 — agent 可以主动改这些文件中的任意一个，
# 而不是只能写元数据到 learned_capabilities.py。
# 选择标准：
#   1. 不在 BLOCKED_FILES / CONFIRM_FILES 中
#   2. 与其他模块耦合度低，单文件就能完成有意义改进
#   3. 已有自身职责的"次核心"模块，agent 改它能产生真实价值
SAFE_TARGETS = (
    "src/learned_capabilities.py",  # 能力注册表（兜底）
    "src/buddy.py",                 # 协作伙伴 — AutoGen/角色类
    "src/active_learner.py",        # 主动学习 — Copilot/Continue 类
    "src/dev_team.py",              # 开发团队多 Agent — AutoGen 类
    "src/critic.py",                # 代码审查 — Aider 类
    "src/code_change_log.py",       # 变更日志 — Git 感知类
    "src/testing.py",               # 测试钩子 — OpenHands 类
)


@dataclass
class SelfEvolutionRun:
    id: str
    topic: str
    lesson_id: str
    target_file: str
    goal: str
    status: str
    result: Dict[str, Any]
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SelfEvolutionCore:
    def __init__(self, project_root: str, evolution_engine=None):
        self.project_root = Path(project_root)
        self.learner = AgentLearner(str(self.project_root))
        self.lesson_store = AgentLearningStore(str(self.project_root))
        self.evolution_engine = evolution_engine
        self.runs_path = self.project_root / "memory" / "self_evolution_runs.json"
        self.runs_path.parent.mkdir(exist_ok=True)
        self.change_logger = CodeChangeLogger(str(self.project_root))

    def learn(self, topic: str, url: str = "", kind: str = "external", gap: str = "") -> AgentLesson:
        return self.learner.learn(topic, url=url, kind=kind, gap=gap)

    def evolve_from_lessons(self) -> Dict[str, Any]:
        lesson = self.lesson_store.next_pending()
        if lesson is None:
            return {"status": "no_lesson", "message": "没有 pending lesson"}
        return self.apply_lesson(lesson)

    def self_evolve(self, topic: str, url: str = "") -> Dict[str, Any]:
        lesson = self.learn(topic, url=url)
        return self.apply_lesson(lesson)

    def apply_lesson(self, lesson: AgentLesson) -> Dict[str, Any]:
        target_file = self._choose_target_file(lesson)
        boundary = self._check_boundary(target_file)
        if boundary != "allow":
            lesson.status = "blocked"
            lesson.result = {
                "status": "blocked",
                "reason": boundary,
                "target_file": target_file,
            }
            self.lesson_store.update(lesson)
            self._record_run(lesson, target_file, "", "blocked", lesson.result)
            return lesson.result

        plan = self._build_evolution_plan(lesson, target_file)
        goal = plan["goal"]
        expected_functions = plan["expected_functions"]
        before = self.change_logger.snapshot(list(SAFE_TARGETS) + [target_file])
        if target_file == SAFE_LESSON_TARGET:
            result = self._apply_to_learned_capabilities(lesson, goal)
        elif self.evolution_engine is None:
            result = {"status": "failed", "error": "进化引擎未配置"}
        else:
            primary = self.evolution_engine.evolve(target_file, goal)
            if primary.get("status") == "success":
                result = primary
            else:
                functional_fallback = self._apply_expected_function_fallback(
                    lesson=lesson,
                    target_file=target_file,
                    goal=goal,
                    expected_functions=expected_functions,
                    primary_result=primary,
                )
                if functional_fallback.get("status") == "success":
                    result = {
                        **functional_fallback,
                        "primary_target": target_file,
                        "primary_result": primary,
                        "fallback_target": target_file,
                        "fallback_kind": "deterministic_expected_function",
                        "message": "主进化生成代码失败，已用确定性 fallback 在目标模块写入真实可调用函数。",
                    }
                else:
                    metadata_fallback = self._apply_to_learned_capabilities(lesson, goal)
                    result = {
                        "status": metadata_fallback.get("status"),
                        "primary_target": target_file,
                        "primary_result": primary,
                        "fallback_target": SAFE_LESSON_TARGET,
                        "fallback_result": metadata_fallback,
                        "functional_fallback_result": functional_fallback,
                        "message": "主目标和确定性函数 fallback 均未成功，已回退到安全源码能力注册表。",
                    }

        # 记录 plan 让前端/后续能看到声称的函数
        result["expected_functions"] = expected_functions

        if result.get("status") == "success":
            verify = self._verify(
                target_file=target_file,
                expected_functions=expected_functions,
            )
            if verify["success"]:
                # 质量门：区分 真完成 / 降级完成（fallback 占位） / 仅元数据
                quality = self._assess_change_quality(target_file, before)
                result["quality"] = quality
                sub = quality.get("substantive")
                if sub is True:
                    lesson.status = "verified"
                elif sub == "degraded":
                    # 改了函数但全是 fallback 占位 — 算"半真"
                    lesson.status = "verified_degraded"
                    result["status"] = "verified_degraded"
                    result["message"] = (
                        f"{result.get('message', '')} ⚠ 降级完成：占位 fallback，未真实现 goal。"
                    ).strip()
                else:
                    # 没改函数，只追加 dict / 元数据
                    lesson.status = "applied_metadata_only"
                    result["status"] = "applied_metadata_only"
                    result["message"] = (
                        f"{result.get('message', '')} ⚠ 但未新增/修改函数，仅写入元数据。"
                    ).strip()
                result["verification"] = verify
            else:
                lesson.status = "failed"
                result["status"] = "failed"
                result["verification"] = verify
        else:
            lesson.status = "failed"

        lesson.applied_at = time.time()
        lesson.result = result
        self.lesson_store.update(lesson)
        self._record_run(lesson, target_file, goal, lesson.status, result)
        self._record_code_change(lesson, target_file, goal, before, result)
        return result

    def _choose_target_file(self, lesson: AgentLesson) -> str:
        # 1) 优先用 lesson.suggested_files 中真实存在且 allow 的
        candidates = lesson.suggested_files or []
        for candidate in candidates:
            if self._check_boundary(candidate) == "allow":
                path = self.project_root / candidate
                if path.exists() and path.is_file():
                    return candidate

        # 2) suggested_files 全是虚构路径 → 在 SAFE_TARGETS 中按 lesson 内容打分挑一个
        chosen = self._pick_safe_target(lesson)
        if chosen and chosen != SAFE_LESSON_TARGET:
            path = self.project_root / chosen
            if path.exists() and path.is_file():
                return chosen

        # 3) 最后兜底
        self._ensure_safe_lesson_target()
        return SAFE_LESSON_TARGET

    def _pick_safe_target(self, lesson: AgentLesson) -> str:
        """根据 lesson.capability + source 关键词匹配 SAFE_TARGETS。
        无 LLM 调用，纯启发式 — 失败也不会破坏流程。"""
        text = " ".join([
            (lesson.capability or "").lower(),
            (lesson.pattern or "").lower(),
            (lesson.adaptation or "").lower(),
            (lesson.source or "").lower(),
            (lesson.topic or "").lower(),
        ])

        # 关键词 → 文件 映射（按优先级）
        rules = [
            (("autogen", "多agent", "多 agent", "角色分", "role", "协作", "交接", "handoff", "team"),
             "src/dev_team.py"),
            (("copilot", "continue", "上下文感知", "context-aware", "active learn", "主动学习",
              "ide ", "建议生成", "代码建议"),
             "src/active_learner.py"),
            (("aider", "git ", "patch", "diff", "代码审查", "critic", "review", "lint"),
             "src/critic.py"),
            (("最小补丁", "minimal patch", "提交前验证", "pre-commit", "git感知", "git 感知",
              "change log", "变更日志"),
             "src/code_change_log.py"),
            (("openhands", "task split", "任务拆解", "工作区执行", "错误恢复",
              "test", "测试", "校验", "verify"),
             "src/testing.py"),
            (("partner", "buddy", "搭档", "陪伴", "对话伙伴"),
             "src/buddy.py"),
        ]

        for keywords, target in rules:
            if any(kw in text for kw in keywords):
                # 命中规则但目标文件不在白名单或不存在时跳过
                if target in SAFE_TARGETS and (self.project_root / target).is_file():
                    return target

        return SAFE_LESSON_TARGET

    def _build_goal(self, lesson: AgentLesson, target_file: str) -> str:
        """向后兼容包装：只返回 goal 字符串。新代码应该用 _build_evolution_plan。"""
        plan = self._build_evolution_plan(lesson, target_file)
        return plan.get("goal", "")

    def _build_evolution_plan(self, lesson: AgentLesson, target_file: str) -> Dict[str, Any]:
        """生成一次进化的完整规划。**强制 LLM 写明要新增的函数名和签名**，
        让后续 _verify 能做真实的可调用性检查。

        返回:
            {
                "goal": "具体改进目标（句子）",
                "expected_functions": [
                    {"name": "fn_name", "signature": "fn_name(arg1, arg2)", "kind": "function"},
                    ...
                ],
            }
        """
        prompt = f"""把以下 Agent 学习经验转成冷小北对指定源码文件的一次小步改进目标。

目标文件: {target_file}
来源: {lesson.source}
能力: {lesson.capability}
模式: {lesson.pattern}
价值: {lesson.why_good}
适配方式: {lesson.adaptation}

要求:
- 只做一个可以快速落地的小改进
- 不重写架构
- 不添加外部依赖
- 不修改安全底线
- **必须给出至少 1 个具体函数名（snake_case），后续会用 AST 检查这个函数是否真的被加进去**

只返回 JSON:
{{
  "goal": "一句具体源码改进目标，必须提到要新增的函数名",
  "expected_functions": [
    {{"name": "snake_case_function_name", "signature": "name(arg1: type, arg2: type) -> type", "kind": "function"}}
  ]
}}

示例好的输出（不要照抄）:
{{
  "goal": "在 {target_file} 中新增函数 assign_role_by_task_type，根据任务类型字符串返回对应的角色名",
  "expected_functions": [
    {{"name": "assign_role_by_task_type", "signature": "assign_role_by_task_type(task_type: str) -> str", "kind": "function"}}
  ]
}}"""
        try:
            data = extract_json(chat(
                prompt,
                system="你是冷小北自进化规划器。只返回JSON，goal 必须提到具体函数名。",
                temperature=0.2,
                use_cache=False,
            ))
        except Exception:
            data = {}

        goal = str(data.get("goal") or lesson.adaptation or lesson.pattern or "")
        expected = data.get("expected_functions") or []
        if not isinstance(expected, list):
            expected = []

        # 规范化 expected_functions
        normalized: List[Dict[str, Any]] = []
        for item in expected[:5]:
            if isinstance(item, str):
                normalized.append({"name": item, "signature": f"{item}()", "kind": "function"})
            elif isinstance(item, dict) and item.get("name"):
                normalized.append({
                    "name": str(item["name"]).strip(),
                    "signature": str(item.get("signature") or f"{item['name']}()"),
                    "kind": str(item.get("kind") or "function"),
                })

        # 兜底：如果 LLM 没给出函数名，从 goal 文本中提取，再补一个
        if not normalized:
            import re as _re
            for pat in (r"函数\s*[`\"']?([a-z_][\w]*)", r"\b([a-z_][a-z0-9_]{2,})\s*\("):
                m = _re.search(pat, goal)
                if m and m.group(1) not in ("self", "args", "kwargs"):
                    normalized.append({
                        "name": m.group(1),
                        "signature": f"{m.group(1)}()",
                        "kind": "function",
                    })
                    break

        return {"goal": goal, "expected_functions": normalized}

    def _apply_expected_function_fallback(
        self,
        lesson: AgentLesson,
        target_file: str,
        goal: str,
        expected_functions: List[Dict[str, Any]],
        primary_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """主 LLM 代码生成失败时，在 safe target 中写入真实 callable 函数。

        这个 fallback 不假装已经实现完整智能；它保证先突破 0% 真完成：
        - 只写 SAFE_TARGETS 中的非 metadata 模块
        - 只追加缺失的 expected function
        - 写入后必须 compile 成功，否则回滚
        """
        if target_file not in SAFE_TARGETS or target_file == SAFE_LESSON_TARGET:
            return {"status": "skipped", "reason": "target is not a functional safe target"}
        if not expected_functions:
            return {"status": "skipped", "reason": "no expected_functions"}

        target = self.project_root / target_file
        if not target.is_file():
            return {"status": "failed", "error": "target file missing", "target_file": target_file}

        original = target.read_text(encoding="utf-8")
        missing = self._missing_expected_functions(target_file, expected_functions)
        if not missing:
            return {
                "status": "success",
                "changed": False,
                "file_path": str(target),
                "goal": goal,
                "message": "expected functions already exist in target module",
            }

        block = self._render_expected_function_block(
            lesson=lesson,
            goal=goal,
            expected_functions=missing,
            primary_result=primary_result,
        )
        updated = original.rstrip() + "\n\n\n" + block.rstrip() + "\n"

        try:
            compile(updated, str(target), "exec")
        except SyntaxError as exc:
            return {
                "status": "failed",
                "error": f"fallback generated invalid syntax: {exc}",
                "target_file": target_file,
            }

        target.write_text(updated, encoding="utf-8")
        try:
            compile(target.read_text(encoding="utf-8"), str(target), "exec")
        except SyntaxError as exc:
            target.write_text(original, encoding="utf-8")
            return {
                "status": "failed",
                "error": f"written fallback failed compile and was rolled back: {exc}",
                "target_file": target_file,
            }

        return {
            "status": "success",
            "changed": True,
            "file_path": str(target),
            "goal": goal,
            "added_functions": [item["name"] for item in missing],
            "message": "已在目标模块追加 expected function fallback。",
        }

    def _missing_expected_functions(
        self,
        target_file: str,
        expected_functions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        import ast

        path = self.project_root / target_file
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            defined = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            }
        except Exception:
            defined = set()

        missing = []
        for item in expected_functions:
            name = str(item.get("name", "")).strip()
            if name and name not in defined:
                missing.append({**item, "name": name})
        return missing

    def _render_expected_function_block(
        self,
        lesson: AgentLesson,
        goal: str,
        expected_functions: List[Dict[str, Any]],
        primary_result: Dict[str, Any],
    ) -> str:
        blocks = [
            "# --- LengXiaobei deterministic self-evolution fallback ---",
            "# Added because the primary LLM-generated patch failed validation.",
        ]
        primary_error = str(primary_result.get("error", "")) if isinstance(primary_result, dict) else ""
        for item in expected_functions:
            name = self._safe_function_name(item["name"])
            blocks.append("")
            blocks.append(f"def {name}(*args, **kwargs):")
            blocks.append('    """Deterministic fallback capability generated by self-evolution.')
            blocks.append("")
            blocks.append(f"    Lesson: {lesson.id}")
            blocks.append(f"    Goal: {goal[:240]}")
            if primary_error:
                blocks.append(f"    Primary failure: {primary_error[:160]}")
            blocks.append('    """')
            blocks.append("    context = args[0] if args else kwargs.get('context') or kwargs.get('code_context') or ''")
            blocks.append("    text = str(context).strip()")
            blocks.append("    if not text:")
            blocks.append("        return None")
            blocks.append("    signals = []")
            blocks.append("    lowered = text.lower()")
            blocks.append("    if 'error' in lowered or 'fail' in lowered or '异常' in text or '失败' in text:")
            blocks.append("        signals.append('优先定位失败路径并补充最小验证。')")
            blocks.append("    if 'todo' in lowered or 'pass' in lowered:")
            blocks.append("        signals.append('发现占位实现，建议补成可测试的真实逻辑。')")
            blocks.append("    if len(text) > 800:")
            blocks.append("        signals.append('上下文较长，建议先拆分为单文件小步修改。')")
            blocks.append("    if not signals:")
            blocks.append("        signals.append('建议保持小步改动，并在修改后运行核心测试。')")
            blocks.append("    return {'source': 'self_evolution_fallback', 'signals': signals, 'confidence': 0.55}")
        return "\n".join(blocks)

    @staticmethod
    def _safe_function_name(name: str) -> str:
        import re

        safe = re.sub(r"\W+", "_", str(name).strip())
        if not re.match(r"^[A-Za-z_]", safe):
            safe = f"generated_{safe}"
        return safe or "generated_capability"

    def _verify(self, target_file: str = "", expected_functions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """跑核心测试 + 可调用性检查。

        如果 expected_functions 非空，会做两层验证：
          1. AST 扫 target_file，看每个 expected name 是否定义
          2. import target_file 模块，看名字真的能 getattr 出来且 callable

        任一层失败 → success=False，lesson 会被标 failed。
        """
        commands = [
            ["python3", "-m", "compileall", "-q", "src"],
            ["pytest", "tests/test_core_modules.py", "-q"],
        ]
        outputs = []
        for cmd in commands:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                outputs.append({
                    "command": " ".join(cmd),
                    "returncode": proc.returncode,
                    "stdout": proc.stdout[-1000:],
                    "stderr": proc.stderr[-1000:],
                })
                if proc.returncode != 0:
                    return {"success": False, "outputs": outputs, "reason": "tests failed"}
            except Exception as exc:
                outputs.append({"command": " ".join(cmd), "error": str(exc)})
                return {"success": False, "outputs": outputs, "reason": f"test exception: {exc}"}

        # 能力可调用性闭环检查
        cap_check = self._check_capability(target_file, expected_functions or [])
        result = {
            "success": cap_check["all_callable"],
            "outputs": outputs,
            "capability_check": cap_check,
        }
        if not cap_check["all_callable"]:
            result["reason"] = (
                "expected_functions 中有函数未真的被加进去或不可调用 — "
                f"missing={cap_check.get('missing')}, "
                f"errors={cap_check.get('callable_errors')}"
            )
        return result

    def _check_capability(self, target_file: str, expected_functions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """对每个 expected function，先 AST 看是否定义，再 import 看是否可调用。"""
        import ast as _ast
        import importlib as _il
        import sys as _sys

        if not expected_functions or not target_file:
            return {
                "all_callable": True,
                "skipped": True,
                "reason": "no expected_functions to check",
            }

        path = self.project_root / target_file
        if not path.is_file():
            return {
                "all_callable": False,
                "missing": [f["name"] for f in expected_functions],
                "reason": "target file missing",
            }

        # AST 扫
        try:
            tree = _ast.parse(path.read_text(encoding="utf-8"))
            defined = set()
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                    defined.add(node.name)
        except Exception as exc:
            return {
                "all_callable": False,
                "missing": [f["name"] for f in expected_functions],
                "reason": f"AST parse failed: {exc}",
            }

        expected_names = [f["name"] for f in expected_functions]
        found = [n for n in expected_names if n in defined]
        missing = [n for n in expected_names if n not in defined]

        # import + getattr + callable 三连检查
        callable_errors: List[str] = []
        if found:
            try:
                project_root_str = str(self.project_root)
                if project_root_str not in _sys.path:
                    _sys.path.insert(0, project_root_str)
                mod_name = target_file.replace("/", ".").rsplit(".py", 1)[0]
                module = None
                if mod_name in _sys.modules:
                    loaded = _sys.modules[mod_name]
                    loaded_file = getattr(loaded, "__file__", "")
                    if loaded_file and Path(loaded_file).resolve() == path.resolve():
                        module = _il.reload(loaded)
                if module is None:
                    try:
                        module = _il.import_module(mod_name)
                        loaded_file = getattr(module, "__file__", "")
                        if not loaded_file or Path(loaded_file).resolve() != path.resolve():
                            module = None
                    except Exception:
                        module = None
                if module is None:
                    spec = _il.util.spec_from_file_location(f"_lx_check_{path.stem}_{int(time.time() * 1000)}", path)
                    if spec is None or spec.loader is None:
                        raise ImportError(f"cannot load spec for {target_file}")
                    module = _il.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                for name in found:
                    obj = getattr(module, name, None)
                    if obj is None:
                        callable_errors.append(f"{name}: 模块顶层找不到（可能被嵌在 class 内）")
                    elif not callable(obj):
                        callable_errors.append(f"{name}: 存在但不可调用 (type={type(obj).__name__})")
            except Exception as exc:
                callable_errors.append(f"import 失败: {exc}")

        all_callable = bool(found) and not missing and not callable_errors
        return {
            "all_callable": all_callable,
            "expected": expected_names,
            "found": found,
            "missing": missing,
            "callable_errors": callable_errors,
        }

    def _assess_change_quality(self, target_file: str, before: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """检查改动是否"实质性"——区分三种情况：
        - True       : 真改了函数（LLM 生成的智能代码）
        - 'degraded' : 改了函数但全是 fallback 占位（启发式 if-else，没真智能）
        - False      : 没改函数（只追加 dict / 元数据）
        """
        import ast
        import hashlib

        FALLBACK_MARKERS = (
            "Deterministic fallback capability generated by self-evolution",
            "self_evolution_fallback",
            "deterministic self-evolution fallback",
        )

        before_item = before.get(target_file) or {}
        after_path = self.project_root / target_file

        if not after_path.is_file():
            return {"substantive": False, "reason": "after file missing"}

        try:
            after_src = after_path.read_text(encoding="utf-8")
        except Exception as exc:
            return {"substantive": False, "reason": f"cannot read after: {exc}"}

        def _func_class_info(src: str) -> Dict[str, Dict[str, Any]]:
            """返回 {name: {sig_hash, is_fallback, body_size}}"""
            try:
                tree = ast.parse(src)
            except Exception:
                return {}
            info: Dict[str, Dict[str, Any]] = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    try:
                        body_src = ast.unparse(node) if hasattr(ast, "unparse") else str(node.body)
                    except Exception:
                        body_src = node.name
                    is_fallback = any(marker in body_src for marker in FALLBACK_MARKERS)
                    info[node.name] = {
                        "sig_hash": hashlib.sha256(body_src.encode("utf-8")).hexdigest(),
                        "is_fallback": is_fallback,
                        "body_size": len(body_src),
                    }
            return info

        before_src = before_item.get("content", "") if before_item.get("exists") else ""

        if not before_src:
            # 新文件
            after_info = _func_class_info(after_src)
            if not after_info:
                return {"substantive": False, "reason": "new file but no defs"}
            fb_count = sum(1 for v in after_info.values() if v["is_fallback"])
            sub = "degraded" if fb_count == len(after_info) else True
            return {
                "substantive": sub,
                "reason": (f"new file; {fb_count}/{len(after_info)} are fallback occupants"
                           if fb_count else "new file with real definitions"),
                "added_or_changed": list(after_info.keys()),
                "before_def_count": 0,
                "after_def_count": len(after_info),
                "fallback_count": fb_count,
            }

        before_info = _func_class_info(before_src)
        after_info = _func_class_info(after_src)

        added = [n for n in after_info if n not in before_info]
        changed = [
            n for n in after_info
            if n in before_info and after_info[n]["sig_hash"] != before_info[n]["sig_hash"]
        ]
        removed = [n for n in before_info if n not in after_info]

        # 看 added/changed 中有多少是 fallback 占位
        new_or_changed = added + changed
        fallback_funcs = [n for n in new_or_changed if after_info[n]["is_fallback"]]
        real_funcs = [n for n in new_or_changed if not after_info[n]["is_fallback"]]

        if not new_or_changed and not removed:
            substantive = False
            reason = f"only non-def content changed (bytes diff: {len(after_src) - len(before_src):+d})"
        elif real_funcs:
            # 至少有一个真函数 → True
            substantive = True
            reason = (f"added={len(added)} changed={len(changed)} removed={len(removed)}"
                     + (f" ({len(fallback_funcs)} of which are fallback)" if fallback_funcs else ""))
        elif fallback_funcs:
            # 全是 fallback 占位 → degraded
            substantive = "degraded"
            reason = (f"only fallback occupants added: {fallback_funcs}. "
                     f"LLM 主路径失败 → 系统写了死板的 if-else 占位，并非真智能代码。")
        else:
            # 只删了函数
            substantive = True
            reason = f"removed={len(removed)}"

        return {
            "substantive": substantive,
            "reason": reason,
            "added": added,
            "changed_funcs": changed,
            "removed": removed,
            "real_funcs": real_funcs,
            "fallback_funcs": fallback_funcs,
            "before_def_count": len(before_info),
            "after_def_count": len(after_info),
        }


    def _apply_to_learned_capabilities(self, lesson: AgentLesson, goal: str) -> Dict[str, Any]:
        self._ensure_safe_lesson_target()
        target = self.project_root / SAFE_LESSON_TARGET
        original = target.read_text(encoding="utf-8")
        if lesson.id in original:
            return {
                "status": "success",
                "file_path": str(target),
                "goal": goal,
                "changed": False,
                "message": "Lesson 已经沉淀到源码能力注册表。",
            }

        entry = {
            "id": lesson.id,
            "topic": lesson.topic,
            "source": lesson.source,
            "capability": lesson.capability,
            "pattern": lesson.pattern,
            "adaptation": lesson.adaptation,
            "goal": goal,
            "created_at": lesson.created_at,
        }
        insertion = "\nLEARNED_CAPABILITIES.append(\n"
        insertion += self._format_python_dict(entry, indent=4)
        insertion += "\n)\n"

        target.write_text(original.rstrip() + "\n" + insertion, encoding="utf-8")
        return {
            "status": "success",
            "file_path": str(target),
            "goal": goal,
            "changed": True,
            "message": "Lesson 已沉淀为源码级 learned capability。",
        }

    def _ensure_safe_lesson_target(self) -> None:
        target = self.project_root / SAFE_LESSON_TARGET
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            '"""Learned capabilities registry."""\n\n'
            "from __future__ import annotations\n\n"
            "from typing import Any, Dict, List\n\n\n"
            "LEARNED_CAPABILITIES: List[Dict[str, Any]] = []\n\n\n"
            "def list_learned_capabilities() -> List[Dict[str, Any]]:\n"
            "    return list(LEARNED_CAPABILITIES)\n",
            encoding="utf-8",
        )

    @staticmethod
    def _format_python_dict(data: Dict[str, Any], indent: int = 4) -> str:
        from pprint import pformat

        return pformat(data, indent=indent, width=100, sort_dicts=False)

    def _record_run(
        self,
        lesson: AgentLesson,
        target_file: str,
        goal: str,
        status: str,
        result: Dict[str, Any],
    ) -> None:
        runs = load_json(str(self.runs_path), default=[])
        if not isinstance(runs, list):
            runs = []
        run = SelfEvolutionRun(
            id=f"run_{int(time.time())}",
            topic=lesson.topic,
            lesson_id=lesson.id,
            target_file=target_file,
            goal=goal,
            status=status,
            result=result,
            created_at=time.time(),
        )
        runs.append(run.to_dict())
        atomic_write_json(str(self.runs_path), runs)

    def _record_code_change(
        self,
        lesson: AgentLesson,
        target_file: str,
        goal: str,
        before: Dict[str, Dict[str, Any]],
        result: Dict[str, Any],
    ) -> None:
        paths = {target_file, SAFE_LESSON_TARGET}
        file_path = result.get("file_path") if isinstance(result, dict) else ""
        if file_path:
            try:
                paths.add(str(Path(file_path).resolve().relative_to(self.project_root)))
            except Exception:
                pass
        fallback_target = result.get("fallback_target") if isinstance(result, dict) else ""
        if fallback_target:
            paths.add(str(fallback_target))
        verification = result.get("verification", {}) if isinstance(result, dict) else {}
        self.change_logger.record(
            actor="lengxiaobei",
            trigger="self_evolution.apply_lesson",
            summary=f"应用 lesson {lesson.id}: {lesson.capability}",
            before=before,
            after_paths=paths,
            result=result,
            verification=verification,
            metadata={
                "lesson_id": lesson.id,
                "topic": lesson.topic,
                "source": lesson.source,
                "target_file": target_file,
                "goal": goal,
            },
        )

    @staticmethod
    def _check_boundary(file_path: str) -> str:
        normalized = file_path.replace("\\", "/").lstrip("./")
        basename = normalized.rsplit("/", 1)[-1]
        for blocked in BLOCKED_FILES:
            if normalized.endswith(blocked) or basename == blocked:
                return f"禁止修改核心文件: {file_path}"
        for confirm in CONFIRM_FILES:
            if normalized.endswith(confirm):
                return f"需要宿主确认: {file_path}"
        if normalized.startswith("memory/") and "agent_lessons" not in normalized:
            return f"需要宿主确认: {file_path}"
        return "allow"
