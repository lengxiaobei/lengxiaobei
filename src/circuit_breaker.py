"""
⚠️  LEGACY — 此模块已被 src/hard_boundary.py 替代。

旧设计：多级风险分类 + LLM 驱动的熔断阈值。
新设计：HardBoundary — 只守三条硬边界。

迁移至: src/hard_boundary.py
"""

class CircuitBreaker:
    def __init__(self, name=""):
        self.name = name
        self.state = "closed"
        self.failures = []

    def check_health(self):
        return self.state != "open"

    def record_success(self):
        self.state = "closed"
        self.failures.clear()

    def record_failure(self, reason=""):
        self.failures.append(str(reason))
        if len(self.failures) >= 3:
            self.state = "open"


_default_breaker = CircuitBreaker("default")


def check_health():
    return _default_breaker.check_health()


def record_success():
    _default_breaker.record_success()


def record_failure(reason=""):
    _default_breaker.record_failure(reason)
