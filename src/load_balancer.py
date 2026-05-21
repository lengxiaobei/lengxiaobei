"""负载均衡器 — 单进程精简版（无实际负载均衡，直接执行）"""

from typing import Any, Callable


class _NoopLoadBalancer:
    def add_memory_instance(self, url: str, name: str, weight: int = 1):
        pass

    def remove_memory_instance(self, name: str):
        pass

    def execute_with_instance(self, func: Callable[[str], Any]) -> Any:
        return func("")


_noop = _NoopLoadBalancer()


def get_memory_load_balancer():
    return _noop


def add_memory_instance(url: str, name: str, weight: int = 1):
    pass


def remove_memory_instance(name: str):
    pass


def execute_with_memory_instance(func: Callable[[str], Any]) -> Any:
    return func("")