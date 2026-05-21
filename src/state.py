"""
高级状态管理系统 — 照搬 Claude Code 设计
====================================
核心功能：
- 完整的应用状态管理
- 状态选择器模式
- 发布-订阅机制
- 状态变化监听
- 更好的状态一致性
"""

from typing import Generic, TypeVar, Callable, Set, Any, Dict, Optional, List


# ============================================================================# 类型定义# ============================================================================

T = TypeVar('T')
R = TypeVar('R')

Listener = Callable[[], None]
OnChange = Callable[[Dict[str, Any]], None]


class Store(Generic[T]):
    """状态存储"""
    
    def __init__(self, initial_state: T, on_change: Optional[OnChange] = None):
        """初始化状态存储"""
        self._state = initial_state
        self._listeners: Set[Listener] = set()
        self._on_change = on_change
    
    def get_state(self) -> T:
        """获取当前状态"""
        return self._state
    
    def set_state(self, updater: Callable[[T], T]):
        """更新状态"""
        prev = self._state
        next_state = updater(prev)
        
        # 检查状态是否变化
        if next_state is prev:
            return
        
        self._state = next_state
        
        # 通知监听器
        if self._on_change:
            self._on_change({"newState": next_state, "oldState": prev})
        
        # 触发所有订阅者
        for listener in self._listeners:
            listener()
    
    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """订阅状态变化"""
        self._listeners.add(listener)
        
        # 返回取消订阅函数
        def unsubscribe():
            self._listeners.remove(listener)
        
        return unsubscribe


def create_store(initial_state: T, on_change: Optional[OnChange] = None) -> Store[T]:
    """创建状态存储"""
    return Store(initial_state, on_change)


# ============================================================================# 状态选择器# ============================================================================

def create_selector(
    selectors: List[Callable[[T], Any]],
    result_func: Callable[..., R]
) -> Callable[[T], R]:
    """创建状态选择器"""
    def selector(state: T) -> R:
        args = [sel(state) for sel in selectors]
        return result_func(*args)
    return selector


# ============================================================================# 应用状态类型# ============================================================================

class AppState:
    """应用状态"""
    
    def __init__(self):
        self.session = {
            "id": None,
            "status": "idle",  # idle, active, error
            "last_activity": None
        }
        self.ui = {
            "theme": "light",
            "sidebar_open": True,
            "active_tab": "chat"
        }
        self.memory = {
            "last_consolidation": None,
            "memory_count": 0
        }
        self.evolution = {
            "last_evolution": None,
            "pending_changes": 0
        }
        self.tools = {
            "enabled": [],
            "disabled": []
        }
        self.buddy = {
            "name": None,
            "level": 1,
            "mood": "happy"
        }
        # 通用键值存储
        self._kv_store = {}
    
    def set(self, key: str, value: Any):
        """设置键值对"""
        self._kv_store[key] = value
    
    def get(self, key: str, default: Any = None):
        """获取键值对"""
        return self._kv_store.get(key, default)
    
    def delete(self, key: str):
        """删除键值对"""
        if key in self._kv_store:
            del self._kv_store[key]
    
    def has(self, key: str) -> bool:
        """检查键是否存在"""
        return key in self._kv_store
    
    def keys(self) -> list:
        """获取所有键"""
        return list(self._kv_store.keys())
    
    def clear(self):
        """清空所有键值对"""
        self._kv_store.clear()


# ============================================================================# 状态选择器# ============================================================================

def select_session_status(state: AppState) -> str:
    """选择会话状态"""
    return state.session.get("status", "idle")

def select_ui_theme(state: AppState) -> str:
    """选择UI主题"""
    return state.ui.get("theme", "light")

def select_memory_count(state: AppState) -> int:
    """选择记忆数量"""
    return state.memory.get("memory_count", 0)

def select_pending_changes(state: AppState) -> int:
    """选择待处理的更改数量"""
    return state.evolution.get("pending_changes", 0)

def select_buddy_mood(state: AppState) -> str:
    """选择宠物心情"""
    return state.buddy.get("mood", "happy")


# ============================================================================# 复合选择器# ============================================================================

def select_app_summary(state: AppState) -> Dict[str, Any]:
    """选择应用摘要"""
    return {
        "session_status": select_session_status(state),
        "ui_theme": select_ui_theme(state),
        "memory_count": select_memory_count(state),
        "pending_changes": select_pending_changes(state),
        "buddy_mood": select_buddy_mood(state)
    }


# ============================================================================# 状态管理工具# ============================================================================

