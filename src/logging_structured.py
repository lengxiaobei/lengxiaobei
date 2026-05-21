"""
结构化日志系统
==============
支持 JSON 格式日志 + trace_id 用于分布式追踪
"""
import os
import sys
import time
import json
import uuid
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from contextvars import ContextVar


# =============================================================================
# Trace ID Context
# =============================================================================

trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar('span_id', default=None)


def generate_trace_id() -> str:
    """生成新的 trace_id"""
    return str(uuid.uuid4())[:16]


def generate_span_id() -> str:
    """生成新的 span_id"""
    return str(uuid.uuid4())[:8]


def get_trace_id() -> str:
    """获取当前 trace_id，如果没有则生成"""
    tid = trace_id_var.get()
    if tid is None:
        tid = generate_trace_id()
        trace_id_var.set(tid)
    return tid


def get_span_id() -> str:
    """获取当前 span_id"""
    sid = span_id_var.get()
    if sid is None:
        sid = generate_span_id()
        span_id_var.set(sid)
    return sid


class TraceContext:
    """追踪上下文管理器"""

    def __init__(self, trace_id: str = None, span_id: str = None, parent_span_id: str = None):
        self.trace_id = trace_id or generate_trace_id()
        self.span_id = span_id or generate_span_id()
        self.parent_span_id = parent_span_id
        self._token = None

    def __enter__(self):
        self._token = trace_id_var.set(self.trace_id)
        span_id_var.set(self.span_id)
        return self

    def __exit__(self, *args):
        if self._token is not None:
            trace_id_var.reset(self._token)
        span_id_var.set(None)


# =============================================================================
# Log Levels
# =============================================================================

class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# =============================================================================
# Structured Log Record
# =============================================================================

class StructuredLogRecord(Dict[str, Any]):
    """结构化日志记录"""

    def __init__(
        self,
        level: str,
        message: str,
        trace_id: str = None,
        span_id: str = None,
        logger_name: str = "",
        timestamp: float = None,
        **kwargs
    ):
        super().__init__()
        self["timestamp"] = timestamp or time.time()
        self["level"] = level
        self["message"] = message
        self["trace_id"] = trace_id or get_trace_id()
        self["span_id"] = span_id or get_span_id()
        self["logger"] = logger_name
        self["thread"] = threading.current_thread().name
        self["process"] = os.getpid()

        # Merge extra fields
        for key, value in kwargs.items():
            if key not in ("level", "message", "timestamp", "trace_id", "span_id", "logger"):
                self[key] = value

    def to_json(self, human_readable: bool = False) -> str:
        """转换为 JSON 字符串"""
        if human_readable:
            return json.dumps(self, indent=2, ensure_ascii=False)
        return json.dumps(self, ensure_ascii=False)


# =============================================================================
# Structured Logger
# =============================================================================

class StructuredLogger:
    """结构化日志记录器"""

    def __init__(
        self,
        name: str,
        level: str = None,
        output_file: Path = None,
        json_format: bool = True,
        human_readable: bool = False
    ):
        self.name = name
        self.level = getattr(LogLevel, level or "INFO")
        self.output_file = output_file
        self.json_format = json_format
        self.human_readable = human_readable
        self._lock = threading.Lock()

        # Setup console handler
        self._console_handler = logging.StreamHandler(sys.stdout)
        self._console_handler.setFormatter(logging.Formatter("%(message)s"))

    def _write(self, record: StructuredLogRecord):
        """写入日志"""
        if self.output_file:
            with self._lock:
                with open(self.output_file, "a", encoding="utf-8") as f:
                    f.write(record.to_json(self.human_readable) + "\n")

        # Console output
        text = record["message"]
        if self.human_readable:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record["timestamp"]))
            text = f"[{record['level']}] {ts} [{record['trace_id']}] {text}"

        # Determine logging level
        level = record["level"]
        if level == "DEBUG":
            logging.debug(text)
        elif level == "INFO":
            logging.info(text)
        elif level == "WARNING":
            logging.warning(text)
        elif level == "ERROR":
            logging.error(text)
        elif level == "CRITICAL":
            logging.critical(text)

    def _log(self, level: str, message: str, **kwargs):
        """记录日志"""
        record = StructuredLogRecord(
            level=level,
            message=message,
            logger_name=self.name,
            **kwargs
        )
        self._write(record)

    def debug(self, message: str, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log(LogLevel.CRITICAL, message, **kwargs)

    def log_exception(self, message: str, exc: Exception, **kwargs):
        """记录异常"""
        kwargs["exception_type"] = type(exc).__name__
        kwargs["exception_message"] = str(exc)
        self.error(message, **kwargs)


# =============================================================================
# Logger Factory
# =============================================================================

_loggers: Dict[str, StructuredLogger] = {}
_loggers_lock = threading.Lock()


def get_logger(
    name: str,
    level: str = None,
    output_dir: Path = None,
    json_format: bool = True
) -> StructuredLogger:
    """获取或创建 logger 实例"""
    with _loggers_lock:
        if name not in _loggers:
            output_file = None
            if output_dir:
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{name}.log"

            _loggers[name] = StructuredLogger(
                name=name,
                level=level,
                output_file=output_file,
                json_format=json_format
            )

        return _loggers[name]


# =============================================================================
# Default Loggers
# =============================================================================

def get_agent_logger(output_dir: Path = None) -> StructuredLogger:
    """获取 Agent 主日志记录器"""
    return get_logger("lengxiaobei", output_dir=output_dir)


def get_evolution_logger(output_dir: Path = None) -> StructuredLogger:
    """获取 Evolution 日志记录器"""
    return get_logger("lengxiaobei.evolution", output_dir=output_dir)


def get_memory_logger(output_dir: Path = None) -> StructuredLogger:
    """获取 Memory 日志记录器"""
    return get_logger("lengxiaobei.memory", output_dir=output_dir)


def get_kairos_logger(output_dir: Path = None) -> StructuredLogger:
    """获取 KAIROS 日志记录器"""
    return get_logger("lengxiaobei.kairos", output_dir=output_dir)
