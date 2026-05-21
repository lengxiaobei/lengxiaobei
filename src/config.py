"""
配置管理模块
提供集中式配置管理系统，支持热更新和观察者模式
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Protocol


class ConfigObserver(Protocol):
    """配置观察者协议"""
    def on_config_change(self, key: str, value: Any) -> None:
        ...


class ConfigManager:
    """集中式配置管理系统"""
    
    def __init__(self):
        self.project_root: Path = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.config_file: Path = self.project_root / "config.json"
        self.last_modified: float = 0.0
        self.config_data: Dict[str, Any] = {}
        self._observers: list[ConfigObserver] = []
        
        self.load_config()
    
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
                self.last_modified = self.config_file.stat().st_mtime
                print(f"[ConfigManager] 配置加载成功")
            else:
                self._create_default_config()
        except json.JSONDecodeError as e:
            print(f"[ConfigManager] 配置文件格式错误: {e}")
            self._create_default_config()
        except IOError as e:
            print(f"[ConfigManager] 配置文件读取失败: {e}")
            self._create_default_config()
        except Exception as e:
            print(f"[ConfigManager] 加载配置失败: {e}")
            self._create_default_config()
    
    def _create_default_config(self) -> None:
        """创建默认配置"""
        self.config_data = {
            "project_root": str(self.project_root),
            "memory_dir": str(self.project_root / "memory"),
            "autonomy_level": 80,
            "llm": {
                "api_key": "",
                "model": "MiniMax-M2.7",
                "base_url": "https://api.minimax.chat/v1"
            },
            "clawmem": {
                "enabled": False
            },
            "log_level": "INFO",
            "editor_mode": "normal",
            "control_layer": {
                "api_url": "http://localhost:8080/api/v1",
                "timeout": 30
            },
            "memory_layer": {
                "api_url": "http://localhost:8081/api/v1",
                "timeout": 30
            },
            "qdrant": {
                "url": "http://192.168.31.138:6333",
                "collection": "lengxiaobei_memory"
            },
            "sandbox": {
                "enabled": True,
                "timeout": 30
            }
        }
        
        try:
            # 确保父目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            self.last_modified = self.config_file.stat().st_mtime
            print(f"[ConfigManager] 默认配置创建成功")
        except IOError as e:
            print(f"[ConfigManager] 创建默认配置失败(IO错误): {e}")
        except Exception as e:
            print(f"[ConfigManager] 创建默认配置失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key: 配置键，支持点号分隔的路径，如 "llm.api_key"
            default: 默认值
        
        Returns:
            配置值
        """
        self._check_for_updates()
        
        keys = key.split('.')
        value: Any = self.config_data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数配置值"""
        value = self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def get_str(self, key: str, default: str = "") -> str:
        """获取字符串配置值"""
        value = self.get(key, default)
        return str(value) if value is not None else default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔配置值"""
        value = self.get(key, default)
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)
    
    def set(self, key: str, value: Any) -> bool:
        """设置配置值
        
        Args:
            key: 配置键，支持点号分隔的路径
            value: 配置值
        
        Returns:
            是否设置成功
        """
        try:
            keys = key.split('.')
            config = self.config_data
            
            for i, k in enumerate(keys[:-1]):
                if k not in config:
                    config[k] = {}
                elif not isinstance(config[k], dict):
                    print(f"[ConfigManager] 路径冲突: {'.'.join(keys[:i+1])} 不是字典")
                    return False
                config = config[k]
            
            config[keys[-1]] = value
            self._save_config()
            self._notify_observers(key, value)
            return True
        except Exception as e:
            print(f"[ConfigManager] 设置配置失败: {e}")
            return False
    
    def _save_config(self) -> None:
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            self.last_modified = self.config_file.stat().st_mtime
            print(f"[ConfigManager] 配置保存成功")
        except IOError as e:
            print(f"[ConfigManager] 保存配置失败(IO错误): {e}")
        except Exception as e:
            print(f"[ConfigManager] 保存配置失败: {e}")
    
    def _check_for_updates(self) -> None:
        """检查配置文件是否被修改"""
        if self.config_file.exists():
            try:
                current_modified = self.config_file.stat().st_mtime
                if current_modified > self.last_modified:
                    print(f"[ConfigManager] 检测到配置文件变更，重新加载...")
                    self.load_config()
                    self._notify_observers("config.updated", self.config_data)
            except OSError as e:
                print(f"[ConfigManager] 检查配置更新失败: {e}")
    
    def register_observer(self, observer: ConfigObserver) -> None:
        """注册配置变更观察者"""
        if observer not in self._observers:
            self._observers.append(observer)
    
    def unregister_observer(self, observer: ConfigObserver) -> None:
        """注销配置变更观察者"""
        if observer in self._observers:
            self._observers.remove(observer)
    
    def _notify_observers(self, key: str, value: Any) -> None:
        """通知观察者配置变更"""
        for observer in self._observers:
            try:
                if hasattr(observer, "on_config_change"):
                    observer.on_config_change(key, value)
            except Exception as e:
                print(f"[ConfigManager] 通知观察者失败: {e}")
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        self._check_for_updates()
        return dict(self.config_data)


config_manager: ConfigManager = ConfigManager()


class Config:
    """配置类（兼容旧版）"""

    def __init__(self):
        self.project_root = config_manager.get_str("project_root")
        self.memory_dir = config_manager.get_str("memory_dir")
        self.autonomy_level = config_manager.get_int("autonomy_level")
        
        self.llm_api_key = config_manager.get_str("llm.api_key")
        self.llm_model = config_manager.get_str("llm.model")
        self.llm_base_url = config_manager.get_str("llm.base_url")

        self.clawmem_enabled = config_manager.get_bool("clawmem.enabled")

        self.log_level = config_manager.get_str("log_level")

        self.editor_mode = config_manager.get_str("editor_mode")