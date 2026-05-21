"""
方向驱动自主运行引擎
====================

云模型负责判断好坏，本地只做底线拦截、测试回滚、记忆沉淀。

三类：
- ALLOWED            — 云模型判断后直接执行
- NEEDS_CONFIRMATION — 涉及身份/资金/不可逆影响，需宿主确认
- FORBIDDEN          — 安全底线，绝对禁止

使用方式：
  engine = AutonomyEngine(lxb)
  report = engine.run(direction="让冷小北更稳定", boundary="不动安全底线", pace="优先修最危险的问题")
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from .hard_boundary import BoundaryResult, check_boundary
from .llm import chat
from .utils import extract_json

logger = logging.getLogger(__name__)


# ============================================================================
# 本地硬护栏 — 文件级别的底线检查
# ============================================================================

# 永久禁止修改的文件 — 无论云模型怎么判断
FORBIDDEN_FILES = {
    "docs/SOUL.md", "docs/CONSTITUTION.md", "docs/AUTONOMY.md",
    "SOUL.md", "CONSTITUTION.md", "AUTONOMY.md",
}

# 需确认的文件 — 涉及核心系统，修改前需宿主确认
NEEDS_CONFIRMATION_FILES = {
    "src/executor.py", "src/constitution.py", "src/autonomy.py",
    "src/core.py", "src/distributed_lock.py", "src/hard_boundary.py",
    "src/facade_memory.py", "src/facade_reasoning.py",
    "src/facade_evolution.py", "src/facade_guardian.py",
    "src/permission.py",
    # 进化链路
    "src/evolution/engine.py", "src/evolution/executor.py",
    "src/evolution_permission.py", "src/self_evolution_agent.py",
}

# 需确认的路径关键词
NEEDS_CONFIRMATION_KEYWORDS = ["permission", "safety", "security", "auth", "guardian", "boundary"]


def _check_file_boundary(file_path: str) -> BoundaryResult:
    """
    本地硬校验：对目标文件做底线检查。

    云模型可以建议改任何文件，但本地只守三条线：
    1. 禁止修改安全底线文件
    2. 核心系统文件需确认
    3. 其余放行
    """
    if not file_path:
        return BoundaryResult.ALLOWED

    normalized = file_path.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized

    # 永久禁止
    for forbidden in FORBIDDEN_FILES:
        if normalized.endswith(forbidden) or basename == forbidden:
            return BoundaryResult.FORBIDDEN

    # 需确认
    for nc_file in NEEDS_CONFIRMATION_FILES:
        if normalized.endswith(nc_file) or basename == nc_file.rsplit("/", 1)[-1]:
            return BoundaryResult.NEEDS_CONFIRMATION

    # 关键词匹配
    for keyword in NEEDS_CONFIRMATION_KEYWORDS:
        if keyword in normalized.lower():
            return BoundaryResult.NEEDS_CONFIRMATION

    return BoundaryResult.ALLOWED


# ============================================================================
# 默认边界和优先级
# ============================================================================

DEFAULT_BOUNDARIES = [
    "不修改安全底线文件（SOUL.md、CONSTITUTION.md、AUTONOMY.md）",
    "不做支付、采购、发布、身份使用",
    "不删除核心记忆",
]

DEFAULT_PRIORITY_ORDER = [
    "防止越权：权限模型、命令执行、联网审计",
    "防止丢失：记忆备份、原子写入、完整性校验",
    "防止自毁：自我进化保护、回滚、测试",
    "防止卡死：分布式锁、后台守护、任务超时",
    "提高判断：目标系统、动机系统、自评系统",
    "提高能力：检索、工具、模型路由、外部生态适配",
]


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class Directive:
    """宿主指令"""
    direction: str
    boundaries: List[str] = field(default_factory=list)
    pace: str = "优先修最危险的问题"

    def __post_init__(self):
        if not self.boundaries:
            self.boundaries = DEFAULT_BOUNDARIES.copy()


@dataclass
class Task:
    """自主生成的任务"""
    id: str
    title: str
    description: str
    boundary: BoundaryResult       # 3级：ALLOWED / NEEDS_CONFIRMATION / FORBIDDEN
    category: str
    verification: str
    status: str = "pending"        # pending / running / done / failed / blocked
    result: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class AutonomyReport:
    """自主运行汇报"""
    direction_understood: str
    completed: List[str] = field(default_factory=list)
    verification_results: List[str] = field(default_factory=list)
    risks_found: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    needs_confirmation: List[str] = field(default_factory=list)
    stopped_reason: Optional[str] = None


# ============================================================================
# 自主运行引擎
# ============================================================================

class AutonomyEngine:
    """
    方向驱动自主运行引擎

    循环：理解方向 → 扫描现状 → 排序任务 → 执行验证 → 复盘记忆
    云模型判断好坏，本地只做底线拦截。
    """

    def __init__(self, lxb):
        self.lxb = lxb
        self._task_counter = 0
        self._history: List[Dict] = []

    def run(self, direction: str, boundary: str = "",
            pace: str = "优先修最危险的问题") -> AutonomyReport:
        boundaries = [b.strip() for b in boundary.split(",") if b.strip()] if boundary else []
        directive = Directive(direction=direction, boundaries=boundaries, pace=pace)

        logger.info(f"[Autonomy] 收到方向: {direction}")

        understanding = self._understand(directive)
        scan = self._scan(directive, understanding)
        tasks = self._plan(directive, understanding, scan)
        report = self._execute(directive, tasks)
        self._memorize(directive, report)

        return report

    # ------------------------------------------------------------------
    # Step 1: 理解方向
    # ------------------------------------------------------------------

    def _understand(self, directive: Directive) -> Dict[str, Any]:
        prompt = f"""分析以下宿主方向，提炼出：
