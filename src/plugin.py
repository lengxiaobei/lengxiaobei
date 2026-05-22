"""
Plugin 插件系统 — 照搬 Claude Code 设计
====================================
核心功能：
- 插件管理和加载
- 内置插件支持
- 外部插件安装
- 插件组件系统
- 插件错误处理
- 插件依赖管理
"""

import os
import json
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, Any, List, Optional, TypeVar, Protocol


# ============================================================================# 类型定义# ============================================================================

class PluginAuthor:
    """插件作者"""
    def __init__(self, name: str, email: Optional[str] = None, url: Optional[str] = None):
        self.name = name
        self.email = email
        self.url = url

class PluginManifest:
    """插件清单"""
    def __init__(self, name: str, version: str, description: str, author: PluginAuthor):
        self.name = name
        self.version = version
        self.description = description
        self.author = author

class CommandMetadata:
    """命令元数据"""
    def __init__(self, name: str, description: str, usage: Optional[str] = None):
        self.name = name
        self.description = description
        self.usage = usage

class BuiltinPluginDefinition:
    """内置插件定义"""
    def __init__(self, name: str, description: str, version: Optional[str] = None,
                 skills: Optional[List[Any]] = None, hooks: Optional[Dict[str, Any]] = None,
                 mcp_servers: Optional[Dict[str, Any]] = None, is_available: Optional[callable] = None,
                 default_enabled: bool = True):
        self.name = name
        self.description = description
        self.version = version
        self.skills = skills or []
        self.hooks = hooks or {}
        self.mcp_servers = mcp_servers or {}
        self.is_available = is_available
        self.default_enabled = default_enabled

class PluginRepository:
    """插件仓库"""
    def __init__(self, url: str, branch: str, last_updated: Optional[str] = None, commit_sha: Optional[str] = None):
        self.url = url
        self.branch = branch
        self.last_updated = last_updated
        self.commit_sha = commit_sha

class PluginConfig:
    """插件配置"""
    def __init__(self, project_root: str, repositories: Optional[Dict[str, PluginRepository]] = None):
        self.project_root = project_root
        self.repositories = repositories or {}

class LoadedPlugin:
    """已加载的插件"""
    def __init__(self, name: str, manifest: PluginManifest, path: str, source: str,
                 repository: str, enabled: Optional[bool] = None, is_builtin: bool = False,
                 sha: Optional[str] = None, commands_path: Optional[str] = None,
                 commands_paths: Optional[List[str]] = None,
                 commands_metadata: Optional[Dict[str, CommandMetadata]] = None,
                 agents_path: Optional[str] = None, agents_paths: Optional[List[str]] = None,
                 skills_path: Optional[str] = None, skills_paths: Optional[List[str]] = None,
                 output_styles_path: Optional[str] = None,
                 output_styles_paths: Optional[List[str]] = None,
                 hooks_config: Optional[Dict[str, Any]] = None,
                 mcp_servers: Optional[Dict[str, Any]] = None,
                 lsp_servers: Optional[Dict[str, Any]] = None,
                 settings: Optional[Dict[str, Any]] = None):
        self.name = name
        self.manifest = manifest
        self.path = path
        self.source = source
        self.repository = repository
        self.enabled = enabled
        self.is_builtin = is_builtin
        self.sha = sha
        self.commands_path = commands_path
        self.commands_paths = commands_paths or []
        self.commands_metadata = commands_metadata or {}
        self.agents_path = agents_path
        self.agents_paths = agents_paths or []
        self.skills_path = skills_path
        self.skills_paths = skills_paths or []
        self.output_styles_path = output_styles_path
        self.output_styles_paths = output_styles_paths or []
        self.hooks_config = hooks_config or {}
        self.mcp_servers = mcp_servers or {}
        self.lsp_servers = lsp_servers or {}
        self.settings = settings or {}

class PluginComponent:
    """插件组件类型"""
    COMMANDS = 'commands'
    AGENTS = 'agents'
    SKILLS = 'skills'
    HOOKS = 'hooks'
    OUTPUT_STYLES = 'output-styles'

class PluginError:
    """插件错误"""
    def __init__(self, error_type: str, source: str, **kwargs):
        self.type = error_type
        self.source = source
        self.__dict__.update(kwargs)

