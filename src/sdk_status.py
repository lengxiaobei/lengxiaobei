"""
SDK 状态更新系统 - 照搬 Claude Code 设计
========================================
核心特性：
- SDK 状态管理
- 与外部系统状态同步
- 状态变更通知
- 状态持久化
- 状态恢复

参考 Claude Code 的 SDK 状态更新实现
"""

import json
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Set


# ============================================================================
# 类型定义
# ============================================================================

@dataclass
class SDKState:
    """SDK 状态"""
    version: str = "1.0.0"
    last_updated: float = field(default_factory=time.time)
    is_connected: bool = False
    connection_status: str = "disconnected"
    active_sessions: int = 0
    total_requests: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    custom_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateUpdate:
    """状态更新"""
    key: str
    value: Any
    timestamp: float = field(default_factory=time.time)
    source: str = "internal"


@dataclass
class SyncConfig:
    """同步配置"""
    enabled: bool = True
    sync_interval: float = 5.0  # 同步间隔（秒）
    retry_attempts: int = 3
    retry_delay: float = 2.0
    sync_endpoint: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class StatePersistenceConfig:
    """状态持久化配置"""
    enabled: bool = True
    persistence_file: str = ".sdk_state.json"
    save_interval: float = 10.0  # 保存间隔（秒）


# ============================================================================
# 核心功能
# ============================================================================

class SDKStatusManager:
    """SDK 状态管理器"""
    
    def __init__(self):
        self._state = SDKState()
        self._lock = threading.RLock()
        self._listeners: Set[Callable[[StateUpdate], None]] = set()
        self._sync_config = SyncConfig()
        self._persistence_config = StatePersistenceConfig()
        self._sync_thread: Optional[threading.Thread] = None
        self._persistence_thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self):
        """启动状态管理器"""
        with self._lock:
            if self._running:
                return
            
            self._running = True
            
            # 启动同步线程
            if self._sync_config.enabled:
                self._sync_thread = threading.Thread(
                    target=self._sync_loop,
                    daemon=True
                )
                self._sync_thread.start()
            
            # 启动持久化线程
            if self._persistence_config.enabled:
                self._persistence_thread = threading.Thread(
                    target=self._persistence_loop,
                    daemon=True
                )
                self._persistence_thread.start()
            
            # 加载持久化状态
            self._load_state()
    
    def stop(self):
        """停止状态管理器"""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            
            # 等待线程结束
            if self._sync_thread:
                self._sync_thread.join(timeout=2.0)
            if self._persistence_thread:
                self._persistence_thread.join(timeout=2.0)
            
            # 保存状态
            self._save_state()
    
    def get_state(self) -> SDKState:
        """获取当前状态"""
        with self._lock:
            return SDKState(**self._state.__dict__)
    
    def update_state(self, updates: Dict[str, Any], source: str = "internal"):
        """
        更新状态
        
        Args:
            updates: 状态更新字典
            source: 更新来源
        """
        with self._lock:
            for key, value in updates.items():
                if hasattr(self._state, key):
                    old_value = getattr(self._state, key)
                    setattr(self._state, key, value)
                    
                    # 创建状态更新事件
                    update = StateUpdate(
                        key=key,
                        value=value,
                        source=source
                    )
                    
                    # 通知监听器
                    self._notify_listeners(update)
            
            # 更新最后更新时间
            self._state.last_updated = time.time()
    
    def update_custom_state(self, key: str, value: Any, source: str = "internal"):
        """
        更新自定义状态
        
        Args:
            key: 自定义状态键
            value: 自定义状态值
            source: 更新来源
        """
        with self._lock:
            self._state.custom_state[key] = value
            
            # 创建状态更新事件
            update = StateUpdate(
                key=f"custom_{key}",
                value=value,
                source=source
            )
            
            # 通知监听器
            self._notify_listeners(update)
            
            # 更新最后更新时间
            self._state.last_updated = time.time()
    
    def register_listener(self, listener: Callable[[StateUpdate], None]):
        """
        注册状态变更监听器
        
        Args:
            listener: 监听器函数
        """
        with self._lock:
            self._listeners.add(listener)
    
    def unregister_listener(self, listener: Callable[[StateUpdate], None]):
        """
        注销状态变更监听器
        
        Args:
            listener: 监听器函数
        """
        with self._lock:
            self._listeners.remove(listener)
    
    def set_sync_config(self, config: SyncConfig):
        """
        设置同步配置
        
        Args:
            config: 同步配置
        """
        with self._lock:
            self._sync_config = config
    
    def set_persistence_config(self, config: StatePersistenceConfig):
        """
        设置持久化配置
        
        Args:
            config: 持久化配置
        """
        with self._lock:
            self._persistence_config = config
    
    def sync_with_external(self) -> bool:
        """
        与外部系统同步状态
        
        Returns:
            是否同步成功
        """
        if not self._sync_config.enabled or not self._sync_config.sync_endpoint:
            return False
        
        try:
            # 这里实现与外部系统的同步逻辑
            # 实际项目中可能需要使用 requests 库发送 HTTP 请求
            import requests
            
            state_dict = self._state.__dict__
            response = requests.post(
                self._sync_config.sync_endpoint,
                json=state_dict,
                headers=self._sync_config.headers,
                timeout=10.0
            )
            
            if response.status_code == 200:
                # 处理外部系统返回的状态
                external_state = response.json()
                self.update_state(external_state, source="external")
                return True
            else:
                return False
        except Exception as e:
            # 记录错误
            self.update_state({
                "error_count": self._state.error_count + 1,
                "last_error": str(e)
            })
            return False
    
    def _notify_listeners(self, update: StateUpdate):
        """通知监听器"""
        for listener in self._listeners:
            try:
                listener(update)
            except Exception as e:
                # 捕获监听器异常，避免影响其他监听器
                pass
    
    def _sync_loop(self):
        """同步循环"""
        while self._running:
            try:
                # 尝试同步
                success = self.sync_with_external()
                if not success:
                    # 重试
                    for attempt in range(self._sync_config.retry_attempts):
                        time.sleep(self._sync_config.retry_delay)
                        if self.sync_with_external():
                            break
            except Exception as e:
                # 记录错误
                self.update_state({
                    "error_count": self._state.error_count + 1,
                    "last_error": str(e)
                })
            
            # 等待下一次同步
            time.sleep(self._sync_config.sync_interval)
    
    def _persistence_loop(self):
        """持久化循环"""
        last_save_time = time.time()
        
        while self._running:
            current_time = time.time()
            if current_time - last_save_time >= self._persistence_config.save_interval:
                self._save_state()
                last_save_time = current_time
            
            # 等待下一次保存
            time.sleep(1.0)
    
    def _save_state(self):
        """保存状态到文件"""
        if not self._persistence_config.enabled:
            return
        
        try:
            state_dict = self._state.__dict__
            with open(self._persistence_config.persistence_file, 'w') as f:
                json.dump(state_dict, f, indent=2)
        except Exception as e:
            # 记录错误
            self.update_state({
                "error_count": self._state.error_count + 1,
                "last_error": f"Failed to save state: {str(e)}"
            })
    
    def _load_state(self):
        """从文件加载状态"""
        if not self._persistence_config.enabled:
            return
        
        try:
            with open(self._persistence_config.persistence_file, 'r') as f:
                state_dict = json.load(f)
                
                # 更新状态
                self.update_state(state_dict, source="persistence")
        except FileNotFoundError:
            # 文件不存在，创建新状态
            pass
        except Exception as e:
            # 记录错误
            self.update_state({
                "error_count": self._state.error_count + 1,
                "last_error": f"Failed to load state: {str(e)}"
            })


