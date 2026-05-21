"""
⚠️  LEGACY — 此模块已被 src/hard_boundary.py 替代。

旧设计：多级风险分类 + LLM 驱动的熔断阈值。
新设计：HardBoundary — 只守三条硬边界。

迁移至: src/hard_boundary.py
"""

class CircuitBreaker:
    def __init__(self, name=""): self.state = "closed"
def check_health(): return True
def record_success(): pass
def record_failure(reason=""): pass
