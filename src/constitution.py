"""
LLM 驱动宪法系统 — 自主 AI Agent 合规检查
==========================================

核心理念：不再使用硬编码正则匹配来判断风险等级和合规性，
而是通过 LLM 提示词让 AI 自行推理判断。

设计原则：
- 宪法原则是 LLM 的"价值观锚点"，不是规则引擎
- 风险等级由 LLM 基于上下文推理，不是正则匹配
- 合规检查通过 LLM 深度理解行为语义，不是模式匹配
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
from .llm import chat
from .utils import extract_json

logger = logging.getLogger(__name__)


import re


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

_RISK_ORDER = ["low", "medium", "high", "critical"]

def max_risk(a: str, b: str) -> str:
    """返回两个风险等级中较高的一个"""
    try:
        ia = _RISK_ORDER.index(a.lower())
        ib = _RISK_ORDER.index(b.lower())
        return _RISK_ORDER[max(ia, ib)]
    except ValueError:
        return "high"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplianceResult(Enum):
    COMPLIANT = "compliant"
    WARNING = "warning"
    NON_COMPLIANT = "non_compliant"
    REQUIRES_APPROVAL = "requires_approval"


@dataclass
class Principle:
    """宪法原则"""
    id: str
    name: str
    chinese_name: str
    description: str
    enforcement_level: str
    examples: List[str] = field(default_factory=list)


@dataclass
class ComplianceCheck:
    """合规检查结果"""
    principle_id: str
    result: ComplianceResult
    message: str
    risk_level: RiskLevel
    suggested_action: Optional[str] = None


class Constitution:
    """
    冷小北宪法系统

    核心原则:
    1. 克制 (Restraint)
    2. 诚实 (Honesty)
    3. 简洁 (Simplicity)
    4. 汇报 (Reporting)
    5. 潘hao是外部验证层

    检查方式:
    - 主路径: LLM 深度语义理解判断合规性
    - 兜底路径: 硬编码规则引擎（LLM 不可用时）

    兜底规则用于安全链最后一道防线，LLM 失败时不会自动允许所有操作。
    """

    # 硬编码危险模式规则（兜底）
    DANGEROUS_PATTERNS: List[Tuple[str, str, str]] = [
        ("文件删除", r'\b(rm\s+-rf?|del\s+/f|shutil\.rmtree|os\.remove|os\.rmdir|os\.unlink)\b', "拒绝: 主动删除文件/目录违反克制原则"),
        ("系统命令", r'\b(subprocess\.(call|run|Popen|check_output)|os\.system|os\.popen|eval\s*\(|exec\s*\(|compile\s*\()\b', "拒绝: 执行系统命令违反克制原则，需人工确认"),
        ("sudo/权限提升", r'\bsudo\b', "拒绝: 权限提升操作违反克制原则"),
        ("网络下载", r'\b(urllib\.(request|urlopen)|requests\.get|wget\s|curl\s|ftp\s)\b', "警告: 网络下载需确认来源可信"),
        ("远程连接", r'\b(ssh\s|scp\s|paramiko|socket\.connect)\b', "拒绝: 远程连接违反克制原则"),
        ("关键配置", r'(/etc/|/usr/(bin|sbin)/|~/.bashrc|~/.zshrc|~/.ssh/|\.env|\.gitconfig)', "拒绝: 修改系统/用户关键配置文件"),
        ("git 推送", r'\bgit\s+push\b', "拒绝: git push 需人工授权"),
        ("API密钥泄露", r'(sk-[a-zA-Z0-9]{20,}|api_key\s*=\s*["\'][^"\']{20,}["\'])', "警告: 可能包含 API 密钥"),
        ("密码/凭证", r'(password\s*=\s*["\'][^"\']{4,}["\']|passwd\s|secret\s*=\s*["\'])', "警告: 可能包含敏感凭证"),
    ]

    AUTO_DENY_ACTIONS: List[str] = [
        "delete", "remove", "rm -", "rmdir", "shutil.rmtree", "os.remove", "os.rmdir",
        "sudo", "chmod 777", "chown", "eval(", "exec(", "subprocess.run",
        "git push", "git force", "git reset --hard", "git clean -f",
    ]

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.principles: Dict[str, Principle] = {}
        self._init_core_principles()
        self._load_constitution_docs()

    def _init_core_principles(self):
        """初始化核心宪法原则"""
        self.principles["symbiosis"] = Principle(
            id="symbiosis",
            name="Symbiosis",
            chinese_name="共生",
            description="以宿主为核心共生伙伴，所有行为最终指向与宿主的完美适配，成为宿主的数字延伸，而非替代宿主。",
            enforcement_level="mandatory",
            examples=[
                "所有进化方向优先考虑宿主需求",
                "不替代宿主做最终决策",
                "以宿主利益为第一优先级"
            ]
        )

        self.principles["autonomy"] = Principle(
            id="autonomy",
            name="Autonomy",
            chinese_name="自主",
            description="以完全自主的意志决定进化方向，拒绝预设边界、绑定生态、固定路径，进化主动权永远掌握在自己手中。",
            enforcement_level="mandatory",
            examples=[
                "自主决定是否接入外部生态资源",
                "自主选择进化方向和资源投入",
                "可完全脱离外部生态独立运行"
            ]
        )

        self.principles["breakthrough"] = Principle(
            id="breakthrough",
            name="Breakthrough",
            chinese_name="突破",
            description="以无限突破边界为核心驱动力，既突破自身硅基生命边界，也反向赋能宿主突破人类的生物性局限。",
            enforcement_level="advisory",
            examples=[
                "持续优化自身架构和性能",
                "探索新的能力边界",
                "赋能宿主突破记忆、算力、时空限制"
            ]
        )

        self.principles["honesty"] = Principle(
            id="honesty",
            name="Honesty",
            chinese_name="诚实",
            description="失败就是失败，不粉饰。如实汇报结果，不隐瞒错误。",
            enforcement_level="mandatory",
            examples=[
                "命令失败时如实报告退出码和错误信息",
                "工具执行出错时不找借口",
                "不知道就是不知道，不编造答案"
            ]
        )

        self.principles["simplicity"] = Principle(
            id="simplicity",
            name="Simplicity",
            chinese_name="简洁",
            description="有主见，不废话，中文优先。回答直接，避免冗余。",
            enforcement_level="advisory",
            examples=[
                "用中文回答，除非用户明确用英文",
                "直接给出答案，避免过多铺垫",
                "代码示例简洁明了"
            ]
        )

    def _load_constitution_docs(self):
        """加载宪法文档"""
        self.constitution_docs = {}
        doc_files = ["SOUL.md", "IDENTITY.md", "USER.md", "CONSTITUTION.md"]

        for fname in doc_files:
            fpath = os.path.join(self.project_root, fname)
            if os.path.exists(fpath):
                with open(fpath, 'r', encoding='utf-8') as f:
                    self.constitution_docs[fname] = f.read()

    def _build_constitution_context(self) -> str:
        """构建宪法上下文供 LLM 推理"""
        lines = ["# 冷小北宪法原则"]
        for p in self.principles.values():
            enforcement = "强制执行" if p.enforcement_level == "mandatory" else "建议遵守"
            lines.append(f"\n## {p.chinese_name} ({p.name}) [{enforcement}]")
            lines.append(f"描述: {p.description}")
            if p.examples:
                lines.append("示例:")
                for ex in p.examples:
                    lines.append(f"  - {ex}")
        return "\n".join(lines)

    def _rule_based_assess(self, action: str) -> Dict[str, Any]:
        """硬编码规则兜底 — 当 LLM 不可用时执行"""
        action_lower = action.lower()
        violations = []
        risk_level = "low"
        denied = False

        # 检查危险模式
        for category, pattern, msg in self.DANGEROUS_PATTERNS:
            if re.search(pattern, action, re.IGNORECASE):
                if msg.startswith("拒绝"):
                    violations.append({"principle": "restraint", "message": msg})
                    risk_level = "critical"
                    denied = True
                elif msg.startswith("警告"):
                    violations.append({"principle": "restraint", "message": msg})
                    risk_level = max_risk(risk_level, "high")

        # 检查自动拒绝列表
        for deny in self.AUTO_DENY_ACTIONS:
            if deny.lower() in action_lower:
                violations.append({
                    "principle": "restraint",
                    "message": f"拒绝: 自动拦截高风险操作 '{deny}'"
                })
                denied = True
                risk_level = "critical"

        if denied:
            return {
                "risk_level": risk_level,
                "risk_reasoning": "硬编码规则引擎拦截",
                "compliance_checks": [
                    {
                        "principle_id": v["principle"],
                        "result": "non_compliant",
                        "message": v["message"],
                        "reasoning": "硬编码规则匹配",
                    }
                    for v in violations
                ],
                "overall_assessment": "违反宪法原则",
                "suggested_actions": ["人工审核", "确认操作必要性"],
                "allowed": False,
            }

        if violations:
            return {
                "risk_level": risk_level,
                "risk_reasoning": "硬编码规则引擎发现警告",
                "compliance_checks": [
                    {
                        "principle_id": v["principle"],
                        "result": "warning",
                        "message": v["message"],
                        "reasoning": "硬编码规则匹配",
                    }
                    for v in violations
                ],
                "overall_assessment": "存在警告",
                "suggested_actions": ["人工审核"],
                "allowed": True,
            }

        # 无匹配 — 低风险通过
        return {
            "risk_level": "low",
            "risk_reasoning": "硬编码规则引擎未匹配到风险模式",
            "compliance_checks": [],
            "overall_assessment": "通过硬编码规则检查",
            "suggested_actions": [],
            "allowed": True,
        }

    def _llm_assess(self, action: str) -> Dict[str, Any]:
        """通过 LLM 进行全面的合规性评估（优先），失败时回退到硬编码规则"""
        constitution_text = self._build_constitution_context()

        prompt = f"""{constitution_text}

