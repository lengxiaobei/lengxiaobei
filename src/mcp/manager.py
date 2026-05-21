"""
MCP (Model Control Protocol) 连接管理器
====================================
核心功能：
- 管理多个 MCP 服务器连接
- 处理服务器的连接、断开和重连
- 提供统一的接口访问服务器资源
- 管理服务器的认证状态
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from .types import (
    McpServerConfig,
    ScopedMcpServerConfig,
    MCPServerConnection,
    ConnectedMCPServer,
    FailedMCPServer,
    PendingMCPServer,
    ConfigScope
)
from .client import MCPClient
from .config import ConfigParser, ConfigSerializer


# ============================================================================# MCP服务器管理器# ============================================================================

class MCPConnectionManager:
    """
    MCP连接管理器
    功能：
    1. 管理多个MCP服务器连接
    2. 处理服务器的连接、断开和重连
    3. 提供统一的接口访问服务器资源
    4. 管理服务器的认证状态
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.mcp_dir = self.project_root / "mcp"
        self.mcp_dir.mkdir(exist_ok=True)
        
        # 服务器连接存储
        self.connections: Dict[str, MCPServerConnection] = {}
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        """加载MCP配置"""
        config_file = self.mcp_dir / "mcp_config.json"
        if not config_file.exists():
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            for name, server_config in config.get("mcpServers", {}).items():
                # 解析服务器配置
                parsed_config = ConfigParser.parse_server_config(server_config)
                if parsed_config:
                    # 创建作用域配置
                    scoped_config = ScopedMcpServerConfig(
                        config=parsed_config,
                        scope=ConfigScope.LOCAL
                    )
                    
                    # 创建待处理连接
                    self.connections[name] = PendingMCPServer(
                        name=name,
                        config=scoped_config
                    )
        except Exception as e:
            print(f"[MCP] 加载配置失败: {e}")
    
    async def connect_server(self, name: str) -> bool:
        """连接服务器"""
        if not self._validate_server_exists(name):
            print(f"[MCP] 服务器不存在: {name}")
            return False
        
        connection = self.connections[name]
        if not self._is_pending_server(connection):
            print(f"[MCP] 服务器状态不正确: {connection.type}")
            return False
        
        # 创建客户端
        client = self._create_client(connection.config.config)
        
        # 连接
        if not await client.connect():
            self._update_connection_to_failed(name, connection, "连接失败")
            return False
        
        # 测试连接
        if not await self._test_connection(client):
            return False
        
        # 获取服务器能力
        capabilities = await self._get_server_capabilities(client)
        
        # 创建已连接状态
        cleanup_func = self._create_cleanup_function(client)
        
        self.connections[name] = ConnectedMCPServer(
            name=name,
            client=client,
            capabilities=capabilities,
            config=connection.config,
            cleanup=cleanup_func
        )
        
        print(f"[MCP] 服务器连接成功: {name}")
        return True
    
    def _create_client(self, config: McpServerConfig) -> MCPClient:
        """创建MCP客户端实例"""
        return MCPClient(config)
    
    def _update_connection_to_failed(self, name: str, connection: MCPServerConnection, error_msg: str):
        """更新连接状态为失败"""
        from .types import FailedMCPServer
        
        self.connections[name] = FailedMCPServer(
            name=name,
            config=connection.config,
            error=error_msg
        )
    
    def _create_cleanup_function(self, client: MCPClient):
        """创建清理函数"""
        async def cleanup():
            await client.disconnect()
        return cleanup
    
    async def _test_connection(self, client: MCPClient) -> bool:
        """测试客户端连接"""
        test_response = await client.send({"type": "ping"})
        if not test_response or "error" in test_response:
            return False
        return True
    
    async def _get_server_capabilities(self, client: MCPClient) -> Dict[str, Any]:
        """获取服务器能力"""
        capabilities_response = await client.send({"type": "get_capabilities"})
        return capabilities_response.get("capabilities", {}) if capabilities_response else {}
    
    async def disconnect_server(self, name: str):
        """断开服务器连接"""
        if not self._validate_server_exists(name):
            return
        
        connection = self.connections[name]
        if self._is_connected_server(connection):
            await connection.cleanup()
        
        # 改为待处理状态
        from .types import PendingMCPServer
        
        self.connections[name] = PendingMCPServer(
            name=name,
            config=connection.config
        )
    
    async def send_to_server(self, name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """向服务器发送消息"""
        if not self._validate_server_exists(name):
            return None
        
        connection = self.connections[name]
        if not self._is_connected_server(connection):
            return None
        
        # 检查并处理stdio连接状态
        status_check_result = await self._check_stdio_connection_status(name, connection)
        if status_check_result is not None:
            return status_check_result
        
        result = await connection.client.send(message)
        
        # 如果发送失败且是stdio连接，检查子进程状态
        if result and "error" in result and "terminated" in result["error"]:
            from .types import McpStdioServerConfig
            
            if isinstance(connection.client.config, McpStdioServerConfig):
                self._update_connection_to_failed(name, connection, result["error"])
        
        return result
    
    async def _check_stdio_connection_status(self, name: str, connection: ConnectedMCPServer) -> Optional[Dict[str, Any]]:
        """检查stdio连接状态，如果子进程已退出则更新连接状态"""
        from .types import McpStdioServerConfig
        
        if isinstance(connection.client.config, McpStdioServerConfig):
            if connection.client.transport_handler.process and connection.client.transport_handler.process.returncode is not None:
                print(f"[MCP] 子进程 {name} 已退出，错误码: {connection.client.transport_handler.process.returncode}")
                # 将连接状态改为失败
                self._update_connection_to_failed(
                    name, 
                    connection, 
                    f"Subprocess exited with code {connection.client.transport_handler.process.returncode}"
                )
                return None
        return None
    
    def list_servers(self) -> List[str]:
        """列出所有服务器"""
        return list(self.connections.keys())
    
    def get_server_status(self, name: str) -> Optional[str]:
        """获取服务器状态"""
        if not self._validate_server_exists(name):
            return None
        return self.connections[name].type
    
    def add_server(self, name: str, config: McpServerConfig, scope: ConfigScope = ConfigScope.LOCAL):
        """添加服务器"""
        scoped_config = ScopedMcpServerConfig(
            config=config,
            scope=scope
        )
        
        from .types import PendingMCPServer
        
        self.connections[name] = PendingMCPServer(
            name=name,
            config=scoped_config
        )
        
        self._save_config()
    
    def remove_server(self, name: str):
        """移除服务器"""
        if name in self.connections:
            del self.connections[name]
            self._save_config()
    
    def _save_config(self):
        """保存配置"""
        config = {"mcpServers": {}}
        
        for name, connection in self.connections.items():
            server_config = connection.config.config
            config_dict = ConfigSerializer.serialize_server_config(server_config)
            if config_dict:
                config["mcpServers"][name] = config_dict
        
        config_file = self.mcp_dir / "mcp_config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def _validate_server_exists(self, name: str) -> bool:
        """验证服务器是否存在"""
        return name in self.connections

    def _is_connected_server(self, connection: MCPServerConnection) -> bool:
        """检查是否为已连接的服务器"""
        return isinstance(connection, ConnectedMCPServer)

    def _is_pending_server(self, connection: MCPServerConnection) -> bool:
        """检查是否为待处理的服务器"""
        return isinstance(connection, PendingMCPServer)
