"""
高级调试工具 - 照搬 Claude Code 设计
====================================
核心特性：
- 详细的调试信息收集
- 代码执行跟踪
- 性能分析
- 日志增强
- 调试命令和工具

参考 Claude Code 的高级调试工具实现
"""

import sys
import time
import traceback
import inspect
import functools
import cProfile
import pstats
import io
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Set


# ============================================================================
# 类型定义
# ============================================================================

@dataclass
class DebugInfo:
    """调试信息"""
    timestamp: float = field(default_factory=time.time)
    level: str = "INFO"
    message: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    stack: List[str] = field(default_factory=list)
    duration: Optional[float] = None


@dataclass
class TraceRecord:
    """跟踪记录"""
    function: str
    file: str
    line: int
    timestamp: float = field(default_factory=time.time)
    args: Dict[str, Any] = field(default_factory=dict)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None
    duration: Optional[float] = None


@dataclass
class DebugConfig:
    """调试配置"""
    enabled: bool = True
    trace_enabled: bool = True
    profile_enabled: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = None
    max_trace_depth: int = 10
    max_log_size: int = 10000


# ============================================================================
# 核心功能
# ============================================================================

class DebugManager:
    """调试管理器"""
    
    def __init__(self):
        self._config = DebugConfig()
        self._trace_records: List[TraceRecord] = []
        self._debug_logs: List[DebugInfo] = []
        self._current_trace_depth = 0
        self._profiler: Optional[cProfile.Profile] = None
    
    def set_config(self, config: DebugConfig):
        """
        设置调试配置
        
        Args:
            config: 调试配置
        """
        self._config = config
    
    def get_config(self) -> DebugConfig:
        """
        获取调试配置
        
        Returns:
            调试配置
        """
        return self._config
    
    def log(self, message: str, level: str = "INFO", context: Optional[Dict[str, Any]] = None):
        """
        记录调试日志
        
        Args:
            message: 日志消息
            level: 日志级别
            context: 上下文信息
        """
        if not self._config.enabled:
            return
        
        # 获取调用栈
        stack = traceback.format_stack()[:-1]  # 排除当前调用
        
        debug_info = DebugInfo(
            level=level,
            message=message,
            context=context or {},
            stack=stack
        )
        
        # 添加到日志列表
        self._debug_logs.append(debug_info)
        
        # 限制日志大小
        if len(self._debug_logs) > self._config.max_log_size:
            self._debug_logs.pop(0)
        
        # 输出到控制台
        if level in ["ERROR", "WARNING"] or self._config.log_level == "DEBUG":
            print(f"[{level}] {message}")
        
        # 输出到文件
        if self._config.log_file:
            try:
                with open(self._config.log_file, 'a') as f:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}\n")
                    if context:
                        f.write(f"  Context: {context}\n")
            except Exception:
                pass
    
    def trace(self, func: Callable) -> Callable:
        """
        跟踪函数执行
        
        Args:
            func: 要跟踪的函数
        
        Returns:
            装饰后的函数
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not self._config.enabled or not self._config.trace_enabled:
                return func(*args, **kwargs)
            
            # 检查跟踪深度
            if self._current_trace_depth >= self._config.max_trace_depth:
                return func(*args, **kwargs)
            
            # 记录开始时间
            start_time = time.time()
            self._current_trace_depth += 1
            
            # 获取函数信息
            func_name = func.__name__
            frame = inspect.currentframe().f_back
            file_name = frame.f_code.co_filename
            line_number = frame.f_lineno
            
            # 准备参数信息
            args_info = {}
            for i, arg in enumerate(args):
                arg_name = inspect.getfullargspec(func).args[i] if i < len(inspect.getfullargspec(func).args) else f"arg{i}"
                args_info[arg_name] = self._format_value(arg)
            
            kwargs_info = {k: self._format_value(v) for k, v in kwargs.items()}
            
            # 创建跟踪记录
            trace_record = TraceRecord(
                function=func_name,
                file=file_name,
                line=line_number,
                args=args_info,
                kwargs=kwargs_info
            )
            
            try:
                # 执行函数
                result = func(*args, **kwargs)
                trace_record.result = self._format_value(result)
                return result
            except Exception as e:
                trace_record.error = str(e)
                trace_record.stack = traceback.format_exc()
                raise
            finally:
                # 记录结束时间
                trace_record.duration = time.time() - start_time
                self._current_trace_depth -= 1
                
                # 添加到跟踪记录
                self._trace_records.append(trace_record)
                
                # 限制跟踪记录大小
                if len(self._trace_records) > self._config.max_log_size:
                    self._trace_records.pop(0)
        
        return wrapper
    
    def profile(self, func: Callable) -> Callable:
        """
        性能分析装饰器
        
        Args:
            func: 要分析的函数
        
        Returns:
            装饰后的函数
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not self._config.enabled or not self._config.profile_enabled:
                return func(*args, **kwargs)
            
            # 开始分析
            self._profiler = cProfile.Profile()
            self._profiler.enable()
            
            try:
                return func(*args, **kwargs)
            finally:
                # 结束分析
                self._profiler.disable()
                
                # 输出分析结果
                s = io.StringIO()
                ps = pstats.Stats(self._profiler, stream=s).sort_stats('cumulative')
                ps.print_stats(20)  # 显示前20个函数
                self.log("Performance profile:\n" + s.getvalue(), level="DEBUG")
        
        return wrapper
    
    def get_trace_records(self) -> List[TraceRecord]:
        """
        获取跟踪记录
        
        Returns:
            跟踪记录列表
        """
        return self._trace_records
    
    def get_debug_logs(self) -> List[DebugInfo]:
        """
        获取调试日志
        
        Returns:
            调试日志列表
        """
        return self._debug_logs
    
    def clear_trace_records(self):
        """
        清除跟踪记录
        """
        self._trace_records.clear()
    
    def clear_debug_logs(self):
        """
        清除调试日志
        """
        self._debug_logs.clear()
    
    def dump_trace(self, filename: str = "trace_dump.txt"):
        """
        导出跟踪记录
        
        Args:
            filename: 导出文件名
        """
        try:
            with open(filename, 'w') as f:
                for record in self._trace_records:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.timestamp))}]\n")
                    f.write(f"  Function: {record.function}\n")
                    f.write(f"  File: {record.file}:{record.line}\n")
                    f.write(f"  Args: {record.args}\n")
                    f.write(f"  Kwargs: {record.kwargs}\n")
                    if record.result is not None:
                        f.write(f"  Result: {record.result}\n")
                    if record.error:
                        f.write(f"  Error: {record.error}\n")
                    if record.duration:
                        f.write(f"  Duration: {record.duration:.4f}s\n")
                    f.write("\n")
            self.log(f"Trace dumped to {filename}")
        except Exception as e:
            self.log(f"Failed to dump trace: {str(e)}", level="ERROR")
    
    def dump_logs(self, filename: str = "debug_logs.txt"):
        """
        导出调试日志
        
        Args:
            filename: 导出文件名
        """
        try:
            with open(filename, 'w') as f:
                for log in self._debug_logs:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(log.timestamp))}] [{log.level}]\n")
                    f.write(f"  Message: {log.message}\n")
                    if log.context:
                        f.write(f"  Context: {log.context}\n")
                    if log.stack:
                        f.write("  Stack:\n")
                        for line in log.stack:
                            f.write(f"    {line.rstrip()}\n")
                    if log.duration:
                        f.write(f"  Duration: {log.duration:.4f}s\n")
                    f.write("\n")
            self.log(f"Logs dumped to {filename}")
        except Exception as e:
            self.log(f"Failed to dump logs: {str(e)}", level="ERROR")
    
    def _format_value(self, value: Any) -> str:
        """
        格式化值，避免过长
        
        Args:
            value: 要格式化的值
        
        Returns:
            格式化后的值
        """
        try:
            str_value = str(value)
            if len(str_value) > 100:
                return str_value[:100] + "..."
            return str_value
        except Exception:
            return "<unprintable>"


