"""
配置管理模块
============
多格式配置加载、热重载、多源合并。

支持 JSON / YAML / INI 格式，按优先级深度合并多个配置源。
"""

import configparser
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class ConfigSource:
    """配置源"""
    name: str
    path: str
    format: str = "yaml"       # json | yaml | ini
    priority: int = 0           # 数字越大优先级越高
    enabled: bool = True


@dataclass
class ConfigValidationResult:
    """配置验证结果"""
    valid: bool
    errors: List[str] = field(default_factory=list)


class ConfigManager:
    """配置管理器 — 多源加载、热重载、深度合并"""

    def __init__(self, config_dir: str = "./config", hot_reload: bool = True,
                 reload_interval: float = 5.0, validate: bool = True):
        self.config_dir = config_dir
        self.hot_reload = hot_reload
        self.reload_interval = reload_interval
        self.validate_enabled = validate
        self._sources: List[ConfigSource] = []
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._last_reload = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ---- 生命周期 ----

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            os.makedirs(self.config_dir, exist_ok=True)
            self._reload()
            if self.hot_reload:
                self._thread = threading.Thread(target=self._reload_loop, daemon=True)
                self._thread.start()

    def stop(self):
        with self._lock:
            self._running = False
            if self._thread:
                self._thread.join(timeout=2)

    # ---- 配置源管理 ----

    def add_source(self, source: ConfigSource):
        with self._lock:
            self._sources.append(source)
            self._sources.sort(key=lambda s: s.priority, reverse=True)
            self._reload()

    def remove_source(self, name: str):
        with self._lock:
            self._sources = [s for s in self._sources if s.name != name]
            self._reload()

    # ---- 配置读写 ----

    def get(self, key: str, default: Any = None) -> Any:
        """点号分隔的嵌套键读取"""
        with self._lock:
            self._maybe_reload()
            node = self._data
            for k in key.split("."):
                if isinstance(node, dict) and k in node:
                    node = node[k]
                else:
                    return default
            return node

    def set(self, key: str, value: Any):
        """点号分隔的嵌套键写入"""
        with self._lock:
            keys = key.split(".")
            node = self._data
            for k in keys[:-1]:
                if k not in node or not isinstance(node[k], dict):
                    node[k] = {}
                node = node[k]
            node[keys[-1]] = value

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    # ---- 内部方法 ----

    def _maybe_reload(self):
        if self.hot_reload and time.time() - self._last_reload > self.reload_interval:
            self._reload()

    def _reload(self):
        merged: Dict[str, Any] = {}
        for source in self._sources:
            if source.enabled:
                loaded = self._load_file(source)
                self._deep_merge(merged, loaded)

        if self.validate_enabled:
            result = self._validate(merged)
            if not result.valid:
                print(f"[Config] 验证错误: {result.errors}")

        self._data = merged
        self._last_reload = time.time()

    def _load_file(self, source: ConfigSource) -> Dict[str, Any]:
        if not os.path.exists(source.path):
            return {}
        try:
            with open(source.path, encoding="utf-8") as f:
                if source.format == "json":
                    return json.load(f)
                elif source.format == "yaml":
                    return yaml.safe_load(f) or {}
                elif source.format == "ini":
                    cp = configparser.ConfigParser()
                    cp.read(source.path)
                    return {s: dict(cp[s]) for s in cp.sections()}
        except Exception as e:
            print(f"[Config] 加载失败 {source.path}: {e}")
        return {}

    def _deep_merge(self, target: dict, source: dict):
        for k, v in source.items():
            if k in target and isinstance(target[k], dict) and isinstance(v, dict):
                self._deep_merge(target[k], v)
            else:
                target[k] = v

    def _validate(self, config: dict) -> ConfigValidationResult:
        errors = []
        required = ["system.name", "system.version"]
        for key in required:
            if self._get_nested(config, key) is None:
                errors.append(f"缺少必需配置: {key}")
        return ConfigValidationResult(valid=len(errors) == 0, errors=errors)

    def _get_nested(self, d: dict, key: str) -> Any:
        for k in key.split("."):
            if isinstance(d, dict):
                d = d.get(k)
            else:
                return None
        return d

    def _reload_loop(self):
        while self._running:
            time.sleep(self.reload_interval)
            with self._lock:
                self._reload()