"""
LLM 驱动代码审查器 — 自主 AI Agent 代码质量评估
================================================

核心理念：不再使用硬编码扣分表和静态分析阈值，
而是通过 LLM 提示词让 AI 自行推理判断代码质量。

设计原则：
- 评分由 LLM 基于语义理解推理，不是固定扣分规则
- 严重性判断由 LLM 根据代码上下文决定，不是枚举映射
- 静态分析仅用于最基础的语法检查，不作为主要评判手段
"""

import ast
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from .llm import chat


class Severity(Enum):
    TRIVIAL = "trivial"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class Category(Enum):
    SYNTAX = "syntax"
    STYLE = "style"
    PERFORMANCE = "performance"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    READABILITY = "readability"
    MAINTAINABILITY = "maintainability"
    TESTABILITY = "testability"


@dataclass
class Issue:
    category: Category
    severity: Severity
    description: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class CriticReport:
    file_path: str
    original_code: str
    generated_code: str
    issues: List[Issue] = field(default_factory=list)
    overall_score: float = 0.0
    improvement_suggestions: List[str] = field(default_factory=list)
    needs_revision: bool = True


class CodeCritic:
    """LLM 驱动的代码审查器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()

    def criticize(self, file_path: str, original_code: str, generated_code: str) -> CriticReport:
        report = CriticReport(file_path=file_path, original_code=original_code, generated_code=generated_code)

        syntax_issues = self._check_syntax(generated_code)
        report.issues.extend(syntax_issues)

        llm_result = self._llm_review(file_path, original_code, generated_code)
        report.issues.extend(llm_result.get("issues", []))
        report.overall_score = llm_result.get("overall_score", 50.0)
        report.improvement_suggestions = llm_result.get("improvement_suggestions", [])
        report.needs_revision = llm_result.get("needs_revision", True)

        return report

    def _check_syntax(self, code: str) -> List[Issue]:
        """基础语法检查（唯一保留的静态检查）"""
        try:
            ast.parse(code)
        except SyntaxError as e:
            return [Issue(category=Category.SYNTAX, severity=Severity.CRITICAL,
                          description=f"语法错误: {e}", line_number=e.lineno,
                          suggestion="修复语法错误")]
        return []

    def _llm_review(self, file_path: str, original_code: str, generated_code: str) -> dict:
        """通过 LLM 进行全面的代码审查评估"""
        prompt = f"""你是资深代码审查专家。请对以下代码修改进行全面评估。

文件路径：{file_path}

原始代码：
```python
{original_code[:3000] if len(original_code) > 3000 else original_code}
```

生成/修改后代码：
```python
{generated_code[:3000] if len(generated_code) > 3000 else generated_code}
```

请从以下维度深度分析修改后的代码质量：
1. 代码正确性 - 逻辑是否正确，是否能正常工作
2. 性能影响 - 修改是否会影响性能
3. 安全性 - 是否存在安全风险
4. 可读性 - 代码是否清晰易懂
5. 可维护性 - 修改是否使代码更容易维护
6. 架构合理性 - 修改是否符合架构设计原则
7. 与原始代码的差异分析 - 修改是否合理且必要

请以 JSON 格式返回评估结果：
{{
    "overall_score": 85.0,
    "needs_revision": false,
    "improvement_suggestions": ["建议1", "建议2"],
    "issues": [
        {{
            "category": "syntax/style/performance/security/architecture/readability/maintainability/testability",
            "severity": "trivial/minor/major/critical",
            "description": "问题描述",
            "line_number": null,
            "suggestion": "改进建议"
        }}
    ],
    "summary": "总体评价"
}}

评分标准：
- 90-100: 优秀，代码质量高，可直接合并
- 70-89: 良好，有少量改进空间
- 50-69: 一般，需要一定程度的修改
- 30-49: 较差，存在明显问题
- 0-29: 很差，需要重写

needs_revision 为 true 的情况：overall_score < 60 或存在 critical 级别问题

只返回 JSON，不要有其他内容。"""

        try:
            response = chat(prompt, system="你是资深代码审查专家。你通过深度语义理解来评估代码质量，而非固定规则匹配。只返回JSON。", temperature=0.3)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return self._parse_llm_result(data)
        except Exception as e:
            print(f"[Critic] LLM审查失败: {e}")

        return {"issues": [], "overall_score": 50.0, "improvement_suggestions": ["LLM审查失败，建议人工审查"], "needs_revision": True}

    def _parse_llm_result(self, data: dict) -> dict:
        """解析 LLM 返回的审查结果"""
        issues = []
        for item in data.get("issues", []):
            try:
                cat = Category(item.get("category", "style"))
            except ValueError:
                cat = Category.STYLE
            try:
                sev = Severity(item.get("severity", "minor"))
            except ValueError:
                sev = Severity.MINOR
            issues.append(Issue(
                category=cat, severity=sev,
                description=item.get("description", ""),
                line_number=item.get("line_number"),
                suggestion=item.get("suggestion")
            ))

        score = max(0, min(100, float(data.get("overall_score", 50.0))))
        needs_revision = data.get("needs_revision", score < 60)

        return {
            "issues": issues,
            "overall_score": score,
            "improvement_suggestions": data.get("improvement_suggestions", []),
            "needs_revision": needs_revision
        }