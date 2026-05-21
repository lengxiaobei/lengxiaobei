"""
性能优化模块 - 照搬 Claude Code 设计
====================================
核心特性：
- 异步处理框架
- 缓存机制
- 并发控制
- 性能监控

参考 Claude Code 的性能优化实现
"""

import asyncio
import functools
import time
from typing import Any, Callable, Coroutine as CoroutineType
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Union, TypeVar, Generic


# ============================================================================
# 类型定义
# ============================================================================

T = TypeVar('T')

@dataclass
class CacheItem(Generic[T]):
    """缓存项"""
    value: T
    timestamp: float = field(default_factory=time.time)
    ttl: Optional[float] = None  # 过期时间（秒）


@dataclass
class AsyncTask:
    """异步任务"""
    coro: Callable[..., CoroutineType]
    args: tuple = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    task_id: str = field(default_factory=lambda: str(time.time()))


@dataclass
class PerformanceConfig:
    """性能配置"""
    max_concurrency: int = 10
    cache_enabled: bool = True
    cache_size: int = 1000
    default_ttl: float = 3600  # 默认缓存过期时间（秒）
    async_enabled: bool = True


# ============================================================================
# 缓存系统
# ============================================================================

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, config: Optional[PerformanceConfig] = None):
        self._config = config or PerformanceConfig()
        self._cache: Dict[str, CacheItem] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = 60  # 清理间隔（秒）
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        def cleanup():  # type: ignore
            while True:
                time.sleep(self._cleanup_interval)
                self._cleanup_expired()
        
        thread = threading.Thread(target=cleanup, daemon=True)
        thread.start()
    
    def _cleanup_expired(self):
        """清理过期缓存"""
        with self._lock:
            now = time.time()
            expired_keys = []
            
            for key, item in self._cache.items():
                if item.ttl and now - item.timestamp > item.ttl:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存
        
        Args:
            key: 缓存键
        
        Returns:
            缓存值
        """
        if not self._config.cache_enabled:
            return None
        
        with self._lock:
            if key not in self._cache:
                return None
            
            item = self._cache[key]
            
            # 检查是否过期
            if item.ttl and time.time() - item.timestamp > item.ttl:
                del self._cache[key]
                return None
            
            return item.value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
        """
        if not self._config.cache_enabled:
            return
        
        with self._lock:
            # 检查缓存大小
            if len(self._cache) >= self._config.cache_size:
                # 移除最旧的缓存
                oldest_key = min(self._cache, key=lambda k: self._cache[k].timestamp)
                del self._cache[oldest_key]
            
            self._cache[key] = CacheItem(
                value=value,
                ttl=ttl or self._config.default_ttl
            )
    
    def delete(self, key: str) -> None:
        """
        删除缓存
        
        Args:
            key: 缓存键
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self) -> None:
        """
        清空缓存
        """
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """
        获取缓存大小
        
        Returns:
            缓存大小
        """
        with self._lock:
            return len(self._cache)
    
    def keys(self) -> List[str]:
        """
        获取所有缓存键
        
        Returns:
            缓存键列表
        """
        with self._lock:
            return list(self._cache.keys())


# ============================================================================
# 异步处理系统
# ============================================================================

class AsyncManager:
    """异步管理器"""
    
    def __init__(self, config: Optional[PerformanceConfig] = None):
        self._config = config or PerformanceConfig()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrency)
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
    
    async def run(self, coro: Callable[..., CoroutineType], *args, **kwargs) -> Any:
        """
        运行异步任务
        
        Args:
            coro: 协程函数
            *args: 函数参数
            **kwargs: 函数关键字参数
        
        Returns:
            任务结果
        """
        if not self._config.async_enabled:
            # 同步执行
            return await coro(*args, **kwargs)
        
        async with self._semaphore:
            return await coro(*args, **kwargs)
    
    async def run_with_timeout(self, coro: Callable[..., CoroutineType], timeout: float, *args, **kwargs) -> Any:
        """
        带超时的异步任务
        
        Args:
            coro: 协程函数
            timeout: 超时时间（秒）
            *args: 函数参数
            **kwargs: 函数关键字参数
        
        Returns:
            任务结果
        """
        try:
            return await asyncio.wait_for(
                self.run(coro, *args, **kwargs),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Task timed out after {timeout} seconds")
    
    async def run_all(self, tasks: List[AsyncTask]) -> Dict[str, Any]:
        """
        运行多个异步任务
        
        Args:
            tasks: 任务列表
        
        Returns:
            任务结果字典
        """
        async def run_task(task: AsyncTask) -> tuple:
            try:
                result = await self.run(task.coro, *task.args, **task.kwargs)
                return (task.task_id, result, None)
            except Exception as e:
                return (task.task_id, None, e)
        
        # 按优先级排序
        tasks.sort(key=lambda t: t.priority, reverse=True)
        
        # 并发执行
        results = await asyncio.gather(*[run_task(task) for task in tasks])
        
        # 整理结果
        result_dict = {}
        for task_id, result, error in results:
            if error:
                result_dict[task_id] = error
            else:
                result_dict[task_id] = result
        
        return result_dict
    
    async def schedule(self, task: AsyncTask) -> str:
        """
        调度异步任务
        
        Args:
            task: 异步任务
        
        Returns:
            任务ID
        """
        async def wrapper():
            try:
                result = await self.run(task.coro, *task.args, **task.kwargs)
                return result
            finally:
                async with self._lock:
                    if task.task_id in self._tasks:
                        del self._tasks[task.task_id]
        
        async with self._lock:
            self._tasks[task.task_id] = asyncio.create_task(wrapper())
        
        return task.task_id
    
    async def get_task_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """
        获取任务结果
        
        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）
        
        Returns:
            任务结果
        """
        async with self._lock:
            if task_id not in self._tasks:
                raise ValueError(f"Task {task_id} not found")
            
            task = self._tasks[task_id]
        
        if timeout:
            return await asyncio.wait_for(task, timeout=timeout)
        else:
            return await task
    
    def get_pending_tasks(self) -> List[str]:
        """
        获取待处理任务
        
        Returns:
            任务ID列表
        """
        return list(self._tasks.keys())


# ============================================================================
# 装饰器
# ============================================================================

_cache_manager: Optional[CacheManager] = None
_async_manager: Optional[AsyncManager] = None


def get_cache_manager() -> CacheManager:
    """
    获取缓存管理器
    
    Returns:
        缓存管理器实例
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def get_async_manager() -> AsyncManager:
    """
    获取异步管理器
    
    Returns:
        异步管理器实例
    """
    global _async_manager
    if _async_manager is None:
        _async_manager = AsyncManager()
    return _async_manager


