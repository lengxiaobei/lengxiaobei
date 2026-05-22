"""Proposer — 方案提出

让 LLM 分析代码并生成完整的修改后文件。
优化: 给 LLM 完整的文件内容 + 更好的提示词。
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .llm_client import chat_json, generate_code
from .. import llm

logger = logging.getLogger(__name__)


@dataclass
class Proposal:
    """修改方案"""
    improvement_type: str = "code_quality"
    file_path: str = ""
    original_issue: str = ""
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
            original_issue=data.get("original_issue", data.get("issue", "")),
            strategy=data.get("strategy", ""),
            approach=data.get("approach", ""),
            steps=data.get("steps", []),
            success_criteria=data.get("success_criteria", ""),
            confidence=data.get("confidence", 0.8),
            risk_level=data.get("risk_level", "low"),
        )


class Proposer:
    """方案提出器 — LLM 分析代码并生成完整修改后文件"""

    def __init__(self, project_root: str):
        self.project_root = project_root

    def propose(self, improvement: Dict[str, Any], original_code: str) -> Optional[Proposal]:
        """根据改进点分析代码并提出具体方案"""
        issue = improvement.get("issue", "")
        file_path = improvement.get("file", "")
        issue_type = improvement.get("type", "code_quality")

        logger.info(f"[Proposer] analyzing: {issue[:80]}")

        # 简单修复直接返回，不走 LLM
        if "newline" in issue.lower() and "eof" in issue.lower() or "missing final newline" in issue.lower():
            return Proposal(
                improvement_type=issue_type,
                file_path=file_path,
                original_issue=issue,
                strategy="add missing final newline",
                approach="append newline character, no logic changes",
                steps=["check file ending", "append newline", "verify"],
                success_criteria="file ends with newline, tests pass",
                confidence=0.95,
                risk_level="low",
            )

        # LLM 生成方案
        plan = self._generate_plan(issue, issue_type, original_code)
        if not plan:
            return None

        return plan

    def generate_new_code(self, original_code: str, proposal: Proposal) -> str:
        """生成修改后的完整代码文件"""
        if self._is_newline_only(proposal):
            return original_code if original_code.endswith("\n") else original_code + "\n"

        # 重要：给 LLM 完整的原文件内容，要求生成完整输出
        return self._generate_full_code(original_code, proposal)

    @staticmethod
    def _is_newline_only(proposal: Proposal) -> bool:
        texts = [
            proposal.original_issue or "",
            proposal.strategy or "",
            proposal.approach or "",
            " ".join(proposal.steps or []),
        ]
        combined = " ".join(texts).lower()
        return "newline" in combined and ("eof" in combined or "final" in combined)

    def _generate_plan(self, issue: str, issue_type: str, code: str) -> Optional[Proposal]:
        """让 LLM 分析代码并生成修改方案"""
        code_excerpt = code[:8000]  # 大文件的截断版本

        prompt = f"""You are a senior Python engineer. Analyze the following code and create a detailed improvement plan.

ISSUE: {issue}
TYPE: {issue_type}

CODE:
```python
{code_excerpt}
```

Return a JSON object with:
- strategy: high-level strategy description (1 sentence)
- approach: specific technical approach (1-2 sentences)
- steps: list of 3-5 concrete implementation steps
- success_criteria: how to verify the change is correct
- confidence: 0.0-1.0 estimate of success probability
- risk_level: one of "low", "medium", "high"

IMPORTANT:
- Be conservative. If unsure, set confidence below 0.5.
- Prefer small, focused changes over large refactors.
- Consider backward compatibility.

Return ONLY valid JSON, no markdown, no explanation."""

        try:
            data = chat_json(prompt, temperature=0.2, fallback=None)
            if not data:
                return None
            return Proposal(
                improvement_type=issue_type,
                file_path="",
                original_issue=issue,
                strategy=data.get("strategy", "improve code quality"),
                approach=data.get("approach", "analyze and implement improvements"),
                steps=data.get("steps", ["analyze code", "implement changes", "verify"]),
                success_criteria=data.get("success_criteria", "tests pass"),
                confidence=data.get("confidence", 0.7),
                risk_level=data.get("risk_level", "medium"),
            )
        except Exception as e:
            logger.error(f"[Proposer] plan generation failed: {e}")
            return None

    def _generate_full_code(self, original_code: str, proposal: Proposal) -> str:
        """让 LLM 生成完整修改后的代码文件

        关键: 要求输出完整文件，不是 diff。
        LLM 输出后 executor._sanitize() 会清理 markdown 包装。
        """
        # 限制输入长度，但尽量给完整上下文
        code_input = original_code[:12000]

        prompt = f"""You are an expert Python developer. Rewrite the following file to implement the specified improvement.

FILE CONTENT:
```python
{code_input}
```

IMPROVEMENT:
Issue: {proposal.original_issue}
Strategy: {proposal.strategy}
Approach: {proposal.approach}
Steps:
{chr(10).join(f'- {s}' for s in proposal.steps)}
Success Criteria: {proposal.success_criteria}

RULES:
1. Output the COMPLETE file, not a diff. Include ALL imports, ALL functions, ALL classes.
2. Make ONLY the necessary changes. Do not refactor unrelated code.
3. Follow PEP 8 and the existing code style.
4. Keep all existing imports. Add new imports only if needed.
5. Do NOT add markdown code fences (no ```python, no ```).
6. Do NOT add explanations before or after the code.
7. The first line of your output must be valid Python (import, class, def, or # comment).
8. The output must compile with Python 3.8+.

Output ONLY the complete Python source code."""

        return generate_code(prompt)