class PluginLoadResult:
    """插件加载结果"""
    def __init__(self, enabled: List[LoadedPlugin], disabled: List[LoadedPlugin], errors: List[PluginError]):
        self.enabled = enabled
        self.disabled = disabled
        self.errors = errors


# ============================================================================# 插件管理器# ============================================================================

class PluginManager:
    """
    插件管理器
    功能：
    1. 管理插件的加载和卸载
    2. 处理插件的安装和更新
    3. 管理插件的启用和禁用
    4. 提供插件组件的访问
    """
    
    def __init__(self, config: PluginConfig):
        """初始化插件管理器"""
        self.config = config
        self.plugins_dir = os.path.join(config.project_root, "plugins")
        self.builtin_plugins: List[BuiltinPluginDefinition] = []
        self.loaded_plugins: List[LoadedPlugin] = []
        self.plugin_errors: List[PluginError] = []
        
        # 确保插件目录存在
        os.makedirs(self.plugins_dir, exist_ok=True)
        
        # 注册内置插件
        self._register_builtin_plugins()
    
    def _register_builtin_plugins(self):
        """注册内置插件"""
        # 示例内置插件
        builtin_plugins = [
            BuiltinPluginDefinition(
                name="core",
                description="核心功能插件",
                version="1.0.0",
                default_enabled=True
            ),
            BuiltinPluginDefinition(
                name="web_search",
                description="网络搜索插件",
                version="1.0.0",
                default_enabled=True
            ),
            BuiltinPluginDefinition(
                name="file_operations",
                description="文件操作插件",
                version="1.0.0",
                default_enabled=True
            )
        ]
        
        for plugin in builtin_plugins:
            self.builtin_plugins.append(plugin)
    
    def load_plugins(self) -> PluginLoadResult:
        """加载插件"""
        enabled = []
        disabled = []
        errors = []
        
        # 加载内置插件
        for plugin_def in self.builtin_plugins:
            try:
                if plugin_def.is_available and not plugin_def.is_available():
                    continue
                
                plugin = LoadedPlugin(
                    name=plugin_def.name,
                    manifest=PluginManifest(
                        name=plugin_def.name,
                        version=plugin_def.version or "1.0.0",
                        description=plugin_def.description,
                        author=PluginAuthor(name="Lengxiaobei Team")
                    ),
                    path="builtin",
                    source="builtin",
                    repository="builtin",
                    enabled=plugin_def.default_enabled,
                    is_builtin=True
                )
                
                if plugin.enabled:
                    enabled.append(plugin)
                else:
                    disabled.append(plugin)
                    
            except Exception as e:
                error = PluginError(
                    error_type="generic-error",
                    source="builtin",
                    plugin=plugin_def.name,
                    error=str(e)
                )
                errors.append(error)
        
        # 加载外部插件
        for plugin_dir in os.listdir(self.plugins_dir):
            plugin_path = os.path.join(self.plugins_dir, plugin_dir)
            if not os.path.isdir(plugin_path):
                continue
            
            try:
                manifest_path = os.path.join(plugin_path, "manifest.json")
                if not os.path.exists(manifest_path):
                    error = PluginError(
                        error_type="manifest-parse-error",
                        source="external",
                        plugin=plugin_dir,
                        manifest_path=manifest_path,
                        parseError="Manifest file not found"
                    )
                    errors.append(error)
                    continue
                
                # 读取清单
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest_data = json.load(f)
                
                manifest = PluginManifest(
                    name=manifest_data.get("name", plugin_dir),
                    version=manifest_data.get("version", "1.0.0"),
                    description=manifest_data.get("description", ""),
                    author=PluginAuthor(
                        name=manifest_data.get("author", {}).get("name", "Unknown"),
                        email=manifest_data.get("author", {}).get("email"),
                        url=manifest_data.get("author", {}).get("url")
                    )
                )
                
                plugin = LoadedPlugin(
                    name=manifest.name,
                    manifest=manifest,
                    path=plugin_path,
                    source="external",
                    repository="external",
                    enabled=manifest_data.get("enabled", True)
                )
                
                if plugin.enabled:
                    enabled.append(plugin)
                else:
                    disabled.append(plugin)
                    
            except Exception as e:
                error = PluginError(
                    error_type="generic-error",
                    source="external",
                    plugin=plugin_dir,
                    error=str(e)
                )
                errors.append(error)
        
        self.loaded_plugins = enabled + disabled
        self.plugin_errors = errors
        
        return PluginLoadResult(enabled, disabled, errors)
    
    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """获取插件"""
        for plugin in self.loaded_plugins:
            if plugin.name == name:
                return plugin
        return None
    
    def enable_plugin(self, name: str) -> bool:
        """启用插件"""
        plugin = self.get_plugin(name)
        if plugin:
            plugin.enabled = True
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """禁用插件"""
        plugin = self.get_plugin(name)
        if plugin:
            plugin.enabled = False
            return True
        return False
    
    def install_plugin(self, source: str, plugin_id: str) -> bool:
        """安装插件"""
        # TODO: 实现插件安装逻辑
        # 支持从GitHub、本地路径等安装
        return False
    
    def update_plugin(self, name: str) -> bool:
        """更新插件"""
        # TODO: 实现插件更新逻辑
        return False
    
    def uninstall_plugin(self, name: str) -> bool:
        """卸载插件"""
        # TODO: 实现插件卸载逻辑
        return False
    
    def get_available_plugins(self) -> List[LoadedPlugin]:
        """获取可用插件"""
        return [p for p in self.loaded_plugins if p.enabled]
    
    def get_plugin_components(self, component_type: str) -> List[Any]:
        """获取插件组件"""
        components = []
        
        for plugin in self.loaded_plugins:
            if not plugin.enabled:
                continue
            
            # 根据组件类型获取相应的组件
            if component_type == PluginComponent.COMMANDS:
                # TODO: 加载命令组件
                pass
            elif component_type == PluginComponent.SKILLS:
                # TODO: 加载技能组件
                pass
            elif component_type == PluginComponent.HOOKS:
                # TODO: 加载钩子组件
                pass
        
        return components
    
    def get_plugin_errors(self) -> List[PluginError]:
        """获取插件错误"""
        return self.plugin_errors
    
    def get_status(self) -> Dict[str, Any]:
        """获取插件系统状态"""
        return {
            'total_plugins': len(self.loaded_plugins),
            'enabled_plugins': len([p for p in self.loaded_plugins if p.enabled]),
            'disabled_plugins': len([p for p in self.loaded_plugins if not p.enabled]),
            'errors': len(self.plugin_errors),
            'plugins': [{
                'name': p.name,
                'version': p.manifest.version,
                'enabled': p.enabled,
                'is_builtin': p.is_builtin
            } for p in self.loaded_plugins]
        }