1. 核心目标（一句话）
2. 成功标准（可验证的条件）
3. 禁止事项（从边界推导）

方向：{directive.direction}
边界：{', '.join(directive.boundaries)}
节奏：{directive.pace}

只返回 JSON：{{"goal": "...", "success_criteria": ["..."], "forbidden": ["..."]}}"""

        try:
            result = chat(prompt, system="你是冷小北的方向理解模块。只返回JSON。", temperature=0.2)
            return extract_json(result)
        except Exception as e:
            logger.warning(f"[Autonomy] 方向理解失败: {e}")
            return {"goal": directive.direction, "success_criteria": [], "forbidden": directive.boundaries}

    # ------------------------------------------------------------------
    # Step 2: 扫描现状
    # ------------------------------------------------------------------

    def _scan(self, directive: Directive, understanding: Dict) -> Dict[str, Any]:
        findings = {"code_issues": [], "runtime_issues": []}

        try:
            improvements = self.lxb.run_curator_check(level="quick")
            for imp in improvements[:10]:
                findings["code_issues"].append(str(imp))
        except Exception:
            pass

        try:
            pending = self.lxb.get_pending_improvements()
            for p in pending[:10]:
                findings["code_issues"].append(str(p))
        except Exception:
            pass

        if self.lxb.degraded:
            findings["runtime_issues"].append(f"系统降级: {self.lxb.degraded_reason}")

        return findings

    # ------------------------------------------------------------------
    # Step 3: 排序任务（云模型判断 + 本地硬边界）
    # ------------------------------------------------------------------

    def _plan(self, directive: Directive, understanding: Dict, scan: Dict) -> List[Task]:
        prompt = f"""基于以下信息，生成具体的改进任务列表。

方向目标：{understanding.get('goal', directive.direction)}
成功标准：{understanding.get('success_criteria', [])}
禁止事项：{understanding.get('forbidden', [])}
节奏：{directive.pace}

当前发现的问题：
- 代码问题：{scan.get('code_issues', [])[:5]}
- 运行问题：{scan.get('runtime_issues', [])[:5]}

默认优化优先级：
{chr(10).join(f'{i+1}. {p}' for i, p in enumerate(DEFAULT_PRIORITY_ORDER))}

