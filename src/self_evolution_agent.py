"""
SelfEvolutionAgent — 简化自演化管线
=====================================
云模型做判断，本地只做底线拦截、测试回滚、记忆沉淀。

管线:
  CloudJudge(判断是否值得+生成方案) → HardBoundary(三道检查) → CodeEvolver(执行) → TestRunner(验证) → Memory(记录)

不再有细碎风险分级。
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .hard_boundary import HardBoundary, BoundaryResult, check_boundary
from .llm import chat
from .utils import extract_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class EvolutionDecision:
    """云模型做的判断"""
    worth_doing: bool
    reasoning: str
    target_file: str = ""
    approach: str = ""          # 改动策略
    patch_description: str = ""  # 改动描述
    confidence: float = 0.0
    risk_note: str = ""          # 模型自己认为的风险点


@dataclass
class EvolutionResult:
    """一次进化的完整结果"""
    run_id: str
    decision: EvolutionDecision = None
    boundary: Any = None          # BoundaryCheck
    execution: Dict[str, Any] = field(default_factory=dict)
    test: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"       # pending | judging | rejected | executed | verified | recorded | rolled_back
    error: str = ""


# ---------------------------------------------------------------------------
# LLM Prompt — 云模型负责"该不该改、怎么改"
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """你是一个自治编程 Agent 的判断层。分析以下改进机会，判断是否值得执行。

改进机会：
{improvement}

当前系统状态：
{context}

请以 JSON 返回判断：
{{
  "worth_doing": true/false,
  "reasoning": "为什么值得/不值得做的推理过程",
  "target_file": "要修改的文件路径",
  "approach": "改动策略（如 rename/reorder/extract/optimize）",
  "patch_description": "具体改动描述",
  "confidence": 0.0-1.0,
  "risk_note": "模型观察到的风险点（如实写，不隐藏）"
}}

注意：
- 谨慎判断。不确定的事情不值得做。
- 克制。三行相似代码好过一个过早抽象。
- 考虑这条改动对系统稳定性的影响。
- 只返回 JSON，不要其他文字。"""


# ---------------------------------------------------------------------------
# SelfEvolutionAgent
# ---------------------------------------------------------------------------

class SelfEvolutionAgent:
    """简化自演化管线 — 云判断 + 硬边界 + 测试 + 记忆"""

    def __init__(self, project_root: str,
                 memory=None,
                 test_runner=None,
                 audit_trail=None):
        self.project_root = Path(project_root)
        self.memory = memory
        self.test_runner = test_runner
        self.audit = audit_trail
        self.boundary = HardBoundary()
        self.history: List[EvolutionResult] = []

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def evolve(self, improvement: dict) -> EvolutionResult:
        """执行一次完整的进化判断+执行管线"""
        run_id = f"ev-{int(time.time())}"
        result = EvolutionResult(run_id=run_id)

        # ---- Step 1: CloudJudge — 云模型判断 ----
        result.status = "judging"
        decision = self._judge(improvement)
        result.decision = decision

        if not decision.worth_doing:
            result.status = "rejected"
            result.error = f"云模型判断不值得做: {decision.reasoning}"
            self._record(result)
            return result

        # ---- Step 2: HardBoundary — 硬边界检查 ----
        action_desc = f"修改 {decision.target_file}: {decision.patch_description}"
        check = check_boundary(action_desc, context={"file": decision.target_file})
        result.boundary = check

        if check.result == BoundaryResult.FORBIDDEN:
            result.status = "rejected"
            result.error = f"触碰禁止边界: {check.reason}"
            self._record(result)
            return result

        if check.result == BoundaryResult.NEEDS_CONFIRMATION:
            result.status = "rejected"
            result.error = f"需宿主确认: {check.reason}"
            # 不自动执行，等宿主确认
            self._record(result)
            return result

        # ---- Step 3: CodeEvolver — 执行改动 ----
        result.status = "executed"
        result.execution = self._apply_change(decision)

        if not result.execution.get("success"):
            result.status = "rolled_back"
            result.error = result.execution.get("error", "执行失败")
            self._record(result)
            return result

        # ---- Step 4: TestRunner — 测试验证 ----
        result.status = "verified"
        if self.test_runner:
            result.test = self._run_tests(decision.target_file)
            if not result.test.get("success"):
                self._rollback(decision.target_file, result.execution.get("backup"))
                result.status = "rolled_back"
                result.error = result.test.get("error", "测试未通过")
                self._record(result)
                return result

        # ---- Step 5: Memory — 记录经验 ----
        result.status = "recorded"
        self._record(result)
        self.history.append(result)

        logger.info("进化完成: %s", decision.patch_description[:60])
        return result

    # ------------------------------------------------------------------
    # 各步骤实现
    # ------------------------------------------------------------------

    def _judge(self, improvement: dict) -> EvolutionDecision:
        """CloudJudge: 让云模型判断是否值得做"""
        context = {
            "existing_modules": self._list_src_files(),
            "recent_evolutions": len(self.history),
        }

        prompt = JUDGE_PROMPT.format(
            improvement=str(improvement),
            context=str(context),
        )
        try:
            result = chat(prompt, system="你是自治编程 Agent 的判断层。只返回 JSON。")
            data = extract_json(result)
            return EvolutionDecision(**data)
        except Exception as e:
            logger.warning("云模型判断失败: %s", e)
            return EvolutionDecision(worth_doing=False, reasoning=f"判断失败: {e}")

    def _apply_change(self, decision: EvolutionDecision) -> Dict[str, Any]:
        """CodeEvolver: 读取源码 → LLM 生成 patch → 写入文件"""
        target = os.path.join(str(self.project_root), decision.target_file)
        if not os.path.exists(target):
            return {"success": False, "error": f"文件不存在: {target}"}

        try:
            with open(target, encoding="utf-8") as f:
                original = f.read()

            # 备份
            backup = target + f".bak.{int(time.time())}"
            with open(backup, "w", encoding="utf-8") as f:
                f.write(original)

            # LLM 生成修改后的代码
            new_code = self._generate_patch(original, decision)
            if not new_code:
                return {"success": False, "error": "LLM 未生成有效代码"}

            # 安全检查：新代码不能包含危险模式
            if not self._is_safe_code(new_code):
                return {"success": False, "error": "生成的代码包含危险模式，拒绝写入"}

            # 写入
            with open(target, "w", encoding="utf-8") as f:
                f.write(new_code)

            return {
                "success": True,
                "file": decision.target_file,
                "backup": backup,
                "approach": decision.approach,
                "lines_changed": abs(new_code.count("\n") - original.count("\n")),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _generate_patch(self, original_code: str, decision: EvolutionDecision) -> str:
        """让 LLM 根据决策生成修改后的完整代码"""
        prompt = f"""你是代码修改专家。请根据以下决策修改代码。

