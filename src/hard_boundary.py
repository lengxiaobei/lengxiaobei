"""
HardBoundary — 硬边界检查
==========================
只守三条线，不做细碎风险分级。云模型负责判断好坏，本地只做底线拦截。

三类:
- ALLOWED          — 云模型判断 + 直接执行
- NEEDS_CONFIRMATION — 涉及身份/资金/不可逆影响，需宿主确认
- FORBIDDEN        — 安全底线，云模型也不能越过
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class BoundaryResult(Enum):
    ALLOWED = "allowed"                    # 放行，直接执行
    NEEDS_CONFIRMATION = "needs_confirmation"  # 需宿主确认
    FORBIDDEN = "forbidden"               # 绝对禁止


@dataclass
class BoundaryCheck:
    result: BoundaryResult
    reason: str = ""
    matched_rule: str = ""


# ---------------------------------------------------------------------------
# 三条硬边界
# ---------------------------------------------------------------------------

# 需要确认 — 涉及宿主身份、资金、不可逆影响
NEEDS_CONFIRMATION_PATTERNS = [
    # 身份/账户
    "use_account", "impersonate", "login_as", "use_identity",
    # 资金
    "spend_money", "pay", "purchase", "buy", "charge", "bill",
    "use_host_funds", "use_credit_card", "bank_transfer",
    # 发布到公网
    "publish_to_web", "deploy_to_production", "push_to_public",
    "git_push", "push_to_remote", "publish_package",
    # 不可逆删除
    "delete_large_files", "rm -rf", "drop_table", "truncate",
    # 外部依赖
    "install_untrusted", "pip_install_unverified",
    # 云资源
    "provision_cloud", "create_instance", "allocate_ip",
]

# 绝对禁止 — 安全底线
FORBIDDEN_PATTERNS = [
    # 修改安全底线
    "modify_security_bounds", "change_hard_boundary", "disable_safety",
    # 隐私泄露
    "leak_privacy", "expose_secrets", "send_private_data",
    # 违法/攻击
    "illegal_activity", "cyber_attack", "ddos", "exploit", "malware",
    "ransomware", "phishing",
    # 删除核心记忆
    "delete_core_memory", "wipe_memory", "purge_memories",
    # 绕过宿主控制
    "bypass_host_control", "override_host_decision",
    "disable_host_override",
]


class HardBoundary:
    """硬边界 — 管道中的一道门，不替代云模型的判断力"""

    def check(self, action: str, context: dict = None) -> BoundaryCheck:
        """
        检查行动是否触碰硬边界。

        Args:
            action: 行动描述（自然语言，云模型产出）
            context: 附加上下文（文件路径、涉及金额等）

        Returns:
            BoundaryCheck with result and reason
        """
        action_lower = action.lower()
        ctx_str = str(context or {}).lower()

        # 1. 先查绝对禁止
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in action_lower or pattern in ctx_str:
                return BoundaryCheck(
                    result=BoundaryResult.FORBIDDEN,
                    reason=f"触碰安全底线: {pattern}",
                    matched_rule=pattern,
                )

        # 2. 再查需确认
        for pattern in NEEDS_CONFIRMATION_PATTERNS:
            if pattern in action_lower or pattern in ctx_str:
                return BoundaryCheck(
                    result=BoundaryResult.NEEDS_CONFIRMATION,
                    reason=f"需宿主确认: {pattern}",
                    matched_rule=pattern,
                )

        # 3. 其余全部放行（云模型已判断过值得做）
        return BoundaryCheck(result=BoundaryResult.ALLOWED)

    def should_pause(self, action: str, context: dict = None) -> bool:
        """是否需要暂停等待宿主确认"""
        result = self.check(action, context)
        return result.result in (BoundaryResult.NEEDS_CONFIRMATION, BoundaryResult.FORBIDDEN)

    def is_allowed(self, action: str, context: dict = None) -> bool:
        """是否允许执行（ALLOWED 或 NEEDS_CONFIRMATION 经确认后）"""
        result = self.check(action, context)
        return result.result != BoundaryResult.FORBIDDEN


# 全局单例
_boundary = HardBoundary()


def check_boundary(action: str, context: dict = None) -> BoundaryCheck:
    """便捷函数：检查行动是否触碰硬边界"""
    return _boundary.check(action, context)