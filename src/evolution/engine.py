"""EvolutionEngine — 瘦编排器

进化流程: Discover → Propose → Execute → Verify
治理内嵌: Constitution 合规 + 权限审批 + 熔断器在每个关键步骤

架构:
- Curator: 策展人 — 分级调度 + 去重
- Proposer: 方案提出 — 优先 diff/patch 模式
- SafeExecutor: 安全执行 — 权限前置 + 备份/写入/回滚
- PytestVerifier: 测试验证 — 不通过禁止 cleanup
- SkillsStore: 知识库 — 沉淀成功经验
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from ..integrity_checker import IntegrityChecker
from ..hard_boundary import BoundaryResult, check_boundary
from ..circuit_breaker import check_health, record_success, record_failure

from .models import (
    EvolutionPhase, EvolutionStatus, RiskLevel,
    Goal, EvolutionContext, AIDecision, ImprovementRecord,
)
from .curator import Curator, Improvement
from .proposer import Proposer, Proposal
from .executor import SafeExecutor, ExecutionResult
from .verifier import PytestVerifier, TestResult
from .skills_store import SkillsStore
from .audit import AuditTrail, AuditEntry

logger = logging.getLogger(__name__)


class AutonomousEvolutionEngine:
    """自主进化引擎 — 治理内嵌版本"""

    def __init__(self, project_root: str = None,
                 permission_manager=None,
                 circuit_breaker=None,
                 constitution=None):
        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.project_root = project_root

        self.curator = Curator(project_root)
        self.proposer = Proposer(project_root)
        self.executor = SafeExecutor(project_root, permission_manager, constitution)
        self.verifier = PytestVerifier(project_root)
        self.skills = SkillsStore(project_root)
        self.audit = AuditTrail(project_root)

        self.permission_manager = permission_manager
        self.circuit_breaker = circuit_breaker
        self.constitution = constitution

        self.current_score = 0.0
        self.last_evolution_time: float = 0
        self.evolution_cooldown: float = 600

    # ------------------------------------------------------------------
    # evolve — 四步流程 + 治理内嵌
    # ------------------------------------------------------------------

    def evolve(self, file_path: str, goal_description: str,
               constraints: List[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        if constraints is None:
            constraints = []

        abs_path = file_path if os.path.isabs(file_path) else os.path.join(self.project_root, file_path)
        rel_path = os.path.relpath(abs_path, self.project_root)

        logger.info(f"{'='*60}")
        logger.info(f"evolve: {goal_description}")
        logger.info(f"{'='*60}")

        run_id = f"ev-{int(time.time())}-{os.path.basename(abs_path)}"
        audit_entry = self.audit.start_run(run_id, trigger="manual")

        # ---- 熔断 ----
        if not self._cb_check_health():
            return {"status": "failed", "error": "Circuit breaker tripped"}

        # ---- 完整性 (strict 模式：只阻断 SOUL/CONSTITUTION 等安全底线变动) ----
        integrity_check = IntegrityChecker(self.project_root).verify_integrity_strict()
        if integrity_check.get("status") != "success":
            self._cb_record_failure("Strict integrity violated")
            return {
                "status": "failed",
                "error": integrity_check.get("error", "Strict integrity check failed"),
                "strict_violations": integrity_check.get("strict_violations", []),
            }

        if not os.path.exists(abs_path):
            return {"status": "failed", "error": f"File not found: {abs_path}"}

        with open(abs_path) as f:
            original_code = f.read()

        rec = ImprovementRecord(
            file=rel_path, issue=goal_description,
            priority="medium", source="manual",
        )

        # ---- Step 1: Propose ----
        proposal = self.proposer.propose(rec.to_dict(), original_code)
        self.audit.log_phase(audit_entry, "discover", {"issue": goal_description, "file": rel_path})
        self.audit.log_phase(audit_entry, "triage", {"risk_level": getattr(proposal, "risk_level", "unknown") if proposal else "N/A"})

        if not proposal or proposal.confidence < 0.5:
            self.audit.finish_and_write(audit_entry, "rejected", "方案置信度过低")
            return {"status": "failed", "error": "方案置信度过低"}

        self.audit.log_phase(audit_entry, "propose", {
            "strategy": proposal.strategy,
            "approach": proposal.approach,
            "confidence": proposal.confidence,
            "risk_level": proposal.risk_level if hasattr(proposal, "risk_level") else "unknown",
        })

        # ---- Constitution 合规检查 ----
        if self.constitution and not self._is_trivial_autofix(goal_description):
            try:
                allowed, reason, _ = self.constitution.is_action_allowed(
                    f"修改 {rel_path}: {goal_description}"
                )
                self.audit.log_phase(audit_entry, "review", {
                    "constitution": "allowed" if allowed else "denied",
                    "reason": reason,
                    "permission": "N/A",
                })
                if not allowed:
                    logger.warning(f"Constitution 拒绝: {reason}")
                    self.audit.finish_and_write(audit_entry, "rejected", f"Constitution: {reason}")
                    return {"status": "failed", "error": f"Constitution: {reason}"}
            except Exception as e:
                logger.error(f"Constitution 检查异常: {e}")
                pass

        if dry_run:
            return {
                "status": "dry_run",
                "file_path": abs_path,
                "proposal": {
                    "strategy": proposal.strategy,
                    "approach": proposal.approach,
                    "steps": proposal.steps,
                    "risk_level": proposal.risk_level,
                },
            }

        # ---- Step 2: Execute (含权限前置) ----
        rec.risk_level = proposal.risk_level
        new_code = self.proposer.generate_new_code(original_code, proposal)
        exec_result = self.executor.execute(abs_path, new_code, rec)

        if not exec_result.success:
            self.audit.log_phase(audit_entry, "execute", {"success": False, "error": exec_result.error})
            if exec_result.error == "permission_denied":
                self.audit.finish_and_write(audit_entry, "rejected", "权限审批未通过")
                return {"status": "rejected", "error": "权限审批未通过"}
            self.audit.finish_and_write(audit_entry, "failed", exec_result.error)
            return {"status": "failed", "error": exec_result.error}

        self.audit.log_phase(audit_entry, "execute", {
            "success": True,
            "file": rel_path,
            "backup": getattr(exec_result, "backup_path", "N/A"),
        })

        # ---- Step 3: Verify ----
        test_result = self.verifier.verify(abs_path)

        if not test_result.success:
            logger.error(f"测试未通过: {test_result.summary}")
            self.executor.rollback(exec_result)
            self._cb_record_failure("Tests failed")
            self.audit.log_phase(audit_entry, "verify", {"tests_passed": 0, "error": test_result.summary})
            self.audit.log_phase(audit_entry, "record", {"rollback": True, "reason": test_result.summary})
            self.audit.finish_and_write(audit_entry, "failed", f"测试未通过: {test_result.summary}")
            return {"status": "failed", "error": f"测试未通过: {test_result.summary}"}

        logger.info(f"测试通过: {test_result.summary}")
        self.executor.cleanup(exec_result)

        # ---- Step 4: Record ----
        self.skills.record(rec.to_dict(), proposal, original_code, new_code, test_result)
        self.audit.log_phase(audit_entry, "verify", {"tests_passed": True, "summary": test_result.summary})
        self.audit.log_phase(audit_entry, "record", {"skill_recorded": True, "rollback": False})
        self.audit.finish_and_write(audit_entry, "success")
        self._cb_record_success()
        self.last_evolution_time = time.time()
        self.current_score = max(0.5, self.current_score + 0.1)

        # 发布事件
        try:
            from ..kairos.events import emit
            emit("evolution.completed", {"status": "success", "run_id": run_id, "file": rel_path})
        except Exception:
            pass

        result = {
            "status": "success",
            "file_path": abs_path,
            "goal": goal_description,
            "test_result": test_result.summary,
            "score": self.current_score,
        }
        logger.info(f"进化完成: {result['status']}")
        return result

    # ------------------------------------------------------------------
    # evolve_autonomously — idle 门控 + 分级调度
    # ------------------------------------------------------------------

    def evolve_autonomously(self, direction: str = "", boundaries: str = "") -> Dict[str, Any]:
        """
        自主进化循环 — 对齐 AUTONOMY.md 的自主决策循环

        Args:
            direction: 宿主方向（可选），用于指导进化优先级
            boundaries: 宿主边界（可选），用于约束进化范围
        """
        # 降级模式检查
        try:
            from ..llm import has_any_key
            if not has_any_key():
                return {"status": "degraded", "message": "LLM 不可用，跳过自主进化"}
        except Exception:
            pass

        logger.info("自主进化循环启动")

        # idle 门控
        if time.time() - self.last_evolution_time < self.evolution_cooldown:
            return {"status": "cooldown", "message": f"冷却中 ({self.evolution_cooldown}s)"}

        improvements = self._discover_best()
        if not improvements:
            return {"status": "no_improvements", "message": "未发现改进点"}

        logger.info(f"发现 {len(improvements)} 个改进点")

        # 如果有方向，用方向对改进点排序（与方向相关的优先）
        if direction:
            improvements = self._sort_by_direction(improvements, direction)

        # HardBoundary 风险分级：3级过滤
        safe_improvements = []
        needs_confirmation = []
        for imp in improvements:
            boundary = self._assess_improvement_risk(imp)
            if boundary == BoundaryResult.FORBIDDEN:
                logger.warning(f"跳过禁止修改: {imp.issue[:50]}")
                continue
            if boundary == BoundaryResult.NEEDS_CONFIRMATION:
                needs_confirmation.append(imp)
                continue
            safe_improvements.append(imp)

        result = self.execute_evolutions(safe_improvements)

        # 附加需要确认的改进点
        if needs_confirmation:
            result["needs_confirmation"] = [
                f"[NEEDS_CONFIRMATION] {imp.file}: {imp.issue[:80]}" for imp in needs_confirmation
            ]

        # 停机条件：连续失败
        failed_count = sum(
            1 for r in result.get("results", [])
            if r.get("result", {}).get("status") not in ("success", "skipped")
        )
        if failed_count >= 2:
            result["stopped_reason"] = f"连续 {failed_count} 次进化失败，停止自主执行"

        return result

    def _assess_improvement_risk(self, imp: ImprovementRecord) -> BoundaryResult:
        """评估改进点的边界等级 — 3级：FORBIDDEN / NEEDS_CONFIRMATION / ALLOWED"""
        issue_lower = (imp.issue or "").lower()
        file_lower = (imp.file or "").lower()

        # 修改安全底线相关文件 -> FORBIDDEN
        forbidden_files = ["soul.md", "constitution.md", "autonomy.md"]
        if any(f in file_lower for f in forbidden_files):
            return BoundaryResult.FORBIDDEN

        # 修改核心权限/执行器/硬边界 -> NEEDS_CONFIRMATION
        core_files = ["executor.py", "constitution.py", "core.py", "facade_", "permission", "hard_boundary"]
        if any(f in file_lower for f in core_files):
            return BoundaryResult.NEEDS_CONFIRMATION

        # 修小 bug / 补测试 -> ALLOWED
        low_risk_keywords = ["缺少换行", "unused import", "typo", "test", "lint"]
        if any(k in issue_lower for k in low_risk_keywords):
            return BoundaryResult.ALLOWED

        # 其他 -> ALLOWED（让云模型判断）
        return BoundaryResult.ALLOWED

    def _sort_by_direction(self, improvements: List[ImprovementRecord], direction: str) -> List[ImprovementRecord]:
        """根据方向对改进点排序 — 与方向关键词匹配的优先"""
        direction_lower = direction.lower()
        # 方向关键词映射
        direction_keywords = {
            "稳定": ["bug", "fix", "error", "crash", "fail", "异常", "修复", "死锁", "卡死"],
            "自主": ["autonomy", "自主", "方向", "驱动", "goal", "target"],
            "记忆": ["memory", "记忆", "备份", "backup", "存储", "丢失"],
            "安全": ["security", "安全", "权限", "permission", "注入", "越权"],
            "性能": ["performance", "性能", "慢", "timeout", "超时", "优化"],
        }

        def relevance_score(imp: ImprovementRecord) -> int:
            score = 0
            text = f"{imp.issue or ''} {imp.file or ''}".lower()
            for keyword, matches in direction_keywords.items():
                if keyword in direction_lower:
                    for m in matches:
                        if m in text:
                            score += 1
            return score

        improvements.sort(key=relevance_score, reverse=True)
        return improvements

    def _discover_best(self) -> List[ImprovementRecord]:
        """分级发现 — 优先增量，回退全量"""
        results: List[ImprovementRecord] = []

        # 1. quick check
        try:
            for imp in self.curator.quick_check():
                rec = ImprovementRecord.from_curator(imp, "curator")
                if rec.file and not self.curator.is_duplicate(rec.signature):
                    results.append(rec)
        except Exception:
            pass

        # 2. incremental
        if not results and self.curator.should_incremental_review():
            try:
                for imp in self.curator.incremental_review():
                    rec = ImprovementRecord.from_curator(imp, "curator")
                    if rec.file and not self.curator.is_duplicate(rec.signature):
                        results.append(rec)
            except Exception:
                pass

        # 3. full review
        if not results and self.curator.should_full_review():
            try:
                for imp in self.curator.review():
                    rec = ImprovementRecord.from_curator(imp, "curator")
                    if rec.file and not self.curator.is_duplicate(rec.signature):
                        results.append(rec)
            except Exception:
                pass

        return results

    @staticmethod
    def _is_trivial_autofix(goal_description: str) -> bool:
        """确定性、无语义变化的低风险自动修复。"""
        return "文件末尾缺少换行" in goal_description

    # ------------------------------------------------------------------
    # discover_improvements / execute_evolutions
    # ------------------------------------------------------------------

    def discover_improvements(self, improvements: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        logger.info("发现改进点...")
        if improvements:
            valid = []
            for imp in improvements:
                rec = ImprovementRecord.from_kairos(imp)
                if rec is None:
                    continue
                if self.curator.is_duplicate(rec.signature):
                    continue
                valid.append(rec.to_dict())
            return valid

        return [r.to_dict() for r in self._discover_best()]

    def execute_evolutions(self, improvements: List[Dict[str, Any]]) -> Dict[str, Any]:
        logger.info(f"执行 {len(improvements)} 个进化...")

        results = []
        success_count = 0
        max_execute = min(len(improvements), 3)

        for i, imp_data in enumerate(improvements[:max_execute]):
            rec = ImprovementRecord.from_kairos(imp_data) if isinstance(imp_data, dict) else imp_data
            if rec is None:
                results.append({"improvement": imp_data, "result": {"status": "skipped", "error": "缺必填字段"}})
                continue

            abs_path = rec.abspath(self.project_root)
            if not os.path.exists(abs_path):
                results.append({"improvement": rec.to_dict(), "result": {"status": "skipped", "error": "文件不存在"}})
                continue

            logger.info(f"[{i+1}/{max_execute}] {rec.type}: {rec.issue[:50]}")

            try:
                result = self.evolve(abs_path, rec.issue)
                results.append({"improvement": rec.to_dict(), "result": result})
                if result.get("status") == "success":
                    success_count += 1
                    # 只标记成功的进化，失败的保留以供重试
                    self.curator.mark_seen(rec.signature)
                else:
                    logger.warning(f"进化失败，保留在待处理队列: {rec.issue[:50]}")
            except Exception as e:
                import traceback
                logger.error(f"进化异常: {e}\n{traceback.format_exc()}")
                results.append({"improvement": rec.to_dict(), "result": {"status": "failed", "error": str(e)}})

        return {
            "status": "success" if success_count > 0 else "no_changes",
            "total": max_execute,
            "success_count": success_count,
            "improvements": [r.get("improvement", {}) for r in results],
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # circuit breaker helpers
    # ------------------------------------------------------------------

    def _cb_check_health(self) -> bool:
        if self.circuit_breaker is not None:
            return self.circuit_breaker.check_health()
        return check_health()

    def _cb_record_success(self):
        if self.circuit_breaker is not None:
            self.circuit_breaker.record_success()
        else:
            record_success()

    def _cb_record_failure(self, error_msg: str):
        if self.circuit_breaker is not None:
            self.circuit_breaker.record_failure(error_msg)
        else:
            record_failure(error_msg)


def create_autonomous_evolution_engine(project_root: str = None,
                                       permission_manager=None,
                                       circuit_breaker=None,
                                       constitution=None) -> AutonomousEvolutionEngine:
    return AutonomousEvolutionEngine(
        project_root,
        permission_manager=permission_manager,
        circuit_breaker=circuit_breaker,
        constitution=constitution,
    )


if __name__ == "__main__":
    engine = AutonomousEvolutionEngine()
    result = engine.evolve_autonomously()
    logger.info(json.dumps(result, indent=2, ensure_ascii=False))