# ============================================================================
# 便捷函数
# ============================================================================

_sdk_status_manager: Optional[SDKStatusManager] = None


def get_sdk_status_manager() -> SDKStatusManager:
    """
    获取 SDK 状态管理器实例
    
    Returns:
        SDK 状态管理器实例
    """
    global _sdk_status_manager
    if _sdk_status_manager is None:
        _sdk_status_manager = SDKStatusManager()
    return _sdk_status_manager


def start_sdk_status_manager():
    """
    启动 SDK 状态管理器
    """
    manager = get_sdk_status_manager()
    manager.start()


def stop_sdk_status_manager():
    """
    停止 SDK 状态管理器
    """
    manager = get_sdk_status_manager()
    manager.stop()


def get_sdk_state() -> SDKState:
    """
    获取当前 SDK 状态
    
    Returns:
        SDK 状态
    """
    manager = get_sdk_status_manager()
    return manager.get_state()


def update_sdk_state(updates: Dict[str, Any], source: str = "internal"):
    """
    更新 SDK 状态
    
    Args:
        updates: 状态更新字典
        source: 更新来源
    """
    manager = get_sdk_status_manager()
    manager.update_state(updates, source)


def update_sdk_custom_state(key: str, value: Any, source: str = "internal"):
    """
    更新 SDK 自定义状态
    
    Args:
        key: 自定义状态键
        value: 自定义状态值
        source: 更新来源
    """
    manager = get_sdk_status_manager()
    manager.update_custom_state(key, value, source)


def register_sdk_state_listener(listener: Callable[[StateUpdate], None]):
    """
    注册 SDK 状态变更监听器
    
    Args:
        listener: 监听器函数
    """
    manager = get_sdk_status_manager()
    manager.register_listener(listener)


def unregister_sdk_state_listener(listener: Callable[[StateUpdate], None]):
    """
    注销 SDK 状态变更监听器
    
    Args:
        listener: 监听器函数
    """
    manager = get_sdk_status_manager()
    manager.unregister_listener(listener)


def sync_sdk_with_external() -> bool:
    """
    与外部系统同步 SDK 状态
    
    Returns:
        是否同步成功
    """
    manager = get_sdk_status_manager()
    return manager.sync_with_external()


def set_sdk_sync_config(config: SyncConfig):
    """
    设置 SDK 同步配置
    
    Args:
        config: 同步配置
    """
    manager = get_sdk_status_manager()
    manager.set_sync_config(config)


def set_sdk_persistence_config(config: StatePersistenceConfig):
    """
    设置 SDK 持久化配置
    
    Args:
        config: 持久化配置
    """
    manager = get_sdk_status_manager()
    manager.set_persistence_config(config)