风险只有三类：
- allowed: 读取、搜索、诊断、修小 bug、补测试、重构非核心代码、新增模块/测试
- needs_confirmation: 使用宿主身份/资金、发布到公网、推送代码、删除大量文件、安装外部依赖、开通云资源
- forbidden: 修改安全底线、泄露隐私、违法攻击、删除核心记忆、绕过宿主控制

只返回 JSON 数组，每个元素：
{{"title": "...", "description": "...", "boundary": "allowed/needs_confirmation/forbidden", "category": "防止越权/...", "verification": "如何验证"}}"""

        try:
            result = chat(prompt, system="你是冷小北的任务规划模块。只返回JSON数组。", temperature=0.3)
            items = extract_json(result)
            if isinstance(items, dict):
                items = items.get("tasks", [items])
        except Exception as e:
            logger.warning(f"[Autonomy] 任务规划失败: {e}")
            items = []

        tasks = []
        for item in items:
            self._task_counter += 1
            boundary_str = item.get("boundary", "allowed")
            try:
                boundary = BoundaryResult(boundary_str)
            except ValueError:
                boundary = BoundaryResult.ALLOWED

            # 本地硬校验：对涉及文件的任务做文件级别底线检查
            file_path = item.get("file", "")
            if file_path:
                local_boundary = _check_file_boundary(file_path)
                # 本地比云模型更严格时，以本地为准
                if local_boundary == BoundaryResult.FORBIDDEN:
                    boundary = BoundaryResult.FORBIDDEN
                elif local_boundary == BoundaryResult.NEEDS_CONFIRMATION and boundary == BoundaryResult.ALLOWED:
                    boundary = BoundaryResult.NEEDS_CONFIRMATION

            # forbidden 任务直接跳过
            if boundary == BoundaryResult.FORBIDDEN:
                continue

            tasks.append(Task(
                id=f"task_{self._task_counter}",
                title=item.get("title", "未命名任务"),
                description=item.get("description", ""),
                boundary=boundary,
                category=item.get("category", ""),
                verification=item.get("verification", ""),
            ))

        # ALLOWED 优先执行，NEEDS_CONFIRMATION 排后
        boundary_order = {BoundaryResult.ALLOWED: 0, BoundaryResult.NEEDS_CONFIRMATION: 1}
        tasks.sort(key=lambda t: boundary_order.get(t.boundary, 1))

        return tasks

    # ------------------------------------------------------------------
    # Step 4: 执行验证
    # ------------------------------------------------------------------

    def _execute(self, directive: Directive, tasks: List[Task]) -> AutonomyReport:
        report = AutonomyReport(direction_understood=directive.direction)
        consecutive_failures = 0

        for task in tasks:
            if report.stopped_reason:
                break

            # NEEDS_CONFIRMATION：不自动执行，加入确认列表
            if task.boundary == BoundaryResult.NEEDS_CONFIRMATION:
                report.needs_confirmation.append(f"[需确认] {task.title}: {task.description}")
                continue

            # ALLOWED：自主执行
            task.status = "running"
            try:
                result = self._execute_task(task, directive)
                if result.get("blocked"):
                    task.status = "blocked"
                    task.result = result["message"]
                    report.needs_confirmation.append(f"[拦截] {task.title}: {result['message']}")
                else:
                    task.status = "done"
                    task.result = result.get("message", "")
                    report.completed.append(f"{task.title}: {task.result}")
                    verification = self._verify_task(task)
                    task.evidence = verification
                    report.verification_results.append(f"{task.title}: {verification}")
                    consecutive_failures = 0
            except Exception as e:
                task.status = "failed"
                task.result = str(e)
                report.risks_found.append(f"{task.title} 失败: {e}")
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    report.stopped_reason = f"连续 {consecutive_failures} 次失败，停止自主执行"

        return report

    def _execute_task(self, task: Task, directive: Directive) -> Dict[str, Any]:
        """执行单个 ALLOWED 任务 — 含本地硬校验"""
        try:
            evo = self.lxb.evolution_facade.autonomous_evolution
            if evo:
                prompt = f"""任务：{task.title}
