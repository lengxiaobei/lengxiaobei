"""
MCP (Model Control Protocol) 类型定义
====================================
核心功能：
- 定义 MCP 协议的各种类型
- 服务器配置类
- 服务器连接状态类
- 配置作用域和传输方式枚举
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, AsyncGenerator, Union
from enum import Enum


# ============================================================================# 配置类型定义# ============================================================================

class ConfigScope(Enum):
    """配置作用域"""
    LOCAL = "local"
    USER = "user"
    PROJECT = "project"
    DYNAMIC = "dynamic"
    ENTERPRISE = "enterprise"
    CLAUDEAI = "claudeai"
    MANAGED = "managed"


class Transport(Enum):
    """传输方式"""
    STDIO = "stdio"
    SSE = "sse"
    SSE_IDE = "sse-ide"
    HTTP = "http"
    WS = "ws"
    SDK = "sdk"


# ============================================================================# 服务器配置类# ============================================================================

@dataclass(kw_only=True)
class McpServerConfigBase:
    """服务器配置基类"""
    type: str


@dataclass(kw_only=True)
class McpStdioServerConfig(McpServerConfigBase):
    """Stdio服务器配置"""
    type: str = "stdio"
    command: str  # 命令
    args: List[str] = field(default_factory=list)  # 参数
    env: Optional[Dict[str, str]] = None  # 环境变量


@dataclass(kw_only=True)
class McpHttpBasedServerConfig(McpServerConfigBase):
    """基于HTTP的服务器配置基类"""
    url: str  # URL
    headers: Optional[Dict[str, str]] = None  # 头信息
    headers_helper: Optional[str] = None  # 头信息助手
    oauth: Optional[Dict[str, Any]] = None  # OAuth配置


@dataclass(kw_only=True)
class McpSSEServerConfig(McpHttpBasedServerConfig):
    """SSE服务器配置"""
    type: str = "sse"


@dataclass(kw_only=True)
class McpHTTPServerConfig(McpHttpBasedServerConfig):
    """HTTP服务器配置"""
    type: str = "http"


@dataclass(kw_only=True)
class McpWebSocketServerConfig(McpHttpBasedServerConfig):
    """WebSocket服务器配置"""
    type: str = "ws"
    oauth: Optional[Dict[str, Any]] = None  # WebSocket通常不需要OAuth


@dataclass(kw_only=True)
class McpSdkServerConfig(McpServerConfigBase):
    """SDK服务器配置"""
    type: str = "sdk"
    name: str  # 名称


# 服务器配置联合类型
McpServerConfig = Union[
    McpStdioServerConfig,
    McpSSEServerConfig,
    McpHTTPServerConfig,
    McpWebSocketServerConfig,
    McpSdkServerConfig
]


@dataclass
class ScopedMcpServerConfig:
    """带作用域的服务器配置"""
    config: McpServerConfig
    scope: ConfigScope
    plugin_source: Optional[str] = None  # 插件来源


# ============================================================================# 服务器连接状态# ============================================================================

class ServerConnectionType(Enum):
    """服务器连接类型"""
    CONNECTED = "connected"
    FAILED = "failed"
    NEEDS_AUTH = "needs-auth"
    PENDING = "pending"
    DISABLED = "disabled"


@dataclass(kw_only=True)
class BaseMCPServer:
    """MCP服务器基类"""
    name: str
    type: str
    config: ScopedMcpServerConfig  # 配置


@dataclass(kw_only=True)
class ConnectedMCPServer(BaseMCPServer):
    """已连接的MCP服务器"""
    type: str = "connected"
    client: Any  # 客户端实例
    capabilities: Dict[str, Any]  # 服务器能力
    server_info: Optional[Dict[str, str]] = None  # 服务器信息
    instructions: Optional[str] = None  # 指令
    cleanup: Callable[[], AsyncGenerator[None, None]]  # 清理函数


@dataclass(kw_only=True)
class FailedMCPServer(BaseMCPServer):
    """失败的MCP服务器"""
    type: str = "failed"
    error: Optional[str] = None  # 错误信息


@dataclass(kw_only=True)
class NeedsAuthMCPServer(BaseMCPServer):
    """需要认证的MCP服务器"""
    type: str = "needs-auth"


@dataclass(kw_only=True)
class PendingMCPServer(BaseMCPServer):
    """待处理的MCP服务器"""
    type: str = "pending"
    reconnect_attempt: Optional[int] = None  # 重连尝试次数
    max_reconnect_attempts: Optional[int] = None  # 最大重连尝试次数


@dataclass(kw_only=True)
class DisabledMCPServer(BaseMCPServer):
    """禁用的MCP服务器"""
    type: str = "disabled"


# 服务器连接联合类型
MCPServerConnection = Union[
    ConnectedMCPServer,
    FailedMCPServer,
    NeedsAuthMCPServer,
    PendingMCPServer,
    DisabledMCPServer
]
