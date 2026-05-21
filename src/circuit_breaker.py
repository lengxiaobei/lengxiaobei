"""
LLM 驱动熔断保护 — 自主 AI Agent 自适应保护
=============================================

核心理念：不再使用硬编码的阈值（80% CPU、80% RAM、5次连续失败），
而是通过 LLM 提示词根据历史上下文动态评估系统健康状况。

设计原则：
- 熔断阈值由 LLM 根据历史模式推理
- 恢复决策由 LLM 评估，不是固定300秒
- 系统状态判断由 LLM 综合分析
"""

import os
import time
import psutil
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Callable, Any
from .llm import chat


@dataclass
class CircuitBreakerConfig:
    """自适应熔断配置"""
    max_consecutive_failures: int = 7
    max_cpu_percent: float = 85.0
    max_memory_percent: float = 85.0
    recovery_time: int = 180
    check_interval: int = 5


@dataclass
class CircuitBreakerState:
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    is_tripped: bool = False
    trip_time: Optional[float] = None
    recovery_start_time: Optional[float] = None


class CircuitBreaker:
    """LLM 驱动的自适应熔断保护"""

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
                    self.state = CircuitBreakerState(**data)
            except Exception:
                pass

    def _save_state(self):
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state.__dict__, f, indent=2)
        except Exception:
            pass

    def check_health(self) -> bool:
        """检查系统健康状态"""
        if self.state.is_tripped:
            if self._should_recover():
                self._attempt_recovery()
                return True
            return False

        resource_ok, resource_details = self._check_resources_with_context()
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

        should_trip = self._llm_should_trip(error)
        if should_trip or self.state.consecutive_failures >= self.config.max_consecutive_failures:
            self._trip(f"连续失败 {self.state.consecutive_failures} 次: {error[:100]}")
        self._save_state()

    def _check_resources_with_context(self) -> tuple:
        """检查资源使用并结合上下文评估"""
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
        except Exception:
            return True, "资源检查异常，默认通过"

        # 基础阈值检查
        hard_fail = cpu > 95 or mem.percent > 95 or disk.percent > 98
        if hard_fail:
            return False, f"CPU={cpu:.0f}% MEM={mem.percent:.0f}% DISK={disk.percent:.0f}%"

        soft_warn = cpu > self.config.max_cpu_percent or mem.percent > self.config.max_memory_percent
        if soft_warn:
            should_fail = self._llm_evaluate_resource(cpu, mem.percent, disk.percent)
            return not should_fail, f"CPU={cpu:.0f}% MEM={mem.percent:.0f}% DISK={disk.percent:.0f}%"
        return True, "ok"

    def _llm_should_trip(self, error: str) -> bool:
        """通过 LLM 评估连续失败是否应触发熔断"""
        recent = self._history[-5:] if self._history else []
        history_text = json.dumps(recent, ensure_ascii=False)

        prompt = f"""你是系统健康监控AI。请评估当前是否应触发熔断保护。

连续失败次数: {self.state.consecutive_failures}
最大允许次数: {self.config.max_consecutive_failures}
最新错误: {error[:150]}
最近事件: {history_text}

请判断是否需要立即熔断。考虑:
- 如果错误类型是"模型限流(503)"等临时性错误，可以容忍更多次
- 如果错误是"Integrity check failed"等核心错误，应尽早熔断
- 如果错误模式有规律（如都是同类错误），可适当放宽

返回JSON:
{{"should_trip": false, "reasoning": "判断理由"}}
只返回JSON。"""

        try:
            response = chat(prompt, system="你是系统健康监控AI。只返回JSON。", temperature=0.1)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return data.get("should_trip", self.state.consecutive_failures >= self.config.max_consecutive_failures)
        except Exception:
            pass

        return self.state.consecutive_failures >= self.config.max_consecutive_failures

    def _llm_evaluate_resource(self, cpu: float, mem: float, disk: float) -> bool:
        """通过 LLM 评估资源是否严重到需要熔断"""
        prompt = f"""评估当前系统资源状态是否严重到需要熔断保护。

CPU: {cpu:.0f}%
内存: {mem:.0f}%
磁盘: {disk:.0f}%
连续失败: {self.state.consecutive_failures}

返回JSON:
{{"should_trip": false, "reasoning": "评估理由"}}
只返回JSON。"""

        try:
            response = chat(prompt, system="你是系统资源评估AI。只返回JSON。", temperature=0.1)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return data.get("should_trip", cpu > 90 or mem > 95)
        except Exception:
            pass

        return cpu > 90 or mem > 95

    def _should_recover(self) -> bool:
        """通过 LLM 评估是否应该从熔断状态恢复"""
        if not self.state.trip_time:
            return False

        elapsed = time.time() - self.state.trip_time
        min_recovery = self.config.recovery_time

        if elapsed < min_recovery:
            return False

        # 超过基础恢复时间后，使用 LLM 评估
        try:
            cpu = psutil.cpu_percent(interval=0.3)
            mem = psutil.virtual_memory().percent
        except Exception:
            return True

        prompt = f"""评估是否可以从熔断状态恢复。

当前资源: CPU={cpu:.0f}% 内存={mem:.0f}%
熔断时间: 已持续 {elapsed:.0f} 秒
基础恢复时间: {min_recovery} 秒

返回JSON:
{{"should_recover": true, "reasoning": "评估理由"}}
只返回JSON。"""

        try:
            response = chat(prompt, system="你是系统恢复评估AI。只返回JSON。", temperature=0.1)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return data.get("should_recover", True)
        except Exception:
            pass

        return True

    def _attempt_recovery(self):
        print("[CircuitBreaker] 尝试从熔断状态恢复")
        self._reset()

    def _trip(self, reason: str):
        print(f"[CircuitBreaker] 熔断触发: {reason}")
        self.state.is_tripped = True
        self.state.trip_time = time.time()
        self._save_state()
        self._trigger_alert(f"熔断触发: {reason}")

    def _reset(self):
        print("[CircuitBreaker] 熔断状态重置")
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
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            mem_pct = mem.percent
        except Exception:
            cpu = 0
            mem_pct = 0

        return {
            "is_healthy": self.check_health(),
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