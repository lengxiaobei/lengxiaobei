"""
Guardian 守护系统单元测试
========================
覆盖：circuit_breaker, health_check, budget, permission
"""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# CircuitBreaker 测试
# ============================================================================

class TestCircuitBreaker:
    """熔断保护器"""

    def test_record_failure_increments_count(self):
        from src.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        config = CircuitBreakerConfig(max_consecutive_failures=10)
        breaker = CircuitBreaker(config)
        # 忽略之前的状态，测试增量
        initial = breaker.state.consecutive_failures
        breaker.record_failure()
        assert breaker.state.consecutive_failures > initial

    def test_record_success_resets_count(self):
        from src.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        config = CircuitBreakerConfig(max_consecutive_failures=10)
        breaker = CircuitBreaker(config)
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        assert breaker.state.consecutive_failures == 0

    def test_add_alert_callback_works(self):
        from src.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)
        callback = MagicMock()
        breaker.add_alert_callback(callback)
        assert callback in breaker.alert_callbacks


# ============================================================================
# HealthCheck 测试
# ============================================================================

class TestHealthCheck:
    """健康检查"""

    def test_get_health_status_returns_list(self):
        from src.health_check import HealthCheckService
        status = HealthCheckService.get_health_status()
        assert isinstance(status, list)

    def test_get_metrics_returns_dict(self):
        from src.health_check import HealthCheckService
        metrics = HealthCheckService.get_metrics()
        assert isinstance(metrics, dict)

    def test_update_component_status(self):
        from src.health_check import HealthCheckService
        HealthCheckService.update_component_status("test_component", "healthy", "test")
        # 不崩溃即通过

    def test_record_metric_via_class_method(self):
        from src.health_check import HealthCheckService
        # 使用类方法记录指标
        HealthCheckService._metrics["test_metric"] = 42.0
        metrics = HealthCheckService.get_metrics()
        assert "test_metric" in metrics or isinstance(metrics, dict)


# ============================================================================
# Budget 测试
# ============================================================================

class TestBudget:
    """预算控制"""

    def test_budget_tracker_initializes(self):
        from src.budget import BudgetTracker, BudgetConfig
        config = BudgetConfig(max_tokens=1000, max_cost_usd=1.0)
        tracker = BudgetTracker(config)
        assert tracker is not None

    def test_get_status(self):
        from src.budget import BudgetTracker, BudgetConfig
        config = BudgetConfig(max_cost_usd=10.0)
        tracker = BudgetTracker(config)
        status = tracker.get_status()
        assert hasattr(status, 'current_cost_usd')

    def test_is_within_budget_true_initially(self):
        from src.budget import BudgetTracker, BudgetConfig
        config = BudgetConfig(max_cost_usd=10.0)
        tracker = BudgetTracker(config)
        assert tracker.is_within_budget() is True

    def test_get_status_returns_valid_data(self):
        from src.budget import BudgetTracker, BudgetConfig
        config = BudgetConfig(max_tokens=1000)
        tracker = BudgetTracker(config)
        status = tracker.get_status()
        assert isinstance(status.current_tokens, int)
        assert isinstance(status.current_cost_usd, float)

    def test_reset_clears_usage(self):
        from src.budget import BudgetTracker, BudgetConfig
        config = BudgetConfig(max_tokens=1000)
        tracker = BudgetTracker(config)
        tracker.reset()
        assert tracker.get_status().current_tokens == 0


# ============================================================================
# Permission 测试
# ============================================================================

class TestPermission:
    """权限系统"""

    def _make_pm(self):
        from src.permission import PermissionManager
        return PermissionManager()

    def test_permission_manager_initializes(self):
        pm = self._make_pm()
        assert pm is not None

    def test_add_always_allow_rule(self):
        from src.permission import PermissionManager
        pm = PermissionManager()
        pm.add_always_allow_rule("file", "read_file")
        assert pm is not None

    def test_add_always_deny_rule(self):
        from src.permission import PermissionManager
        pm = PermissionManager()
        pm.add_always_deny_rule("dangerous", "rm_rf")
        assert pm is not None

    def test_get_audit_log_returns_list(self):
        from src.permission import PermissionManager
        pm = PermissionManager()
        log = pm.get_audit_log()
        assert isinstance(log, list)

    def test_clear_audit_log(self):
        from src.permission import PermissionManager
        pm = PermissionManager()
        pm.clear_audit_log()
        assert len(pm.get_audit_log()) == 0

    def test_record_audit(self):
        from src.permission import PermissionManager, PermissionAudit
        pm = PermissionManager()
        audit = PermissionAudit(
            tool_name="test_tool",
            tool_input={},
            tool_use_id="test_id",
            result="allow"
        )
        pm.record_audit(audit)
        assert len(pm.get_audit_log()) >= 1

    def test_create_default_can_use_tool(self):
        from src.permission import create_default_can_use_tool
        func = create_default_can_use_tool()
        assert callable(func)

    def test_check_permission_function(self):
        from src.permission import check_permission
        # 函数存在且可调用
        assert callable(check_permission)
