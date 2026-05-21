"""
MCP (Model Control Protocol) 协议包
====================================
核心功能：
- 与外部服务器通信的标准协议
- 支持多种传输方式：stdio、SSE、HTTP、WebSocket
- 服务器连接管理
- 资源管理和认证授权
- 扩展系统能力，连接外部服务
"""

from .types import (
    ConfigScope,
    Transport,
    McpServerConfigBase,
    McpStdioServerConfig,
    McpHttpBasedServerConfig,
    McpSSEServerConfig,
    McpHTTPServerConfig,
    McpWebSocketServerConfig,
    McpSdkServerConfig,
    McpServerConfig,
    ScopedMcpServerConfig,
    ServerConnectionType,
    BaseMCPServer,
    ConnectedMCPServer,
    FailedMCPServer,
    NeedsAuthMCPServer,
    PendingMCPServer,
    DisabledMCPServer,
    MCPServerConnection
)

from .transports import (
    BaseTransportHandler,
    StdioTransportHandler,
    HttpBasedTransportHandler,
    HttpTransportHandler,
    SseTransportHandler,
    WebSocketTransportHandler,
    SdkTransportHandler
)

from .config import ConfigParser, ConfigSerializer
from .client import MCPClient
from .manager import MCPConnectionManager

__all__ = [
    # Types
    "ConfigScope",
    "Transport",
    "McpServerConfigBase",
    "McpStdioServerConfig",
    "McpHttpBasedServerConfig",
    "McpSSEServerConfig",
    "McpHTTPServerConfig",
    "McpWebSocketServerConfig",
    "McpSdkServerConfig",
    "McpServerConfig",
    "ScopedMcpServerConfig",
    "ServerConnectionType",
    "BaseMCPServer",
    "ConnectedMCPServer",
    "FailedMCPServer",
    "NeedsAuthMCPServer",
    "PendingMCPServer",
    "DisabledMCPServer",
    "MCPServerConnection",
    
    # Transports
    "BaseTransportHandler",
    "StdioTransportHandler",
    "HttpBasedTransportHandler",
    "HttpTransportHandler",
    "SseTransportHandler",
    "WebSocketTransportHandler",
    "SdkTransportHandler",
    
    # Config
    "ConfigParser",
    "ConfigSerializer",
    
    # Client
    "MCPClient",
    
    # Manager
    "MCPConnectionManager",
    
    # Convenience functions
    "create_mcp_manager"
]


def create_mcp_manager(project_root: str) -> MCPConnectionManager:
    """创建MCP连接管理器"""
    return MCPConnectionManager(project_root)