# ============================================================================# 便捷函数# ============================================================================

def create_plugin_manager(config: PluginConfig) -> PluginManager:
    """创建插件管理器"""
    return PluginManager(config)

def get_plugin_error_message(error: PluginError) -> str:
    """获取插件错误消息"""
    error_messages = {
        'generic-error': lambda e: e.error,
        'path-not-found': lambda e: f"Path not found: {e.path} ({e.component})",
        'git-auth-failed': lambda e: f"Git authentication failed ({e.authType}): {e.gitUrl}",
        'git-timeout': lambda e: f"Git {e.operation} timeout: {e.gitUrl}",
        'network-error': lambda e: f"Network error: {e.url}{f' - {e.details}' if e.details else ''}",
        'manifest-parse-error': lambda e: f"Manifest parse error: {e.parseError}",
        'manifest-validation-error': lambda e: f"Manifest validation failed: {', '.join(e.validationErrors)}",
        'plugin-not-found': lambda e: f"Plugin {e.pluginId} not found in marketplace {e.marketplace}",
        'marketplace-not-found': lambda e: f"Marketplace {e.marketplace} not found",
        'marketplace-load-failed': lambda e: f"Marketplace {e.marketplace} failed to load: {e.reason}",
        'mcp-config-invalid': lambda e: f"MCP server {e.serverName} invalid: {e.validationError}",
        'hook-load-failed': lambda e: f"Hook load failed: {e.reason}",
        'component-load-failed': lambda e: f"{e.component} load failed from {e.path}: {e.reason}"
    }
    
    if error.type in error_messages:
        return error_messages[error.type](error)
    else:
        return f"Unknown error: {error.type}"
