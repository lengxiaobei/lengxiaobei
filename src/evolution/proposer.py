"""Proposer — 方案提出

基于 Curator 发现的改进点，让 LLM 生成具体的修改方案。
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .llm_client import chat_json, generate_code
from .models import AIDecision, EvolutionContext

logger = logging.getLogger(__name__)


@dataclass
class Proposal:
    """修改方案"""
    improvement_type: str
    file_path: str
    original_issue: str
    strategy: str = ""
    approach: str = ""
    steps: List[str] = field(default_factory=list)
    success_criteria: str = ""
    confidence: float = 0.8
    risk_level: str = "low"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Proposal":
        return cls(
            improvement_type=data.get("improvement_type", "code_quality"),
            file_path=data.get("file_path", ""),
            original_issue=data.get("original_issue", ""),
            strategy=data.get("strategy", ""),
            approach=data.get("approach", ""),
            steps=data.get("steps", []),
            success_criteria=data.get("success_criteria", ""),
            confidence=data.get("confidence", 0.8),
            risk_level=data.get("risk_level", "low"),
        )


class Proposer:
    """方案提出器 — LLM 生成具体修改方案"""

    def __init__(self, project_root: str):
        self.project_root = project_root

    def propose(self, improvement: Dict[str, Any], original_code: str) -> Proposal:
        """根据改进点提出具体方案"""
        logger.info(f"[Proposer] 分析改进点: {improvement.get('issue', improvement.get('type', ''))}")

        issue = improvement.get("issue", "")
        if "文件末尾缺少换行" in issue:
            return Proposal(
                improvement_type=improvement.get("type", "code_quality"),
                file_path=improvement.get("file", ""),
                original_issue=issue,
                strategy="补齐文件末尾换行",
                approach="追加一个换行符，不改变代码逻辑",
                steps=["检查文件结尾", "追加换行符", "运行验证"],
                success_criteria="文件以换行符结尾，测试通过",
                confidence=0.95,
                risk_level="low",
            )

        plan = self._generate_plan(improvement, original_code)
        risk = self._assess_risk(plan, original_code)

        plan.risk_level = risk
        return plan

    def generate_new_code(self, original_code: str, proposal: Proposal) -> str:
        """生成修改后的代码 — 优先基于步骤生成 patch 级改动"""
        if self._is_final_newline_fix(proposal):
            return original_code if original_code.endswith("\n") else original_code + "\n"
        if len(original_code) > 300:
            return self._generate_patch(original_code, proposal)
        return self._generate_full(original_code, proposal)

    @staticmethod
    def _is_final_newline_fix(proposal: Proposal) -> bool:
        text = " ".join([
            proposal.original_issue or "",
            proposal.strategy or "",
            proposal.approach or "",
            " ".join(proposal.steps or []),
        ])
        return "文件末尾缺少换行" in text or "final newline" in text.lower()

    def _generate_patch(self, original_code: str, proposal: Proposal) -> str:
        """生成 diff/patch — 只输出需要修改的行和上下文"""
        prompt = f"""你是代码修改专家。请以最小化改动的方式修改代码。

目标: {proposal.original_issue}
策略: {proposal.strategy}
步骤:
{chr(10).join(f'- {s}' for s in proposal.steps)}

原始代码:
```python
{original_code[:10000]}
```

要求:
1. 只修改必要的行，不改动无关代码
2. 添加新函数时放在文件末尾合适位置
3. 遵循 PEP 8 和已有代码风格
4. 保留所有已有导入

只返回完整的修改后 Python 代码，不要任何解释。"""
        return generate_code(prompt)

    def _generate_full(self, original_code: str, proposal: Proposal) -> str:
        """整文件生成 — 仅用于小文件"""
        prompt = f"""你是代码生成专家。请根据修改方案生成完整的修改后代码。

目标: {proposal.original_issue}
策略: {proposal.strategy}
步骤:
{chr(10).join(f'- {s}' for s in proposal.steps)}

原始代码:
```python
{original_code[:8000]}
```

要求:
1. 解决识别的问题
2. 遵循 PEP 8 和最佳实践
3. 保持代码风格一致
4. 保留所有现有功能

只返回完整的 Python 代码，不要任何解释。"""
        return generate_code(prompt)

    def _generate_plan(self, improvement: Dict[str, Any], code: str) -> Proposal:
        """LLM 生成修改计划"""
        issue = improvement.get("issue", "")
        prompt = f"""你是代码改进专家。请分析以下改进点并制定详细方案。

改进点: {issue}
类型: {improvement.get('type', 'code_quality')}

代码(部分):
```python
{code[:5000]}
```

请返回:
```json
{{
  "strategy": "策略描述",
  "approach": "具体方法",
  "steps": ["步骤1", "步骤2", "步骤3"],
  "success_criteria": "成功标准",
  "confidence": 0.8
}}
```

只返回JSON。"""

        try:
            data = chat_json(prompt, temperature=0.3, fallback={})
        except Exception:
            data = {}

        return Proposal(
            improvement_type=improvement.get("type", "code_quality"),
            file_path=improvement.get("file", ""),
            original_issue=issue,
            strategy=data.get("strategy", "逐步优化代码"),
            approach=data.get("approach", "分析问题并实施改进"),
            steps=data.get("steps", ["分析代码", "实施修改", "验证结果"]),
            success_criteria=data.get("success_criteria", "代码质量提升，测试通过"),
            confidence=data.get("confidence", 0.7),
        )

    def _assess_risk(self, proposal: Proposal, code: str) -> str:
        """LLM 评估风险等级"""
        prompt = f"""评估以下代码修改的风险等级。

修改策略: {proposal.strategy}
修改步骤: {', '.join(proposal.steps)}
代码片段:
```python
{code[:1000]}
```

风险等级:
- low: 简单重构、注释修改、小功能增强
- medium: 功能修改、新函数添加、小范围重构
- high: 核心逻辑修改、架构调整、API变更
- critical: 系统核心模块修改

只返回: low/medium/high/critical"""

        try:
            from .. import llm
            response = llm.chat(prompt, system="你是风险评估专家。", temperature=0.1)
            response = response.strip().lower()
            for level in ["critical", "high", "medium", "low"]:
                if level in response:
                    return level
        except Exception:
            pass
        return "medium"