class StateManager:
    """
    状态管理器
    功能：
    1. 管理应用状态
    2. 提供状态更新方法
    3. 处理状态变化监听
    4. 提供状态选择器
    """
    
    def __init__(self):
        """初始化状态管理器"""
        initial_state = AppState()
        self.store = create_store(initial_state, self._on_state_change)
        self.listeners: Set[Callable[[AppState], None]] = set()
    
    def _on_state_change(self, change: Dict[str, Any]):
        """状态变化回调"""
        new_state = change.get("newState")
        for listener in self.listeners:
            listener(new_state)
    
    def get_state(self) -> AppState:
        """获取当前状态"""
        return self.store.get_state()
    
    def update_session(self, updates: Dict[str, Any]):
        """更新会话状态"""
        def updater(state: AppState):
            new_state = AppState()
            new_state.__dict__.update(state.__dict__)
            # 安全地更新会话状态，确保session字典存在
            if not hasattr(new_state, 'session') or not isinstance(new_state.session, dict):
                new_state.session = {}
            new_state.session.update(updates)
            return new_state
        self.store.set_state(updater)
    
    def update_ui(self, updates: Dict[str, Any]):
        """更新UI状态"""
        def updater(state: AppState):
            new_state = AppState()
            new_state.__dict__.update(state.__dict__)
            # 安全地更新UI状态，确保ui字典存在
            if not hasattr(new_state, 'ui') or not isinstance(new_state.ui, dict):
                new_state.ui = {}
            new_state.ui.update(updates)
            return new_state
        self.store.set_state(updater)
    
    def update_memory(self, updates: Dict[str, Any]):
        """更新记忆状态"""
        def updater(state: AppState):
            new_state = AppState()
            new_state.__dict__.update(state.__dict__)
            # 安全地更新记忆状态，确保memory字典存在
            if not hasattr(new_state, 'memory') or not isinstance(new_state.memory, dict):
                new_state.memory = {}
            new_state.memory.update(updates)
            return new_state
        self.store.set_state(updater)
    
    def update_evolution(self, updates: Dict[str, Any]):
        """更新进化状态"""
        def updater(state: AppState):
            new_state = AppState()
            new_state.__dict__.update(state.__dict__)
            # 安全地更新进化状态，确保evolution字典存在
            if not hasattr(new_state, 'evolution') or not isinstance(new_state.evolution, dict):
                new_state.evolution = {}
            new_state.evolution.update(updates)
            return new_state
        self.store.set_state(updater)
    
    def update_tools(self, updates: Dict[str, Any]):
        """更新工具状态"""
        def updater(state: AppState):
            new_state = AppState()
            new_state.__dict__.update(state.__dict__)
            # 安全地更新工具状态，确保tools字典存在
            if not hasattr(new_state, 'tools') or not isinstance(new_state.tools, dict):
                new_state.tools = {}
            new_state.tools.update(updates)
            return new_state
        self.store.set_state(updater)
    
    def update_buddy(self, updates: Dict[str, Any]):
        """更新宠物状态"""
        def updater(state: AppState):
            new_state = AppState()
            new_state.__dict__.update(state.__dict__)
            # 安全地更新宠物状态，确保buddy字典存在
            if not hasattr(new_state, 'buddy') or not isinstance(new_state.buddy, dict):
                new_state.buddy = {}
            new_state.buddy.update(updates)
            return new_state
        self.store.set_state(updater)
    
    def subscribe(self, listener: Callable[[AppState], None]) -> Callable[[], None]:
        """订阅状态变化"""
        self.listeners.add(listener)
        
        # 返回取消订阅函数
        def unsubscribe():
            self.listeners.remove(listener)
        
        return unsubscribe
    
    def get_session_status(self) -> str:
        """获取会话状态"""
        state = self.get_state()
        # 安全访问：检查session是否存在且为字典
        if hasattr(state, 'session') and isinstance(state.session, dict):
            return state.session.get("status", "idle")
        return "idle"
    
    def get_ui_theme(self) -> str:
        """获取UI主题"""
        state = self.get_state()
        # 安全访问：检查ui是否存在且为字典
        if hasattr(state, 'ui') and isinstance(state.ui, dict):
            return state.ui.get("theme", "light")
        return "light"
    
    def get_memory_count(self) -> int:
        """获取记忆数量"""
        state = self.get_state()
        # 安全访问：检查memory是否存在且为字典
        if hasattr(state, 'memory') and isinstance(state.memory, dict):
            return state.memory.get("memory_count", 0)
        return 0
    
    def get_pending_changes(self) -> int:
        """获取待处理的更改数量"""
        state = self.get_state()
        # 安全访问：检查evolution是否存在且为字典
        if hasattr(state, 'evolution') and isinstance(state.evolution, dict):
            return state.evolution.get("pending_changes", 0)
        return 0
    
    def get_buddy_mood(self) -> str:
        """获取宠物心情"""
        state = self.get_state()
        # 安全访问：检查buddy是否存在且为字典
        if hasattr(state, 'buddy') and isinstance(state.buddy, dict):
            return state.buddy.get("mood", "happy")
        return "happy"
    
    def get_app_summary(self) -> Dict[str, Any]:
        """获取应用摘要"""
        state = self.get_state()
        return {
            "session_status": select_session_status(state),
            "ui_theme": select_ui_theme(state),
            "memory_count": select_memory_count(state),
            "pending_changes": select_pending_changes(state),
            "buddy_mood": select_buddy_mood(state)
        }


# ============================================================================# 便捷函数# ============================================================================

def create_state_manager() -> StateManager:
    """创建状态管理器"""
    return StateManager()