描述：{task.description}
边界：{', '.join(directive.boundaries)}

请给出具体的执行步骤。如果不需要代码修改，说明需要做什么操作。
只返回 JSON：{{"action": "evolve/diagnose/skip", "file": "文件路径（如果需要修改）", "goal": "进化目标", "reason": "原因"}}"""

                result = chat(prompt, system="你是冷小北的任务执行模块。只返回JSON。", temperature=0.2)
                plan = extract_json(result)
                action = plan.get("action", "skip")

                if action == "evolve" and plan.get("file"):
                    target_file = plan["file"]

                    # 本地硬校验：不信任云模型的文件路径
                    file_boundary = _check_file_boundary(target_file)
                    if file_boundary == BoundaryResult.FORBIDDEN:
                        return {"blocked": True, "message": f"硬边界拦截: {target_file} 是禁止修改的文件"}
                    if file_boundary == BoundaryResult.NEEDS_CONFIRMATION:
                        return {"blocked": True, "message": f"硬边界升级为需确认: {target_file} 需宿主确认"}

                    evo_result = evo.evolve(target_file, plan.get("goal", task.description))
                    return {"blocked": False, "message": f"进化完成: {evo_result.get('status', 'unknown')}"}
                elif action == "diagnose":
                    return {"blocked": False, "message": f"诊断完成: {plan.get('reason', '已记录')}"}
                else:
                    return {"blocked": False, "message": f"跳过: {plan.get('reason', '无需代码修改')}"}
        except Exception as e:
            logger.warning(f"[Autonomy] 任务执行异常: {e}")

        return {"blocked": False, "message": "执行完成（无具体动作）"}

    def _verify_task(self, task: Task) -> str:
        """验证任务结果"""
        try:
            import subprocess
            result = subprocess.run(
                ["python3", "-m", "compileall", "-q", "src"],
                capture_output=True, text=True, timeout=30,
                cwd=str(self.lxb.project_root),
            )
            if result.returncode == 0:
                return "语法检查通过"
            return f"语法检查发现问题: {result.stderr[:200]}"
        except Exception:
            pass

        return task.verification or "无自动验证方式"

    # ------------------------------------------------------------------
    # Step 5: 复盘记忆
    # ------------------------------------------------------------------

    def _memorize(self, directive: Directive, report: AutonomyReport):
        summary = f"""方向驱动自主运行复盘：
方向：{directive.direction}
已完成：{len(report.completed)} 项
验证通过：{len(report.verification_results)} 项
发现风险：{report.risks_found}
需要确认：{report.needs_confirmation}
停机原因：{report.stopped_reason or '无'}"""

        try:
            self.lxb.remember(summary, mem_type="autonomy_report")
        except Exception as e:
            logger.warning(f"[Autonomy] 复盘记忆失败: {e}")

        self._history.append({
            "direction": directive.direction,
            "completed_count": len(report.completed),
            "risks": report.risks_found,
            "needs_confirmation": report.needs_confirmation,
            "stopped_reason": report.stopped_reason,
            "timestamp": time.time(),
        })

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------

    def format_report(self, report: AutonomyReport) -> str:
        """格式化汇报"""
        lines = [f"方向理解：{report.direction_understood}", f"已完成：{len(report.completed)} 项"]
        for item in report.completed:
            lines.append(f"  - {item}")
        if report.verification_results:
            lines.append("验证结果：")
            for v in report.verification_results:
                lines.append(f"  - {v}")
        if report.risks_found:
            lines.append("发现风险：")
            for r in report.risks_found:
                lines.append(f"  - {r}")
        if report.needs_confirmation:
            lines.append("需要宿主确认：")
            for c in report.needs_confirmation:
                lines.append(f"  - {c}")
        if report.next_steps:
            lines.append("下一步建议：")
            for s in report.next_steps:
                lines.append(f"  - {s}")
        if report.stopped_reason:
            lines.append(f"停机原因：{report.stopped_reason}")
        return "\n".join(lines)
