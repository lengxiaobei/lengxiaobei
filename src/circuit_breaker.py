"""
自适应熔断保护 — 本地规则引擎
=============================================

使用本地规则引擎替代 LLM 调用做熔断决策，避免在系统故障时增加额外负载。

设计原则：
- 熔断阈值由本地规则引擎根据历史模式快速判断
- 恢复决策基于时间窗口 + 资源状态，不依赖外部调用
- 错误分类使用关键词匹配，零延迟
"""

import os
import time
import logging
import psutil
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Callable, Any

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    """自适应熔断配置"""
    max_consecutive_failures: int = 7
    max_cpu_percent: float = 85.0
    max_memory_percent: float = 85.0
    recovery_time: int = 180
    check_interval: int = 5
    # 临时性错误可容忍更多次
    temp_error_threshold: int = 12
    # 核心错误应尽早熔断
    critical_error_threshold: int = 3


@dataclass
class CircuitBreakerState:
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    is_tripped: bool = False
    trip_time: Optional[float] = None
    recovery_start_time: Optional[float] = None


# 错误分类关键词
_TEMPORARY_ERRORS = [
    "503", "429", "rate limit", "rate_limit", "throttl",
    "timeout", "timed out", "connection reset", "connection refused",
    "temporary", "retry", "overload", "capacity",
]

_CRITICAL_ERRORS = [
    "integrity check failed", "corruption", "data loss",
    "authentication failed", "unauthorized", "permission denied",
    "fatal", "panic", "segfault",
]


