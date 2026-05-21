"""
高级权限控制系统 - 照搬 Claude Code 设计
==========================================
核心特性：
- 细粒度的权限控制
- 工具使用审计
- 权限拒绝记录
- 安全增强

参考 Claude Code 的 wrappedCanUseTool 函数实现
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple

from .query_engine import PermissionDenial


# ============================================================================
# 类型定义
# ============================================================================

@dataclass
class PermissionContext:
    """权限上下文"""
    tool_name: str
    tool_input: Dict[str, Any]
    tool_use_id: str
    assistant_message: Optional[str] = None
    force_decision: bool = False


@dataclass
class PermissionResult:
    """权限检查结果"""
    behavior: str  # "allow" | "deny" | "ask"
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionAudit:
    """权限审计记录"""
    tool_name: str
    tool_input: Dict[str, Any]
    tool_use_id: str
    result: str  # "allow" | "deny" | "ask"
    timestamp: float = field(default_factory=time.time)
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionManager:
    """权限管理器"""
    audit_log: List[PermissionAudit] = field(default_factory=list)
    permission_denials: List[PermissionDenial] = field(default_factory=list)
    always_allow_rules: Dict[str, List[str]] = field(default_factory=lambda: {"command": []})
    always_deny_rules: Dict[str, List[str]] = field(default_factory=dict)
    
    def record_audit(self, audit: PermissionAudit):
        """记录权限审计"""
        self.audit_log.append(audit)
        
        # 记录权限拒绝
        if audit.result == "deny":
            denial = PermissionDenial(
                tool_name=audit.tool_name,
                tool_use_id=audit.tool_use_id,
                tool_input=audit.tool_input,
                timestamp=audit.timestamp
            )
            self.permission_denials.append(denial)
    
    def add_always_allow_rule(self, tool_type: str, tool_name: str):
        """添加总是允许的规则"""
        if tool_type not in self.always_allow_rules:
            self.always_allow_rules[tool_type] = []
        if tool_name not in self.always_allow_rules[tool_type]:
            self.always_allow_rules[tool_type].append(tool_name)
    
    def add_always_deny_rule(self, tool_type: str, tool_name: str):
        """添加总是拒绝的规则"""
        if tool_type not in self.always_deny_rules:
            self.always_deny_rules[tool_type] = []
        if tool_name not in self.always_deny_rules[tool_type]:
            self.always_deny_rules[tool_type].append(tool_name)
    
    def get_audit_log(self) -> List[PermissionAudit]:
        """获取审计日志"""
        return self.audit_log
    
    def get_permission_denials(self) -> List[PermissionDenial]:
        """获取权限拒绝记录"""
        return self.permission_denials
    
    def clear_audit_log(self):
        """清空审计日志"""
        self.audit_log = []
    
    def clear_permission_denials(self):
        """清空权限拒绝记录"""
        self.permission_denials = []


# ============================================================================
# 核心功能
# ============================================================================

def create_wrapped_can_use_tool(
    original_can_use_tool: Callable,
    permission_manager: PermissionManager
) -> Callable:
    """
    创建包装后的权限检查函数
    
    参考 Claude Code 的 wrappedCanUseTool 函数
    
    Args:
        original_can_use_tool: 原始的权限检查函数
        permission_manager: 权限管理器
    
    Returns:
        包装后的权限检查函数
    """
    async def wrapped_can_use_tool(
        tool: Dict[str, Any],
        tool_input: Dict[str, Any],
        tool_use_context: Dict[str, Any],
        assistant_message: Optional[str] = None,
        tool_use_id: Optional[str] = None,
        force_decision: bool = False
    ) -> PermissionResult:
        """包装后的权限检查函数"""
        # 确保 tool_use_id 存在
        if not tool_use_id:
            tool_use_id = f"tool_{uuid.uuid4()}"
        
        # 检查总是允许的规则
        tool_name = tool.get('name', '')
        if 'command' in permission_manager.always_allow_rules:
            if tool_name in permission_manager.always_allow_rules['command']:
                audit = PermissionAudit(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_use_id=tool_use_id,
                    result="allow",
                    reason="Always allow rule",
                    metadata={"rule_type": "always_allow"}
                )
                permission_manager.record_audit(audit)
                return PermissionResult(behavior="allow", reason="Always allow rule")
        
        # 检查总是拒绝的规则
        if 'command' in permission_manager.always_deny_rules:
            if tool_name in permission_manager.always_deny_rules['command']:
                audit = PermissionAudit(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_use_id=tool_use_id,
                    result="deny",
                    reason="Always deny rule",
                    metadata={"rule_type": "always_deny"}
                )
                permission_manager.record_audit(audit)
                return PermissionResult(behavior="deny", reason="Always deny rule")
        
        # 调用原始的权限检查函数
        result = await original_can_use_tool(
            tool,
            tool_input,
            tool_use_context,
            assistant_message,
            tool_use_id,
            force_decision
        )
        
        # 记录审计
        audit = PermissionAudit(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
            result=result.behavior,
            reason=result.reason,
            metadata=result.metadata
        )
        permission_manager.record_audit(audit)
        
        return result
    
    return wrapped_can_use_tool


def create_default_can_use_tool() -> Callable:
    """
    创建默认的权限检查函数
    
    Returns:
        默认的权限检查函数
    """
    async def default_can_use_tool(
        tool: Dict[str, Any],
        tool_input: Dict[str, Any],
        tool_use_context: Dict[str, Any],
        assistant_message: Optional[str] = None,
        tool_use_id: Optional[str] = None,
        force_decision: bool = False
    ) -> PermissionResult:
        """默认的权限检查函数"""
        # 基础的权限检查逻辑
        # 实际项目中应该根据具体的权限规则进行检查
        tool_name = tool.get('name', '')
        
        # 示例：拒绝危险的系统命令
        dangerous_commands = ['rm', 'sudo', 'shutdown', 'reboot']
        if tool_name in dangerous_commands:
            return PermissionResult(
                behavior="deny",
                reason="Dangerous command not allowed",
                metadata={"risk_level": "high"}
            )
        
        # 示例：需要确认的命令
        require_confirmation = ['mkdir', 'cp', 'mv']
        if tool_name in require_confirmation and not force_decision:
            return PermissionResult(
                behavior="ask",
                reason="Command requires confirmation",
                metadata={"risk_level": "medium"}
            )
        
        # 默认允许
        return PermissionResult(
            behavior="allow",
            reason="Command allowed",
            metadata={"risk_level": "low"}
        )
    
    return default_can_use_tool


def create_permission_manager() -> PermissionManager:
    """
    创建权限管理器
    
    Returns:
        权限管理器实例
    """
    return PermissionManager()


# ============================================================================
# 便捷函数
# ============================================================================

def check_permission(
    tool: Dict[str, Any],
    tool_input: Dict[str, Any],
    permission_manager: PermissionManager,
    can_use_tool: Callable,
    **kwargs
) -> Tuple[bool, Optional[str]]:
    """
    检查权限的便捷函数
    
    Args:
        tool: 工具信息
        tool_input: 工具输入
        permission_manager: 权限管理器
        can_use_tool: 权限检查函数
        **kwargs: 其他参数
    
    Returns:
        (是否允许, 拒绝原因)
    """
    import asyncio
    
    result = asyncio.run(can_use_tool(tool, tool_input, {}, **kwargs))
    return result.behavior == "allow", result.reason if result.behavior != "allow" else None


def get_permission_summary(permission_manager: PermissionManager) -> Dict[str, Any]:
    """
    获取权限摘要
    
    Args:
        permission_manager: 权限管理器
    
    Returns:
        权限摘要
    """
    audit_log = permission_manager.get_audit_log()
    denials = permission_manager.get_permission_denials()
    
    # 统计信息
    total_checks = len(audit_log)
    allow_count = sum(1 for audit in audit_log if audit.result == "allow")
    deny_count = sum(1 for audit in audit_log if audit.result == "deny")
    ask_count = sum(1 for audit in audit_log if audit.result == "ask")
    
    # 工具使用统计
    tool_usage = {}
    for audit in audit_log:
        if audit.tool_name not in tool_usage:
            tool_usage[audit.tool_name] = {
                "total": 0,
                "allow": 0,
                "deny": 0,
                "ask": 0
            }
        tool_usage[audit.tool_name]["total"] += 1
        tool_usage[audit.tool_name][audit.result] += 1
    
    return {
        "total_checks": total_checks,
        "allow_count": allow_count,
        "deny_count": deny_count,
        "ask_count": ask_count,
        "denial_count": len(denials),
        "tool_usage": tool_usage,
        "recent_denials": denials[-5:]  # 最近5个拒绝记录
    }
