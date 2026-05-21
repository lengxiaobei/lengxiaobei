"""
任务预算控制系统 - 照搬 Claude Code 设计
==========================================
核心特性：
- 预算管理（token 和 USD）
- 预算追踪和监控
- 预算警报和限制
- 资源使用分析

参考 Claude Code 的任务预算控制实现
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from functools import cached_property

from .query_engine import Usage


# ============================================================================
# 类型定义
# ============================================================================

@dataclass
class BudgetConfig:
    """预算配置"""
    max_tokens: Optional[int] = None  # 最大 token 数
    max_cost_usd: Optional[float] = None  # 最大成本（美元）
    max_time_seconds: Optional[int] = None  # 最大执行时间（秒）
    token_cost_per_1k: float = 0.0001  # 每 1000 token 的成本
    alert_threshold: float = 0.8  # 警报阈值（80%）


@dataclass
class BudgetStatus:
    """预算状态"""
    current_tokens: int = 0
    current_cost_usd: float = 0.0
    current_time_seconds: float = 0.0
    start_time: float = field(default_factory=time.time)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    is_exceeded: bool = False
    exceeded_reason: Optional[str] = None


@dataclass
class BudgetTracker:
    """预算追踪器"""
    config: BudgetConfig
    status: BudgetStatus = field(default_factory=BudgetStatus)
    on_alert: Optional[Callable] = None
    on_exceeded: Optional[Callable] = None
    
    def update_usage(self, usage: Usage):
        """更新用量"""
        # 更新 token 用量
        self.status.current_tokens += usage.total_tokens
        
        # 更新成本
        self.status.current_cost_usd += usage.cost_usd
        
        # 更新时间
        self.status.current_time_seconds = time.time() - self.status.start_time
        
        # 检查预算
        self._check_budget()
    
    def _check_budget(self):
        """检查预算"""
        # 检查 token 限制
        if self.config.max_tokens and self.status.current_tokens >= self.config.max_tokens:
            self.status.is_exceeded = True
            self.status.exceeded_reason = f"Token limit exceeded: {self.status.current_tokens}/{self.config.max_tokens}"
            if self.on_exceeded:
                self.on_exceeded(self.status.exceeded_reason)
            return
        
        # 检查成本限制
        if self.config.max_cost_usd and self.status.current_cost_usd >= self.config.max_cost_usd:
            self.status.is_exceeded = True
            self.status.exceeded_reason = f"Cost limit exceeded: ${self.status.current_cost_usd:.4f}/${self.config.max_cost_usd:.4f}"
            if self.on_exceeded:
                self.on_exceeded(self.status.exceeded_reason)
            return
        
        # 检查时间限制
        if self.config.max_time_seconds and self.status.current_time_seconds >= self.config.max_time_seconds:
            self.status.is_exceeded = True
            self.status.exceeded_reason = f"Time limit exceeded: {self.status.current_time_seconds:.2f}s/{self.config.max_time_seconds}s"
            if self.on_exceeded:
                self.on_exceeded(self.status.exceeded_reason)
            return
        
        # 检查警报阈值
        self._check_alerts()
    
    def _check_alerts(self):
        """检查警报"""
        # Token 警报
        if self.config.max_tokens:
            token_ratio = self.status.current_tokens / self.config.max_tokens
            if token_ratio >= self.config.alert_threshold and token_ratio < 1.0:
                alert = {
                    "type": "token",
                    "message": f"Token usage approaching limit: {token_ratio:.1%}",
                    "ratio": token_ratio,
                    "timestamp": time.time()
                }
                self._add_alert(alert)
        
        # 成本警报
        if self.config.max_cost_usd:
            cost_ratio = self.status.current_cost_usd / self.config.max_cost_usd
            if cost_ratio >= self.config.alert_threshold and cost_ratio < 1.0:
                alert = {
                    "type": "cost",
                    "message": f"Cost approaching limit: {cost_ratio:.1%}",
                    "ratio": cost_ratio,
                    "timestamp": time.time()
                }
                self._add_alert(alert)
        
        # 时间警报
        if self.config.max_time_seconds:
            time_ratio = self.status.current_time_seconds / self.config.max_time_seconds
            if time_ratio >= self.config.alert_threshold and time_ratio < 1.0:
                alert = {
                    "type": "time",
                    "message": f"Time approaching limit: {time_ratio:.1%}",
                    "ratio": time_ratio,
                    "timestamp": time.time()
                }
                self._add_alert(alert)
    
    def _add_alert(self, alert: Dict[str, Any]):
        """添加警报"""
        # 避免重复警报
        if not any(a.get('type') == alert['type'] for a in self.status.alerts):
            self.status.alerts.append(alert)
            if self.on_alert:
                self.on_alert(alert)
    
    def get_status(self) -> BudgetStatus:
        """获取预算状态"""
        return self.status
    
    def get_summary(self) -> Dict[str, Any]:
        """获取预算摘要"""
        summary = {
            "current_tokens": self.status.current_tokens,
            "current_cost_usd": self.status.current_cost_usd,
            "current_time_seconds": self.status.current_time_seconds,
            "is_exceeded": self.status.is_exceeded,
            "exceeded_reason": self.status.exceeded_reason,
            "alerts": self.status.alerts
        }
        
        # 添加限制信息
        if self.config.max_tokens:
            summary["max_tokens"] = self.config.max_tokens
            summary["token_ratio"] = self.status.current_tokens / self.config.max_tokens
        
        if self.config.max_cost_usd:
            summary["max_cost_usd"] = self.config.max_cost_usd
            summary["cost_ratio"] = self.status.current_cost_usd / self.config.max_cost_usd
        
        if self.config.max_time_seconds:
            summary["max_time_seconds"] = self.config.max_time_seconds
            summary["time_ratio"] = self.status.current_time_seconds / self.config.max_time_seconds
        
        return summary
    
    def reset(self):
        """重置预算追踪"""
        self.status = BudgetStatus()
    
    def is_within_budget(self) -> bool:
        """检查是否在预算内"""
        return not self.status.is_exceeded


@dataclass
class TaskBudget:
    """任务预算"""
    total: int  # 总预算（token）
    used: int = 0
    
    @property
    def remaining(self) -> int:
        """剩余预算（动态计算）"""
        return self.total - self.used
    
    def use(self, amount: int):
        """使用预算"""
        self.used += amount
        return self.remaining
    
    def is_used_up(self) -> bool:
        """检查是否用尽"""
        return self.remaining <= 0
    
    def get_percentage_used(self) -> float:
        """获取使用百分比"""
        return (self.used / self.total) * 100 if self.total > 0 else 0


# ============================================================================
# 核心功能
# ============================================================================

def create_budget_tracker(
    max_tokens: Optional[int] = None,
    max_cost_usd: Optional[float] = None,
    max_time_seconds: Optional[int] = None,
    token_cost_per_1k: float = 0.0001,
    alert_threshold: float = 0.8,
    on_alert: Optional[Callable] = None,
    on_exceeded: Optional[Callable] = None
) -> BudgetTracker:
    """
    创建预算追踪器
    
    Args:
        max_tokens: 最大 token 数
        max_cost_usd: 最大成本（美元）
        max_time_seconds: 最大执行时间（秒）
        token_cost_per_1k: 每 1000 token 的成本
        alert_threshold: 警报阈值
        on_alert: 警报回调函数
        on_exceeded: 预算超出回调函数
    
    Returns:
        预算追踪器实例
    """
    config = BudgetConfig(
        max_tokens=max_tokens,
        max_cost_usd=max_cost_usd,
        max_time_seconds=max_time_seconds,
        token_cost_per_1k=token_cost_per_1k,
        alert_threshold=alert_threshold
    )
    
    return BudgetTracker(
        config=config,
        on_alert=on_alert,
        on_exceeded=on_exceeded
    )


def create_task_budget(total: int) -> TaskBudget:
    """
    创建任务预算
    
    Args:
        total: 总预算（token）
    
    Returns:
        任务预算实例
    """
    return TaskBudget(total=total)


def calculate_cost(tokens: int, cost_per_1k: float = 0.0001) -> float:
    """
    计算成本
    
    Args:
        tokens: token 数
        cost_per_1k: 每 1000 token 的成本
    
    Returns:
        成本（美元）
    """
    return (tokens / 1000) * cost_per_1k


def format_budget_summary(summary: Dict[str, Any]) -> str:
    """
    格式化预算摘要
    
    Args:
        summary: 预算摘要
    
    Returns:
        格式化的字符串
    """
    lines = []
    lines.append("=== 预算摘要 ===")
    lines.append(f"当前 Token: {summary['current_tokens']}")
    lines.append(f"当前成本: ${summary['current_cost_usd']:.4f}")
    lines.append(f"当前时间: {summary['current_time_seconds']:.2f}s")
    
    if 'max_tokens' in summary:
        lines.append(f"Token 限制: {summary['max_tokens']} ({summary['token_ratio']:.1%})")
    
    if 'max_cost_usd' in summary:
        lines.append(f"成本限制: ${summary['max_cost_usd']:.4f} ({summary['cost_ratio']:.1%})")
    
    if 'max_time_seconds' in summary:
        lines.append(f"时间限制: {summary['max_time_seconds']}s ({summary['time_ratio']:.1%})")
    
    if summary['is_exceeded']:
        lines.append(f"⚠️  预算超出: {summary['exceeded_reason']}")
    else:
        lines.append("✅  在预算范围内")
    
    if summary['alerts']:
        lines.append("\n📋  警报:")
        for alert in summary['alerts']:
            lines.append(f"  - {alert['message']}")
    
    return "\n".join(lines)


# ============================================================================
# 装饰器
# ============================================================================

def with_budget(
    max_tokens: Optional[int] = None,
    max_cost_usd: Optional[float] = None,
    max_time_seconds: Optional[int] = None
):
    """
    预算控制装饰器
    
    Args:
        max_tokens: 最大 token 数
        max_cost_usd: 最大成本（美元）
        max_time_seconds: 最大执行时间（秒）
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 创建预算追踪器
            tracker = create_budget_tracker(
                max_tokens=max_tokens,
                max_cost_usd=max_cost_usd,
                max_time_seconds=max_time_seconds
            )
            
            # 添加预算追踪器到 kwargs
            kwargs['budget_tracker'] = tracker
            
            try:
                result = await func(*args, **kwargs)
                
                # 打印预算摘要
                summary = tracker.get_summary()
                print(format_budget_summary(summary))
                
                return result
            except Exception as e:
                # 打印预算摘要
                summary = tracker.get_summary()
                print(format_budget_summary(summary))
                raise
        
        return wrapper
    
    return decorator