# ============================================================================
# 便捷函数
# ============================================================================

_debug_manager: Optional[DebugManager] = None


def get_debug_manager() -> DebugManager:
    """
    获取调试管理器实例
    
    Returns:
        调试管理器实例
    """
    global _debug_manager
    if _debug_manager is None:
        _debug_manager = DebugManager()
    return _debug_manager


def set_debug_config(config: DebugConfig):
    """
    设置调试配置
    
    Args:
        config: 调试配置
    """
    manager = get_debug_manager()
    manager.set_config(config)


def debug_log(message: str, level: str = "INFO", context: Optional[Dict[str, Any]] = None):
    """
    记录调试日志
    
    Args:
        message: 日志消息
        level: 日志级别
        context: 上下文信息
    """
    manager = get_debug_manager()
    manager.log(message, level, context)


def debug_trace(func: Callable) -> Callable:
    """
    跟踪函数执行
    
    Args:
        func: 要跟踪的函数
    
    Returns:
        装饰后的函数
    """
    manager = get_debug_manager()
    return manager.trace(func)


def debug_profile(func: Callable) -> Callable:
    """
    性能分析装饰器
    
    Args:
        func: 要分析的函数
    
    Returns:
        装饰后的函数
    """
    manager = get_debug_manager()
    return manager.profile(func)