def cached(ttl: Optional[float] = None):
    """
    缓存装饰器
    
    Args:
        ttl: 过期时间（秒）
    
    Returns:
        装饰后的函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            key_parts = [func.__name__]
            for arg in args:
                key_parts.append(str(arg))
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={v}")
            cache_key = "_".join(key_parts)
            
            # 尝试从缓存获取
            cache_manager = get_cache_manager()
            cached_value = cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            cache_manager.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


async def async_cached(ttl: Optional[float] = None):
    """
    异步缓存装饰器
    
    Args:
        ttl: 过期时间（秒）
    
    Returns:
        装饰后的协程函数
    """
    def decorator(func: Callable[..., CoroutineType]) -> Callable[..., CoroutineType]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            key_parts = [func.__name__]
            for arg in args:
                key_parts.append(str(arg))
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={v}")
            cache_key = "_".join(key_parts)
            
            # 尝试从缓存获取
            cache_manager = get_cache_manager()
            cached_value = cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # 执行函数
            result = await func(*args, **kwargs)
            
            # 缓存结果
            cache_manager.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def async_wrap(func: Callable) -> Callable[..., CoroutineType]:
    """
    同步函数转异步
    
    Args:
        func: 同步函数
    
    Returns:
        异步函数
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
    return wrapper


