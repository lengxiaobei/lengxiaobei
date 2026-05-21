"""
Prometheus Metrics Module
========================
集成 Prometheus 指标收集，用于监控和告警
"""
import time
from typing import Dict, Any, Optional
from functools import wraps
import threading


# =============================================================================
# Metrics Registry
# =============================================================================

class MetricsRegistry:
    """指标注册表"""

    _instance: Optional['MetricsRegistry'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list] = {}
        self._labels: Dict[str, Dict[str, str]] = {}
        self._last_update = time.time()

    @classmethod
    def get_instance(cls) -> 'MetricsRegistry':
        if cls._instance is None:
            cls()
        return cls._instance


# =============================================================================
# Counter Metric
# =============================================================================

class Counter:
    """计数器指标"""

    def __init__(self, name: str, description: str = "", labels: Dict[str, str] = None):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value = 0.0
        self._lock = threading.Lock()

    def inc(self, value: float = 1.0):
        with self._lock:
            self._value += value

    def reset(self):
        with self._lock:
            self._value = 0.0

    def value(self) -> float:
        return self._value

    def to_prometheus(self) -> str:
        labels_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        if labels_str:
            return f'# TYPE {self.name} counter\n{self.name}{{{labels_str}}} {self._value}\n'
        return f'# TYPE {self.name} counter\n{self.name} {self._value}\n'


# =============================================================================
# Gauge Metric
# =============================================================================

class Gauge:
    """仪表指标"""

    def __init__(self, name: str, description: str = "", labels: Dict[str, str] = None):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, value: float):
        with self._lock:
            self._value = value

    def inc(self, value: float = 1.0):
        with self._lock:
            self._value += value

    def dec(self, value: float = 1.0):
        with self._lock:
            self._value -= value

    def value(self) -> float:
        return self._value

    def to_prometheus(self) -> str:
        labels_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        if labels_str:
            return f'# TYPE {self.name} gauge\n{self.name}{{{labels_str}}} {self._value}\n'
        return f'# TYPE {self.name} gauge\n{self.name} {self._value}\n'


# =============================================================================
# Histogram Metric
# =============================================================================

class Histogram:
    """直方图指标"""

    def __init__(self, name: str, description: str = "", labels: Dict[str, str] = None,
                 buckets: tuple = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self.buckets = buckets
        self._values = []
        self._lock = threading.Lock()

    def observe(self, value: float):
        with self._lock:
            self._values.append(value)

    def to_prometheus(self) -> str:
        labels_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        prefix = f'{self.name}_' if labels_str else f'{self.name}_'

        output = f'# TYPE {self.name} histogram\n'

        # Calculate bucket counts
        sorted_values = sorted(self._values)
        for bucket in self.buckets:
            count = sum(1 for v in sorted_values if v <= bucket)
            bucket_labels = f'{labels_str},le="{bucket}"' if labels_str else f'le="{bucket}"'
            output += f'{prefix}bucket{{{bucket_labels}}} {count}\n'

        # +Inf bucket
        inf_labels = f'{labels_str},le="+Inf"' if labels_str else 'le="+Inf"'
        output += f'{prefix}bucket{{{inf_labels}}} {len(sorted_values)}\n'

        # Sum and count
        output += f'{prefix}sum{{{labels_str}}} {sum(sorted_values)}\n' if labels_str else f'{prefix}sum {sum(sorted_values)}\n'
        output += f'{prefix}count{{{labels_str}}} {len(sorted_values)}\n' if labels_str else f'{prefix}count {len(sorted_values)}\n'

        return output


# =============================================================================
# Global Metrics
# =============================================================================

# 系统指标
system_cpu_usage = Gauge(
    "lengxiaobei_system_cpu_usage",
    "System CPU usage percentage",
    {"host": "lengxiaobei"}
)

system_memory_usage = Gauge(
    "lengxiaobei_system_memory_usage",
    "System memory usage percentage",
    {"host": "lengxiaobei"}
)

system_disk_usage = Gauge(
    "lengxiaobei_system_disk_usage",
    "System disk usage percentage",
    {"host": "lengxiaobei"}
)

# LLM 指标
llm_requests_total = Counter(
    "lengxiaobei_llm_requests_total",
    "Total LLM API requests",
    {"model": ""}
)

llm_request_duration_seconds = Histogram(
    "lengxiaobei_llm_request_duration_seconds",
    "LLM request duration in seconds",
    {"model": ""}
)

llm_tokens_total = Counter(
    "lengxiaobei_llm_tokens_total",
    "Total LLM tokens used",
    {"model": "", "type": "input|output"}
)

llm_cost_usd = Counter(
    "lengxiaobei_llm_cost_usd",
    "Total LLM cost in USD",
    {"model": ""}
)

llm_errors_total = Counter(
    "lengxiaobei_llm_errors_total",
    "Total LLM errors",
    {"model": "", "error_type": ""}
)

# 进化指标
evolution_proposals_total = Counter(
    "lengxiaobei_evolution_proposals_total",
    "Total evolution proposals",
    {"status": "pending|approved|rejected|applied"}
)

evolution_execution_duration_seconds = Histogram(
    "lengxiaobei_evolution_execution_duration_seconds",
    "Evolution execution duration"
)

evolution_files_modified = Counter(
    "lengxiaobei_evolution_files_modified_total",
    "Total files modified by evolution"
)

# 记忆指标
memory_entries_total = Gauge(
    "lengxiaobei_memory_entries_total",
    "Total memory entries",
    {"memory_type": "context|skill|fact|experience"}
)

memory_query_duration_seconds = Histogram(
    "lengxiaobei_memory_query_duration_seconds",
    "Memory query duration"
)

# 健康指标
health_score = Gauge(
    "lengxiaobei_health_score",
    "Overall system health score (0-100)"
)

circuit_breaker_state = Gauge(
    "lengxiaobei_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    {"name": ""}
)


# =============================================================================
# Decorator for tracking function metrics
# =============================================================================

def track_duration(metric: Histogram):
    """装饰器：跟踪函数执行时间"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                metric.observe(time.time() - start)
        return wrapper
    return decorator


# =============================================================================
# Metrics Export
# =============================================================================

def get_all_metrics() -> str:
    """导出所有指标为 Prometheus 格式"""
    metrics = [
        system_cpu_usage,
        system_memory_usage,
        system_disk_usage,
        llm_requests_total,
        llm_request_duration_seconds,
        llm_tokens_total,
        llm_cost_usd,
        llm_errors_total,
        evolution_proposals_total,
        evolution_execution_duration_seconds,
        evolution_files_modified,
        memory_entries_total,
        memory_query_duration_seconds,
        health_score,
        circuit_breaker_state,
    ]

    output = ""
    for metric in metrics:
        try:
            output += metric.to_prometheus()
        except Exception:
            pass

    return output


def get_metrics_json() -> Dict[str, Any]:
    """导出所有指标为 JSON 格式"""
    return {
        "timestamp": time.time(),
        "system": {
            "cpu_usage": system_cpu_usage.value(),
            "memory_usage": system_memory_usage.value(),
            "disk_usage": system_disk_usage.value(),
        },
        "llm": {
            "requests_total": llm_requests_total.value(),
            "tokens_total": llm_tokens_total.value(),
            "cost_usd": llm_cost_usd.value(),
            "errors_total": llm_errors_total.value(),
        },
        "evolution": {
            "proposals_total": evolution_proposals_total.value(),
            "files_modified": evolution_files_modified.value(),
        },
        "memory": {
            "entries_total": {k: v.value() for k, v in {}.items()},
        },
        "health": {
            "score": health_score.value(),
        }
    }
