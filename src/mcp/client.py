"""
MCP (Model Control Protocol) 客户端
====================================
核心功能：
- 连接到 MCP 服务器
- 发送和接收消息
- 管理连接状态
- 处理认证
"""

from typing import Dict, Any, Optional

from .types import McpServerConfig
from .transports import (
    StdioTransportHandler,
    SseTransportHandler,
    HttpTransportHandler,
    WebSocketTransportHandler,
    SdkTransportHandler
)


# ============================================================================# MCP客户端# ============================================================================

class MCPClient:
    """
    MCP客户端
    功能：
    1. 连接到MCP服务器
    2. 发送和接收消息
    3. 管理连接状态
    4. 处理认证
    """
    
    def __init__(self, config: McpServerConfig):
        self.config = config
        self.connected = False
        self.transport_handler = self._create_transport_handler(config)
    
    def _create_transport_handler(self, config: McpServerConfig):
        """根据配置创建相应的传输处理器"""
        from .types import (
            McpStdioServerConfig,
            McpSSEServerConfig,
            McpHTTPServerConfig,
            McpWebSocketServerConfig,
            McpSdkServerConfig
        )
        
        if isinstance(config, McpStdioServerConfig):
            return StdioTransportHandler(config)
        elif isinstance(config, McpSSEServerConfig):
            return SseTransportHandler(config)
        elif isinstance(config, McpHTTPServerConfig):
            return HttpTransportHandler(config)
        elif isinstance(config, McpWebSocketServerConfig):
            return WebSocketTransportHandler(config)
        elif isinstance(config, McpSdkServerConfig):
            return SdkTransportHandler(config)
        else:
            raise ValueError(f"Unsupported config type: {type(config)}")
    
    async def connect(self) -> bool:
        """连接到服务器"""
        try:
            await self.transport_handler.connect()
            self.connected = True
            return True
        except Exception as e:
            print(f"[MCP] 连接失败: {e}")
            self.connected = False
            return False
    
    async def send(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发送消息"""
        if not self.connected:
            return None
        
        try:
            return await self.transport_handler.send(message)
        except Exception as e:
            print(f"[MCP] 发送消息失败: {e}")
            return None
    
    async def disconnect(self):
        """断开连接"""
        await self.transport_handler.disconnect()
        self.connected = False
