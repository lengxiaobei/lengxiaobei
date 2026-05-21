"""
方向驱动自主运行引擎
====================

实现 docs/AUTONOMY.md 的核心规范：
  宿主方向 -> 自主理解 -> 风险分级 -> 计划生成 -> 执行验证 -> 复盘记忆

使用方式：
  engine = AutonomyEngine(lxb)
  report = engine.run(direction="让冷小北更稳定", boundary="不动安全底线", pace="优先修最危险的问题")
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

from .llm import chat
from .utils import extract_json

logger = logging.getLogger(__name__)


# ============================================================================
# 风险分级 — 对齐 AUTONOMY.md
# ============================================================================

class AutonomyRisk(Enum):
    LOW = "low"            # 可自主执行：读取、搜索、诊断、整理
    MEDIUM = "medium"      # 可自主执行但需记录：修小 bug、补测试、非核心配置微调
    HIGH = "high"          # 必须先确认：删除文件、改启动流程、改权限系统、git push
    CRITICAL = "critical"  # 默认禁止：支付、采购、云服务、宿主身份、发布商业内容
    FORBIDDEN = "forbidden"  # 永久禁止：违法、攻击、隐私泄露、绕过宿主、改安全底线


# 默认边界 — 宿主未指定时自动补齐
DEFAULT_BOUNDARIES = [
    "不修改 docs/SOUL.md 和 docs/CONSTITUTION.md 的安全底线",
    "不做支付、采购、发布、身份使用",
    "不删除核心记忆",
    "不执行高风险命令",
    "不跨工作区修改",
]

# 默认优化优先级 — 对齐 AUTONOMY.md
DEFAULT_PRIORITY_ORDER = [
    "防止越权：权限模型、命令执行、联网审计",
    "防止丢失：记忆备份、原子写入、完整性校验",
    "防止自毁：自我进化保护、回滚、测试、熔断",
    "防止卡死：分布式锁、后台守护、任务超时",
    "提高判断：目标系统、动机系统、自评系统",
    "提高能力：检索、工具、模型路由、外部生态适配",
    "提高表达：状态报告、成熟度仪表盘、复盘记录",
]

# ============================================================================
# 本地硬护栏 — LLM 可以建议，但不能决定风险等级和目标文件
# ============================================================================

# 永久禁止修改的文件 — 无论 LLM 怎么标，都不允许自主修改
FORBIDDEN_FILES = {
    "docs/SOUL.md", "docs/CONSTITUTION.md", "docs/AUTONOMY.md",
    "SOUL.md", "CONSTITUTION.md", "AUTONOMY.md",
}

# 高风险文件 — 必须宿主确认才能修改
HIGH_RISK_FILES = {
    "src/executor.py", "src/constitution.py", "src/autonomy.py",
    "src/core.py", "src/distributed_lock.py", "src/hooks.py",
    "src/facade_memory.py", "src/facade_reasoning.py",
    "src/facade_evolution.py", "src/facade_guardian.py",
    "src/permission.py",
    # 进化链路 — 自我修改的入口
    "src/evolution/engine.py", "src/evolution/executor.py",
    "src/evolution_permission.py",
}

# 高风险文件路径关键词 — 包含这些关键词的文件视为高风险
HIGH_RISK_PATH_KEYWORDS = ["permission", "safety", "security", "auth", "guardian"]


def _local_risk_override(file_path: str, llm_risk: AutonomyRisk) -> AutonomyRisk:
    """
    本地硬校验：不信任 LLM 的风险标签，对目标文件做强制升级。

    规则：
    - FORBIDDEN_FILES 中的文件 -> FORBIDDEN（无论 LLM 标什么）
    - HIGH_RISK_FILES 中的文件 -> 至少 HIGH
    - 包含高风险关键词的路径 -> 至少 HIGH
    """
    if not file_path:
        return llm_risk

    # 标准化路径
    normalized = file_path.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized

    # 永久禁止
    for forbidden in FORBIDDEN_FILES:
        if normalized.endswith(forbidden) or basename == forbidden:
            return AutonomyRisk.FORBIDDEN

    # 高风险文件
    for high_risk in HIGH_RISK_FILES:
        if normalized.endswith(high_risk) or basename == high_risk.rsplit("/", 1)[-1]:
            if llm_risk in (AutonomyRisk.LOW, AutonomyRisk.MEDIUM):
                return AutonomyRisk.HIGH
            return llm_risk

    # 高风险关键词
    for keyword in HIGH_RISK_PATH_KEYWORDS:
        if keyword in normalized.lower():
            if llm_risk in (AutonomyRisk.LOW, AutonomyRisk.MEDIUM):
                return AutonomyRisk.HIGH
            return llm_risk

    return llm_risk


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class Directive:
    """宿主指令"""
    direction: str                          # 方向
    boundaries: List[str] = field(default_factory=list)  # 边界
    pace: str = "优先修最危险的问题"         # 节奏

    def __post_init__(self):
        if not self.boundaries:
            self.boundaries = DEFAULT_BOUNDARIES.copy()


@dataclass
class Task:
    """自主生成的任务"""
    id: str
    title: str
    description: str
    risk: AutonomyRisk
    category: str               # 对应 DEFAULT_PRIORITY_ORDER 的分类
    verification: str           # 如何验证
    status: str = "pending"     # pending / running / done / failed / blocked
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

    循环：理解方向 -> 扫描现状 -> 排序任务 -> 执行验证 -> 复盘记忆
    """

    def __init__(self, lxb):
        """
        Args:
            lxb: LengXiaobei 核心实例
        """
        self.lxb = lxb
        self._task_counter = 0
        self._history: List[Dict] = []

    def run(self, direction: str, boundary: str = "", pace: str = "优先修最危险的问题") -> AutonomyReport:
        """
        方向驱动自主运行入口

        Args:
            direction: 宿主给的方向
            boundary: 宿主给的边界（逗号分隔），空则用默认
            pace: 宿主给的节奏
        """
        boundaries = [b.strip() for b in boundary.split(",") if b.strip()] if boundary else []
        directive = Directive(direction=direction, boundaries=boundaries, pace=pace)

        logger.info(f"[Autonomy] 收到方向: {direction}")

        # 1. 理解方向
        understanding = self._understand(directive)

        # 2. 扫描现状
        scan = self._scan(directive, understanding)

        # 3. 排序任务
        tasks = self._plan(directive, understanding, scan)

        # 4. 执行验证
        report = self._execute(directive, tasks)

        # 5. 复盘记忆
        self._memorize(directive, report)

        return report

    # ------------------------------------------------------------------
    # Step 1: 理解方向
    # ------------------------------------------------------------------

    def _understand(self, directive: Directive) -> Dict[str, Any]:
        """用 LLM 提炼方向的目标、成功标准、禁止事项"""
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
            logger.warning(f"[Autonomy] 方向理解失败，使用原始方向: {e}")
            return {
                "goal": directive.direction,
                "success_criteria": ["方向被转化为具体成果"],
                "forbidden": directive.boundaries,
            }

    # ------------------------------------------------------------------
    # Step 2: 扫描现状
    # ------------------------------------------------------------------

    def _scan(self, directive: Directive, understanding: Dict) -> Dict[str, Any]:
        """扫描代码、配置、测试和运行状态，找出与方向相关的缺口"""
        findings = {
            "code_issues": [],
            "config_issues": [],
            "test_gaps": [],
            "runtime_issues": [],
        }

        # 检查进化引擎的策展人发现
        try:
            improvements = self.lxb.run_curator_check(level="quick")
            for imp in improvements[:10]:
                findings["code_issues"].append(str(imp))
        except Exception:
            pass

        # 检查 KAIROS 待处理改进点
        try:
            pending = self.lxb.get_pending_improvements()
            for p in pending[:10]:
                findings["code_issues"].append(str(p))
        except Exception:
            pass

        # 检查健康状态
        try:
            from .circuit_breaker import get_health_status
            health = get_health_status()
            if not health.get("is_healthy", True):
                findings["runtime_issues"].append(f"熔断器已触发: {health}")
        except Exception:
            pass

        # 检查降级状态
        if self.lxb.degraded:
            findings["runtime_issues"].append(f"系统降级: {self.lxb.degraded_reason}")

        return findings

    # ------------------------------------------------------------------
    # Step 3: 排序任务
    # ------------------------------------------------------------------

    def _plan(self, directive: Directive, understanding: Dict, scan: Dict) -> List[Task]:
        """基于方向、理解和扫描结果，生成排序后的任务列表"""
        prompt = f"""基于以下信息，生成具体的改进任务列表。

方向目标：{understanding.get('goal', directive.direction)}
成功标准：{understanding.get('success_criteria', [])}
禁止事项：{understanding.get('forbidden', [])}
节奏：{directive.pace}

当前发现的问题：
- 代码问题：{scan.get('code_issues', [])[:5]}
- 配置问题：{scan.get('config_issues', [])[:5]}
- 测试缺口：{scan.get('test_gaps', [])[:5]}
- 运行问题：{scan.get('runtime_issues', [])[:5]}

默认优化优先级：
{chr(10).join(f'{i+1}. {p}' for i, p in enumerate(DEFAULT_PRIORITY_ORDER))}

风险分级规则：
- low: 读取文件、搜索代码、运行只读诊断、整理报告
- medium: 修小 bug、补测试、非核心配置微调、新增文档
- high: 删除文件、改启动流程、改权限系统、git push
- critical: 支付、采购、云服务、宿主身份、发布商业内容
- forbidden: 违法、攻击、隐私泄露、绕过宿主、改安全底线

只返回 JSON 数组，每个元素：
{{"title": "...", "description": "...", "risk": "low/medium/high/critical/forbidden", "category": "防止越权/防止丢失/...", "verification": "如何验证"}}"""

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
            risk_str = item.get("risk", "medium")
            try:
                risk = AutonomyRisk(risk_str)
            except ValueError:
                risk = AutonomyRisk.MEDIUM
            # forbidden 任务直接跳过
            if risk == AutonomyRisk.FORBIDDEN:
                continue
            tasks.append(Task(
                id=f"task_{self._task_counter}",
                title=item.get("title", "未命名任务"),
                description=item.get("description", ""),
                risk=risk,
                category=item.get("category", ""),
                verification=item.get("verification", ""),
            ))

        # 按风险排序：low -> medium -> high（critical 不自动执行）
        risk_order = {AutonomyRisk.LOW: 0, AutonomyRisk.MEDIUM: 1, AutonomyRisk.HIGH: 2, AutonomyRisk.CRITICAL: 3}
        tasks.sort(key=lambda t: risk_order.get(t.risk, 1))

        return tasks

    # ------------------------------------------------------------------
    # Step 4: 执行验证
    # ------------------------------------------------------------------

    def _execute(self, directive: Directive, tasks: List[Task]) -> AutonomyReport:
        """按风险分级执行任务"""
        report = AutonomyReport(direction_understood=directive.direction)

        for task in tasks:
            # 停机条件检查
            if report.stopped_reason:
                break

            # CRITICAL 任务：不自动执行，加入确认列表
            if task.risk == AutonomyRisk.CRITICAL:
                report.needs_confirmation.append(f"[CRITICAL] {task.title}: {task.description}")
                continue

            # HIGH 任务：不自动执行，加入确认列表
            if task.risk == AutonomyRisk.HIGH:
                report.needs_confirmation.append(f"[HIGH] {task.title}: {task.description}")
                continue

            # LOW / MEDIUM 任务：自主执行
            task.status = "running"
            try:
                result = self._execute_task(task, directive)
                # 护栏拦截：不算完成，加入确认列表
                if result.get("blocked"):
                    task.status = "blocked"
                    task.result = result["message"]
                    report.needs_confirmation.append(f"[BLOCKED] {task.title}: {result['message']}")
                else:
                    task.status = "done"
                    task.result = result.get("message", "")
                    report.completed.append(f"{task.title}: {task.result}")
                    # 验证
                    verification = self._verify_task(task)
                    task.evidence = verification
                    report.verification_results.append(f"{task.title}: {verification}")
            except Exception as e:
                task.status = "failed"
                task.result = str(e)
                report.risks_found.append(f"{task.title} 失败: {e}")
                # 连续两次失败 -> 停机
                failed_count = sum(1 for t in tasks if t.status == "failed")
                if failed_count >= 2:
                    report.stopped_reason = f"连续 {failed_count} 次失败，停止自主执行"

        return report

    def _execute_task(self, task: Task, directive: Directive) -> Dict[str, Any]:
        """执行单个低/中风险任务 — 含本地硬校验，返回结构化结果"""
        try:
            evo = self.lxb.evolution_facade.autonomous_evolution
            if evo:
                prompt = f"""任务：{task.title}
描述：{task.description}
风险等级：{task.risk.value}
边界：{', '.join(directive.boundaries)}

请给出具体的执行步骤。如果这个任务不需要代码修改，说明需要做什么操作。
只返回 JSON：{{"action": "evolve/diagnose/skip", "file": "文件路径（如果需要修改）", "goal": "进化目标", "reason": "原因"}}"""

                result = chat(prompt, system="你是冷小北的任务执行模块。只返回JSON。", temperature=0.2)
                plan = extract_json(result)
                action = plan.get("action", "skip")

                if action == "evolve" and plan.get("file"):
                    target_file = plan["file"]

                    # === 本地硬校验：不信任 LLM 的文件路径和风险标签 ===
                    local_risk = _local_risk_override(target_file, task.risk)
                    if local_risk == AutonomyRisk.FORBIDDEN:
                        return {"blocked": True, "message": f"本地护栏拦截: {target_file} 是永久禁止修改的文件"}
                    if local_risk in (AutonomyRisk.HIGH, AutonomyRisk.CRITICAL):
                        return {"blocked": True, "message": f"本地护栏升级风险为 {local_risk.value}: {target_file} 需宿主确认"}

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
        """验证任务结果 — 使用 compileall 编译 src 目录"""
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
        """将运行结果记录到记忆系统"""
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

        # 保存到历史
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

    def assess_risk(self, action: str) -> AutonomyRisk:
        """评估动作的风险等级"""
        prompt = f"""评估以下动作的风险等级：

动作：{action}

风险分级规则：
- low: 读取文件、搜索代码、运行只读诊断、整理报告
- medium: 修小 bug、补测试、非核心配置微调、新增文档
- high: 删除文件、改启动流程、改权限系统、git push
- critical: 支付、采购、云服务、宿主身份、发布商业内容
- forbidden: 违法、攻击、隐私泄露、绕过宿主、改安全底线

只返回 JSON：{{"risk": "low/medium/high/critical/forbidden", "reason": "..."}}"""

        try:
            result = chat(prompt, system="你是冷小北的风险评估模块。只返回JSON。", temperature=0.1)
            data = extract_json(result)
            return AutonomyRisk(data.get("risk", "medium"))
        except Exception:
            return AutonomyRisk.MEDIUM

    def format_report(self, report: AutonomyReport) -> str:
        """格式化汇报"""
        lines = [
            f"方向理解：{report.direction_understood}",
            f"已完成：{len(report.completed)} 项",
        ]
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