def parallelize(max_workers: Optional[int] = None):
    """
    并行执行装饰器
    
    Args:
        max_workers: 最大工作线程数
    
    Returns:
        装饰后的函数
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(items, *args, **kwargs):
            from concurrent.futures import ThreadPoolExecutor
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                results = list(executor.map(
                    lambda item: func(item, *args, **kwargs),
                    items
                ))
            return results
        return wrapper
    return decorator


# ============================================================================
# 性能监控
# ============================================================================

@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self._metrics: List[PerformanceMetric] = []
        self._lock = threading.RLock()
    
    def record(self, name: str, value: float, unit: str):
        """
        记录性能指标
        
        Args:
            name: 指标名称
            value: 指标值
            unit: 单位
        """
        with self._lock:
            metric = PerformanceMetric(
                name=name,
                value=value,
                unit=unit
            )
            self._metrics.append(metric)
    
    def get_metrics(self, name: Optional[str] = None) -> List[PerformanceMetric]:
        """
        获取性能指标
        
        Args:
            name: 指标名称（可选）
        
        Returns:
            性能指标列表
        """
        with self._lock:
            if name:
                return [m for m in self._metrics if m.name == name]
            else:
                return self._metrics.copy()
    
    def clear(self):
        """
        清空性能指标
        """
        with self._lock:
            self._metrics.clear()
    
    def get_stats(self, name: str) -> Dict[str, Any]:
        """
        获取指标统计信息
        
        Args:
            name: 指标名称
        
        Returns:
            统计信息
        """
        metrics = self.get_metrics(name)
        if not metrics:
            return {}
        
        values = [m.value for m in metrics]
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
            "last": values[-1]
        }


_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """
    获取性能监控器
    
    Returns:
        性能监控器实例
    """
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def measure_performance(func: Callable) -> Callable:
    """
    性能测量装饰器
    
    Args:
        func: 要测量的函数
    
    Returns:
        装饰后的函数
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            monitor = get_performance_monitor()
            monitor.record(f"{func.__name__}_duration", duration, "seconds")
    return wrapper


async def async_measure_performance(func: Callable[..., CoroutineType]) -> Callable[..., CoroutineType]:
    """
    异步性能测量装饰器
    
    Args:
        func: 要测量的协程函数
    
    Returns:
        装饰后的协程函数
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            monitor = get_performance_monitor()
            monitor.record(f"{func.__name__}_duration", duration, "seconds")
    return wrapper


# ============================================================================
# 便捷函数
# ============================================================================

def set_performance_config(config: PerformanceConfig):
    """
    设置性能配置
    
    Args:
        config: 性能配置
    """
    global _cache_manager, _async_manager
    _cache_manager = CacheManager(config)
    _async_manager = AsyncManager(config)


def clear_cache():
    """
    清空缓存
    """
    get_cache_manager().clear()


def get_cache_size() -> int:
    """
    获取缓存大小
    
    Returns:
        缓存大小
    """
    return get_cache_manager().size()

async def run_async(coro: Callable[..., CoroutineType], *args, **kwargs) -> Any:
    """
    运行异步任务
    
    Args:
        coro: 协程函数
        *args: 函数参数
        **kwargs: 函数关键字参数
    
    Returns:
        任务结果
    """
    return await get_async_manager().run(coro, *args, **kwargs)

async def run_async_with_timeout(coro: Callable[..., CoroutineType], timeout: float, *args, **kwargs) -> Any:
    """
    带超时的异步任务
    
    Args:
        coro: 协程函数
        timeout: 超时时间（秒）
        *args: 函数参数
        **kwargs: 函数关键字参数
    
    Returns:
        任务结果
    """
    return await get_async_manager().run_with_timeout(coro, timeout, *args, **kwargs)

async def run_async_all(tasks: List[AsyncTask]) -> Dict[str, Any]:
    """
    运行多个异步任务
    
    Args:
        tasks: 任务列表
    
    Returns:
        任务结果字典
    """
    return await get_async_manager().run_all(tasks)