修改目标: {decision.patch_description}
策略: {decision.approach}
风险提示: {decision.risk_note}

原始代码:
```python
{original_code[:12000]}
```

要求:
1. 只修改必要的部分，不改动无关代码
2. 保持原有代码风格和导入
3. 不要删除现有功能
4. 只返回完整的修改后 Python 代码，不要任何解释或 markdown 标记"""

        try:
            result = chat(prompt, system="你是冷小北的代码修改模块。只返回代码，不要解释。", temperature=0.2)
            # 去掉可能的 markdown 代码围栏
            code = result.strip()
            if code.startswith("```"):
                lines = code.split("\n")
                # 去掉首行 ```python 和末行 ```
                lines = [l for l in lines if not l.strip().startswith("```")]
                code = "\n".join(lines)
            return code.strip()
        except Exception as e:
            logger.warning("LLM patch 生成失败: %s", e)
            return ""

    @staticmethod
    def _is_safe_code(code: str) -> bool:
        """检查生成的代码是否包含危险模式"""
        dangerous = [
            "os.system(", "subprocess.call(", "subprocess.Popen(",
            "eval(", "exec(", "__import__('os')",
            "shutil.rmtree(", "os.remove('/",
            "rm -rf", "format(c=", "/dev/sd",
        ]
        code_lower = code.lower()
        for pattern in dangerous:
            if pattern.lower() in code_lower:
                return False
        return True

    def _run_tests(self, file_path: str) -> Dict[str, Any]:
        """TestRunner: 运行测试"""
        try:
            if self.test_runner:
                result = self.test_runner.verify(
                    os.path.join(str(self.project_root), file_path)
                )
                return {"success": result.success, "summary": str(result)}
            return {"success": True, "summary": "无测试运行器，跳过"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _rollback(self, file_path: str, backup: str):
        """回滚改动"""
        if backup and os.path.exists(backup):
            try:
                with open(backup) as f:
                    original = f.read()
                with open(file_path, "w") as f:
                    f.write(original)
                logger.info("已回滚: %s", file_path)
            except Exception as e:
                logger.warning("回滚失败: %s", e)

    def _record(self, result: EvolutionResult):
        """Memory: 记录经验"""
        if self.audit:
            try:
                self.audit.log_phase(result.run_id, "judge", {
                    "worth_doing": result.decision.worth_doing if result.decision else False,
                    "reasoning": result.decision.reasoning if result.decision else "",
                })
                self.audit.log_phase(result.run_id, "boundary", {
                    "result": result.boundary.result.value if result.boundary else "N/A",
                })
                self.audit.log_phase(result.run_id, "status", {
                    "status": result.status, "error": result.error,
                })
            except Exception:
                pass

        if self.memory and result.status == "recorded":
            try:
                self.memory.store(
                    f"进化 {result.run_id}: {result.decision.patch_description[:200]}",
                    mem_type="episode",
                )
            except Exception:
                pass

    def _list_src_files(self) -> List[str]:
        """列出源码文件列表"""
        src_dir = self.project_root / "src"
        if not src_dir.is_dir():
            return []
        return [
            str(p.relative_to(self.project_root))
            for p in src_dir.rglob("*.py")
            if "__pycache__" not in str(p)
        ][:20]


def create_self_evolution_agent(project_root: str, memory=None,
                                test_runner=None, audit_trail=None) -> SelfEvolutionAgent:
    return SelfEvolutionAgent(project_root, memory, test_runner, audit_trail)