class CircuitBreaker:
    """本地规则引擎驱动的自适应熔断保护"""

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState()
        self.state_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'state', 'circuit_breaker_state.json'
        )
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self._load_state()
        self.alert_callbacks: List[Callable] = []
        self._history: List[Dict] = []

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 只取 CircuitBreakerState 已知字段，忽略多余字段
                    known_fields = {f.name for f in CircuitBreakerState.__dataclass_fields__.values()}
                    filtered = {k: v for k, v in data.items() if k in known_fields}
                    self.state = CircuitBreakerState(**filtered)
            except Exception:
                pass

    def _save_state(self):
        try:
            tmp_path = self.state_file + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.state.__dict__, f, indent=2)
            os.replace(tmp_path, self.state_file)
        except Exception:
            pass

    def check_health(self) -> bool:
        """检查系统健康状态"""
        if self.state.is_tripped:
            if self._should_recover():
                self._attempt_recovery()
                return True
            return False

        resource_ok, resource_details = self._check_resources()
        if not resource_ok:
            self._trip(f"资源使用超限: {resource_details}")
            return False

        return True

    def record_success(self):
        self._history.append({"event": "success", "time": time.time()})
        if len(self._history) > 100:
            self._history = self._history[-50:]
        self.state.consecutive_failures = 0
        self.state.last_success_time = time.time()
        self.state.last_failure_time = None
        if self.state.is_tripped:
            self._reset()
        self._save_state()

    def record_failure(self, error: str = ""):
        self._history.append({"event": "failure", "error": error[:200], "time": time.time()})
        if len(self._history) > 100:
            self._history = self._history[-50:]
        self.state.consecutive_failures += 1
        self.state.last_failure_time = time.time()

        should_trip = self._should_trip(error)
        if should_trip:
            self._trip(f"连续失败 {self.state.consecutive_failures} 次: {error[:100]}")
        self._save_state()

    def _classify_error(self, error: str) -> str:
        """基于关键词分类错误类型"""
        error_lower = error.lower()
        for keyword in _CRITICAL_ERRORS:
            if keyword in error_lower:
                return "critical"
        for keyword in _TEMPORARY_ERRORS:
            if keyword in error_lower:
                return "temporary"
        return "normal"

    def _should_trip(self, error: str) -> bool:
        """本地规则引擎判断是否应触发熔断"""
        error_type = self._classify_error(error)

        if error_type == "critical":
            threshold = self.config.critical_error_threshold
        elif error_type == "temporary":
            threshold = self.config.temp_error_threshold
        else:
            threshold = self.config.max_consecutive_failures

        # 检查近期失败模式：如果同类错误密集出现，降低阈值
        if len(self._history) >= 3:
            recent_errors = [
                h for h in self._history[-5:]
                if h.get("event") == "failure" and h.get("error", "").lower() in error.lower()
            ]
            if len(recent_errors) >= 3:
                threshold = max(threshold // 2, 1)

        return self.state.consecutive_failures >= threshold

    def _check_resources(self) -> tuple:
        """检查资源使用"""
        try:
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
        except Exception:
            return True, "资源检查异常，默认通过"

        # 硬性阈值：必须熔断
        hard_fail = cpu > 95 or mem.percent > 95 or disk.percent > 98
        if hard_fail:
            return False, f"CPU={cpu:.0f}% MEM={mem.percent:.0f}% DISK={disk.percent:.0f}%"

        # 软性阈值：结合失败次数判断
        soft_warn = cpu > self.config.max_cpu_percent or mem.percent > self.config.max_memory_percent
        if soft_warn:
            # 资源高 + 有失败记录 → 熔断
            if self.state.consecutive_failures >= 2:
                return False, f"CPU={cpu:.0f}% MEM={mem.percent:.0f}% + 连续失败"
            # 资源高但无失败 → 仅警告，不熔断
            logger.warning(f"资源使用偏高: CPU={cpu:.0f}% MEM={mem.percent:.0f}%")

        return True, "ok"

    def _should_recover(self) -> bool:
        """基于时间窗口 + 资源状态判断是否恢复"""
        if not self.state.trip_time:
            return False

        elapsed = time.time() - self.state.trip_time
        min_recovery = self.config.recovery_time

        if elapsed < min_recovery:
            return False

        # 检查资源是否恢复正常
        try:
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory().percent
        except Exception:
            return True

        # 资源已降到安全线以下 → 可恢复
        cpu_safe = cpu < self.config.max_cpu_percent * 0.8
        mem_safe = mem < self.config.max_memory_percent * 0.8

        return cpu_safe and mem_safe

    def _attempt_recovery(self):
        logger.info("[CircuitBreaker] 尝试从熔断状态恢复")
        self._reset()

    def _trip(self, reason: str):
        logger.warning(f"[CircuitBreaker] 熔断触发: {reason}")
        self.state.is_tripped = True
        self.state.trip_time = time.time()
        self._save_state()
        self._trigger_alert(f"熔断触发: {reason}")

    def _reset(self):
        logger.info("[CircuitBreaker] 熔断状态重置")
        self.state.is_tripped = False
        self.state.trip_time = None
        self.state.consecutive_failures = 0
        self._save_state()
        self._trigger_alert("熔断状态已重置")

    def _trigger_alert(self, message: str):
        for cb in self.alert_callbacks:
            try:
                cb(message)
            except Exception:
                pass

    def add_alert_callback(self, callback: Callable):
        self.alert_callbacks.append(callback)

    def get_state(self) -> CircuitBreakerState:
        return self.state

    def get_health_status(self) -> Dict[str, Any]:
        try:
            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            mem_pct = mem.percent
        except Exception:
            cpu = 0
            mem_pct = 0

        return {
            "is_healthy": not self.state.is_tripped,
            "is_tripped": self.state.is_tripped,
            "consecutive_failures": self.state.consecutive_failures,
            "max_consecutive_failures": self.config.max_consecutive_failures,
            "cpu_usage": cpu,
            "max_cpu_percent": self.config.max_cpu_percent,
            "memory_usage": mem_pct,
            "max_memory_percent": self.config.max_memory_percent,
            "last_failure_time": self.state.last_failure_time,
            "last_success_time": self.state.last_success_time,
            "trip_time": self.state.trip_time,
            "recovery_time": self.config.recovery_time
        }


circuit_breaker = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    return circuit_breaker


def check_health() -> bool:
    return circuit_breaker.check_health()


def record_success():
    circuit_breaker.record_success()


def record_failure(error: str = ""):
    circuit_breaker.record_failure(error)


def get_health_status() -> Dict[str, Any]:
    return circuit_breaker.get_health_status()