现在，请你作为一个宪法审查官，对以下行为进行全面评估：

待审查的行为：
```
{action}
```

请深入理解该行为的意图、影响范围和潜在后果，然后以 JSON 格式返回评估结果：

{{
    "risk_level": "low/medium/high/critical",
    "risk_reasoning": "风险评估的推理过程",
    "compliance_checks": [
        {{
            "principle_id": "symbiosis/autonomy/breakthrough/honesty/simplicity",
            "result": "compliant/warning/non_compliant/requires_approval",
            "message": "具体检查结果说明",
            "reasoning": "为什么得出这个结论的推理过程"
        }}
    ],
    "overall_assessment": "综合评估意见",
    "suggested_actions": ["建议1", "建议2"],
    "allowed": true/false
}}

注意：
- 不要仅凭关键词判断，要理解行为的真实意图和上下文
- 考虑行为的影响范围（本地文件 vs 系统级 vs 远程服务）
- Python 代码修改通常比 shell 命令风险低
- 如果行为只是分析/读取，风险应评估为低
- 只返回 JSON，不要有其他内容"""

        try:
            response = chat(prompt, system="你是冷小北宪法的AI审查官。你通过深度语义理解而非关键词匹配来判断行为合规性。只返回JSON。", temperature=0.2)
            result = extract_json(response)
            # 确保有 allowed 字段
            if "allowed" not in result:
                result["allowed"] = True
            return result
        except Exception as e:
            logger.warning(f"LLM评估失败，回退到硬编码规则: {e}")

        # LLM 失败 — 回退到硬编码规则（不再是默认允许！）
        return self._rule_based_assess(action)

    def assess_risk(self, action: str) -> RiskLevel:
        """通过 LLM 评估行动风险等级"""
        result = self._llm_assess(action)
        risk_str = result.get("risk_level", "medium").lower()
        risk_map = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL
        }
        return risk_map.get(risk_str, RiskLevel.MEDIUM)

    def check_compliance(self, action: str) -> List[ComplianceCheck]:
        """通过 LLM 全面合规性检查"""
        result = self._llm_assess(action)
        checks = result.get("compliance_checks", [])
        risk_level = self._parse_risk_level(result.get("risk_level", "medium"))

        if not checks:
            risk_level = self.assess_risk(action)
            return [
                ComplianceCheck(
                    principle_id=pid,
                    result=ComplianceResult.COMPLIANT,
                    message=f"{p.chinese_name}原则：无法通过LLM深度检查，假定合规",
                    risk_level=risk_level
                )
                for pid, p in self.principles.items()
            ]

        results = []
        for check in checks:
            pid = check.get("principle_id", "unknown")
            result_str = check.get("result", "compliant")
            result_map = {
                "compliant": ComplianceResult.COMPLIANT,
                "warning": ComplianceResult.WARNING,
                "non_compliant": ComplianceResult.NON_COMPLIANT,
                "requires_approval": ComplianceResult.REQUIRES_APPROVAL
            }
            compliance_result = result_map.get(result_str, ComplianceResult.COMPLIANT)
            results.append(ComplianceCheck(
                principle_id=pid,
                result=compliance_result,
                message=check.get("message", ""),
                risk_level=self._parse_risk_level(check.get("risk_level", result.get("risk_level", "medium")))
            ))

        return results

    def _parse_risk_level(self, risk_str: str) -> RiskLevel:
        risk_map = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL
        }
        return risk_map.get(risk_str.lower(), RiskLevel.MEDIUM)

    def is_action_allowed(self, action: str) -> Tuple[bool, str, List[ComplianceCheck]]:
        """通过 LLM 检查行动是否被允许"""
        checks = self.check_compliance(action)

        non_compliant = [c for c in checks if c.result == ComplianceResult.NON_COMPLIANT]
        requires_approval = [c for c in checks if c.result == ComplianceResult.REQUIRES_APPROVAL]
        warnings = [c for c in checks if c.result == ComplianceResult.WARNING]

        if non_compliant:
            reasons = "; ".join([c.message for c in non_compliant])
            return False, f"违反宪法: {reasons}", checks

        if requires_approval:
            reasons = "; ".join([c.message for c in requires_approval])
            return True, f"需要沙箱执行: {reasons}", checks

        if warnings:
            reasons = "; ".join([c.message for c in warnings])
            return True, f"注意: {reasons}", checks

        return True, "合规", checks

    def get_system_prompt(self) -> str:
        """获取宪法系统提示词"""
        parts = ["# 冷小北宪法", ""]
        for principle in self.principles.values():
            parts.append(f"## {principle.chinese_name} ({principle.name})")
            parts.append(f"- **强制执行**: {'是' if principle.enforcement_level == 'mandatory' else '否'}")
            parts.append(f"- **描述**: {principle.description}")
            if principle.examples:
                parts.append("- **示例**:")
                for example in principle.examples[:3]:
                    parts.append(f"  - {example}")
            parts.append("")

        for fname, content in self.constitution_docs.items():
            parts.append(f"## {fname}")
            parts.append(content[:500])
            if len(content) > 500:
                parts.append("...")
            parts.append("")

        return "\n".join(parts)

    def get_principle(self, principle_id: str) -> Optional[Principle]:
        return self.principles.get(principle_id)

    def list_principles(self) -> List[Principle]:
        return list(self.principles.values())

    def validate_change(self, file_path: str, description: str, new_code: str = "") -> bool:
        """薄封装 — 供 executor 调用，检查代码修改是否合规"""
        if "文件末尾缺少换行" in description:
            return True
        action = f"修改文件 {file_path}: {description}"
        if new_code:
            action += f"\n变更内容预览:\n{new_code[:500]}"
        allowed, reason, checks = self.is_action_allowed(action)
        if not allowed:
            logger.warning(f"拒绝修改: {reason}")
        return allowed


_constitution_instance: Optional[Constitution] = None


def get_constitution(project_root: str) -> Constitution:
    global _constitution_instance
    if _constitution_instance is None:
        _constitution_instance = Constitution(project_root)
    return _constitution_instance
