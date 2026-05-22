"""Small local circuit breaker used by autonomous evolution.

The hard boundary module owns policy decisions. This breaker only tracks
runtime failures so repeated broken evolutions can stop themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List


@dataclass
class CircuitBreakerConfig:
    max_consecutive_failures: int = 3


@dataclass
class CircuitBreakerState:
    consecutive_failures: int = 0
    status: str = "closed"
    failures: List[str] = field(default_factory=list)


class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig | str | None = None, name: str = ""):
        if isinstance(config, CircuitBreakerConfig):
            self.config = config
            self.name = name
        else:
            self.config = CircuitBreakerConfig()
            self.name = str(config or name)
        self.state = CircuitBreakerState()
        self.alert_callbacks: List[Callable[["CircuitBreaker"], None]] = []

    def check_health(self):
        return self.state.status != "open"

    def record_success(self):
        self.state.status = "closed"
        self.state.consecutive_failures = 0
        self.state.failures.clear()

    def record_failure(self, reason=""):
        self.state.failures.append(str(reason))
        self.state.consecutive_failures += 1
        if self.state.consecutive_failures >= self.config.max_consecutive_failures:
            self.state.status = "open"
            self._notify_alerts()

    def add_alert_callback(self, callback):
        self.alert_callbacks.append(callback)

    def _notify_alerts(self):
        for callback in list(self.alert_callbacks):
            try:
                callback(self)
            except Exception:
                pass


_default_breaker = CircuitBreaker("default")


def check_health():
    return _default_breaker.check_health()


def record_success():
    _default_breaker.record_success()


def record_failure(reason=""):
    _default_breaker.record_failure(reason)