def get_trace_records() -> List[TraceRecord]:
    """
    获取跟踪记录
    
    Returns:
        跟踪记录列表
    """
    manager = get_debug_manager()
    return manager.get_trace_records()


def get_debug_logs() -> List[DebugInfo]:
    """
    获取调试日志
    
    Returns:
        调试日志列表
    """
    manager = get_debug_manager()
    return manager.get_debug_logs()


def clear_trace_records():
    """
    清除跟踪记录
    """
    manager = get_debug_manager()
    manager.clear_trace_records()


def clear_debug_logs():
    """
    清除调试日志
    """
    manager = get_debug_manager()
    manager.clear_debug_logs()


def dump_trace(filename: str = "trace_dump.txt"):
    """
    导出跟踪记录
    
    Args:
        filename: 导出文件名
    """
    manager = get_debug_manager()
    manager.dump_trace(filename)


def dump_logs(filename: str = "debug_logs.txt"):
    """
    导出调试日志
    
    Args:
        filename: 导出文件名
    """
    manager = get_debug_manager()
    manager.dump_logs(filename)


# ============================================================================
# 调试命令
# ============================================================================

def debug_inspect(obj: Any) -> Dict[str, Any]:
    """
    检查对象
    
    Args:
        obj: 要检查的对象
    
    Returns:
        对象信息
    """
    info = {
        "type": type(obj).__name__,
        "repr": repr(obj),
        "id": id(obj)
    }
    
    # 检查属性
    if hasattr(obj, "__dict__"):
        info["attributes"] = {}
        for attr in dir(obj):
            if not attr.startswith("_"):
                try:
                    value = getattr(obj, attr)
                    info["attributes"][attr] = str(value)[:100]
                except Exception:
                    info["attributes"][attr] = "<unavailable>"
    
    # 检查序列
    if isinstance(obj, (list, tuple, set)):
        info["length"] = len(obj)
        info["first_few"] = str(obj[:5]) if len(obj) > 5 else str(obj)
    
    # 检查字典
    if isinstance(obj, dict):
        info["length"] = len(obj)
        info["keys"] = list(obj.keys())[:10]  # 只显示前10个键
    
    return info


def debug_timeit(func: Callable, *args, **kwargs) -> Dict[str, Any]:
    """
    测量函数执行时间
    
    Args:
        func: 要测量的函数
        *args: 函数参数
        **kwargs: 函数关键字参数
    
    Returns:
        执行结果和时间信息
    """
    start_time = time.time()
    try:
        result = func(*args, **kwargs)
        success = True
        error = None
    except Exception as e:
        result = None
        success = False
        error = str(e)
    finally:
        duration = time.time() - start_time
    
    return {
        "result": result,
        "duration": duration,
        "success": success,
        "error": error
    }


def debug_traceback() -> str:
    """
    获取当前调用栈
    
    Returns:
        调用栈字符串
    """
    return ''.join(traceback.format_stack())


def debug_memory_usage() -> Dict[str, Any]:
    """
    检查内存使用情况
    
    Returns:
        内存使用信息
    """
    try:
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        return {
            "rss": memory_info.rss / 1024 / 1024,  # MB
            "vms": memory_info.vms / 1024 / 1024,  # MB
            "percent": process.memory_percent()
        }
    except ImportError:
        return {"error": "psutil not installed"}
