"""
LSP (Language Server Protocol) 集成 — 照搬 Claude Code 设计
====================================
核心功能：
- 语言服务器管理
- 插件LSP配置加载
- 环境变量解析
- 服务器作用域管理
- LSP错误处理
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional


# ============================================================================# 类型定义# ============================================================================

class LspServerConfig:
    """LSP服务器配置"""
    def __init__(self, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None, workspace_folder: Optional[str] = None,
                 initialization_options: Optional[Dict[str, Any]] = None):
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.workspace_folder = workspace_folder
        self.initialization_options = initialization_options or {}

class ScopedLspServerConfig(LspServerConfig):
    """带作用域的LSP服务器配置"""
    def __init__(self, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None, workspace_folder: Optional[str] = None,
                 initialization_options: Optional[Dict[str, Any]] = None,
                 scope: str = "dynamic", source: str = ""):
        super().__init__(command, args, env, workspace_folder, initialization_options)
        self.scope = scope
        self.source = source


# ============================================================================# LSP管理器# ============================================================================

class LspManager:
    """
    LSP管理器
    功能：
    1. 管理语言服务器的配置和启动
    2. 加载插件的LSP配置
    3. 解析环境变量
    4. 处理LSP服务器的作用域
    """
    
    def __init__(self, config):
        """初始化LSP管理器"""
        self.config = config
        self.servers: Dict[str, ScopedLspServerConfig] = {}
        self.running_servers: Dict[str, Any] = {}
    
    def load_plugin_lsp_servers(self, plugin) -> Optional[Dict[str, LspServerConfig]]:
        """加载插件的LSP服务器配置"""
        servers = {}
        
        # 1. 检查插件目录中的 .lsp.json 文件
        lsp_json_path = os.path.join(plugin.path, ".lsp.json")
        if os.path.exists(lsp_json_path):
            try:
                with open(lsp_json_path, 'r', encoding='utf-8') as f:
                    lsp_data = json.load(f)
                
                for server_name, server_config in lsp_data.items():
                    config = LspServerConfig(
                        command=server_config.get("command"),
                        args=server_config.get("args"),
                        env=server_config.get("env"),
                        workspace_folder=server_config.get("workspaceFolder"),
                        initialization_options=server_config.get("initializationOptions")
                    )
                    servers[server_name] = config
                    
            except Exception as e:
                print(f"[LSP] Failed to load .lsp.json from plugin {plugin.name}: {e}")
        
        # 2. 检查插件清单中的 lspServers 字段
        if hasattr(plugin.manifest, 'lspServers') and plugin.manifest.lspServers:
            try:
                lsp_servers = plugin.manifest.lspServers
                
                if isinstance(lsp_servers, dict):
                    for server_name, server_config in lsp_servers.items():
                        config = LspServerConfig(
                            command=server_config.get("command"),
                            args=server_config.get("args"),
                            env=server_config.get("env"),
                            workspace_folder=server_config.get("workspaceFolder"),
                            initialization_options=server_config.get("initializationOptions")
                        )
                        servers[server_name] = config
                        
            except Exception as e:
                print(f"[LSP] Failed to load lspServers from plugin {plugin.name}: {e}")
        
        return servers if servers else None
    
    def resolve_plugin_lsp_environment(self, config: LspServerConfig, plugin) -> LspServerConfig:
        """解析插件LSP环境变量"""
        resolved_config = LspServerConfig(
            command=config.command,
            args=config.args.copy() if config.args else [],
            env=config.env.copy() if config.env else {},
            workspace_folder=config.workspace_folder,
            initialization_options=config.initialization_options.copy() if config.initialization_options else {}
        )
        
        # 解析命令路径
        if resolved_config.command:
            resolved_config.command = self._resolve_env_vars(resolved_config.command, plugin)
        
        # 解析参数
        if resolved_config.args:
            resolved_config.args = [self._resolve_env_vars(arg, plugin) for arg in resolved_config.args]
        
        # 解析环境变量
        resolved_env = {
            'LENGXIAOBEI_PLUGIN_ROOT': plugin.path,
            'LENGXIAOBEI_PLUGIN_DATA': os.path.join(self.config.project_root, "plugins", "data"),
            **(resolved_config.env or {})
        }
        for key, value in resolved_env.items():
            if key not in ['LENGXIAOBEI_PLUGIN_ROOT', 'LENGXIAOBEI_PLUGIN_DATA']:
                resolved_env[key] = self._resolve_env_vars(value, plugin)
        resolved_config.env = resolved_env
        
        # 解析工作区文件夹
        if resolved_config.workspace_folder:
            resolved_config.workspace_folder = self._resolve_env_vars(resolved_config.workspace_folder, plugin)
        
        return resolved_config
    
    def _resolve_env_vars(self, value: str, plugin) -> str:
        """解析环境变量"""
        # 替换插件特定变量
        value = value.replace("${LENGXIAOBEI_PLUGIN_ROOT}", plugin.path)
        value = value.replace("${LENGXIAOBEI_PLUGIN_DATA}", os.path.join(self.config.project_root, "plugins", "data"))
        
        # 替换系统环境变量
        for key, val in os.environ.items():
            value = value.replace(f"${{{key}}}", val)
        
        return value
    
    def add_plugin_scope_to_lsp_servers(self, servers: Dict[str, LspServerConfig], plugin_name: str) -> Dict[str, ScopedLspServerConfig]:
        """为LSP服务器添加插件作用域"""
        scoped_servers = {}
        
        for name, config in servers.items():
            # 添加插件前缀以避免冲突
            scoped_name = f"plugin:{plugin_name}:{name}"
            scoped_servers[scoped_name] = ScopedLspServerConfig(
                command=config.command,
                args=config.args,
                env=config.env,
                workspace_folder=config.workspace_folder,
                initialization_options=config.initialization_options,
                scope="dynamic",
                source=plugin_name
            )
        
        return scoped_servers
    
    def get_plugin_lsp_servers(self, plugin) -> Optional[Dict[str, ScopedLspServerConfig]]:
        """获取插件的LSP服务器"""
        if not plugin.enabled:
            return None
        
        # 加载服务器配置
        servers = self.load_plugin_lsp_servers(plugin)
        if not servers:
            return None
        
        # 解析环境变量
        resolved_servers = {}
        for name, config in servers.items():
            resolved_servers[name] = self.resolve_plugin_lsp_environment(config, plugin)
        
        # 添加插件作用域
        scoped_servers = self.add_plugin_scope_to_lsp_servers(resolved_servers, plugin.name)
        
        # 存储到全局服务器列表
        for name, server in scoped_servers.items():
            self.servers[name] = server
        
        return scoped_servers
    
    def extract_lsp_servers_from_plugins(self, plugins) -> Dict[str, ScopedLspServerConfig]:
        """从插件中提取所有LSP服务器"""
        all_servers = {}
        
        for plugin in plugins:
            if not plugin.enabled:
                continue
            
            servers = self.get_plugin_lsp_servers(plugin)
            if servers:
                all_servers.update(servers)
                print(f"[LSP] Loaded {len(servers)} LSP servers from plugin {plugin.name}")
        
        return all_servers
    
    def start_server(self, server_name: str) -> bool:
        """启动LSP服务器"""
        if server_name not in self.servers:
            return False
        
        server = self.servers[server_name]
        
        try:
            # TODO: 实现服务器启动逻辑
            # 这里需要使用 subprocess 启动服务器进程
            # 并建立与服务器的通信
            print(f"[LSP] Starting server: {server_name}")
            self.running_servers[server_name] = "running"  # 占位符
            return True
            
        except Exception as e:
            print(f"[LSP] Failed to start server {server_name}: {e}")
            return False
    
    def stop_server(self, server_name: str) -> bool:
        """停止LSP服务器"""
        if server_name not in self.running_servers:
            return False
        
        try:
            # TODO: 实现服务器停止逻辑
            print(f"[LSP] Stopping server: {server_name}")
            del self.running_servers[server_name]
            return True
            
        except Exception as e:
            print(f"[LSP] Failed to stop server {server_name}: {e}")
            return False
    
    def get_running_servers(self) -> List[str]:
        """获取运行中的服务器"""
        return list(self.running_servers.keys())
    
    def get_server_status(self, server_name: str) -> str:
        """获取服务器状态"""
        if server_name in self.running_servers:
            return self.running_servers[server_name]
        elif server_name in self.servers:
            return "stopped"
        else:
            return "not_found"
    
    def get_status(self) -> Dict[str, Any]:
        """获取LSP系统状态"""
        return {
            'total_servers': len(self.servers),
            'running_servers': len(self.running_servers),
            'servers': [{
                'name': name,
                'source': server.source,
                'status': self.get_server_status(name)
            } for name, server in self.servers.items()]
        }


# ============================================================================# 便捷函数# ============================================================================

def create_lsp_manager(config) -> LspManager:
    """创建LSP管理器"""
    return LspManager(config)


# 为了兼容性，创建别名
LanguageServerProtocol = LspManager
