"""
MCP (Model Control Protocol) 配置解析器
====================================
核心功能：
- 解析和序列化 MCP 服务器配置
- 提供配置文件的加载和保存功能
- 支持不同类型的服务器配置
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from .types import (
    McpServerConfig,
    McpStdioServerConfig,
    McpSSEServerConfig,
    McpHTTPServerConfig,
    McpWebSocketServerConfig,
    McpSdkServerConfig
)


# ============================================================================# 配置解析器# ============================================================================

class ConfigParser:
    """配置解析器"""
    
    @staticmethod
    def parse_server_config(server_config: dict) -> Optional[McpServerConfig]:
        """解析服务器配置字典为对应的配置对象"""
        server_type = server_config.get("type", "stdio")
        
        config_mapping = {
            "stdio": ConfigParser._create_stdio_config,
            "sse": ConfigParser._create_sse_config,
            "http": ConfigParser._create_http_config,
            "ws": ConfigParser._create_websocket_config,
            "sdk": ConfigParser._create_sdk_config
        }
        
        if server_type in config_mapping:
            return config_mapping[server_type](server_config)
        else:
            return None
    
    @staticmethod
    def _create_stdio_config(server_config: dict) -> McpStdioServerConfig:
        """创建Stdio服务器配置"""
        return McpStdioServerConfig(
            command=server_config.get("command"),
            args=server_config.get("args", []),
            env=server_config.get("env")
        )
    
    @staticmethod
    def _create_sse_config(server_config: dict) -> McpSSEServerConfig:
        """创建SSE服务器配置"""
        return McpSSEServerConfig(
            url=server_config.get("url"),
            headers=server_config.get("headers"),
            headers_helper=server_config.get("headersHelper"),
            oauth=server_config.get("oauth")
        )
    
    @staticmethod
    def _create_http_config(server_config: dict) -> McpHTTPServerConfig:
        """创建HTTP服务器配置"""
        return McpHTTPServerConfig(
            url=server_config.get("url"),
            headers=server_config.get("headers"),
            headers_helper=server_config.get("headersHelper"),
            oauth=server_config.get("oauth")
        )
    
    @staticmethod
    def _create_websocket_config(server_config: dict) -> McpWebSocketServerConfig:
        """创建WebSocket服务器配置"""
        return McpWebSocketServerConfig(
            url=server_config.get("url"),
            headers=server_config.get("headers"),
            headers_helper=server_config.get("headersHelper")
        )
    
    @staticmethod
    def _create_sdk_config(server_config: dict) -> McpSdkServerConfig:
        """创建SDK服务器配置"""
        return McpSdkServerConfig(
            name=server_config.get("name")
        )


class ConfigSerializer:
    """配置序列化器"""
    
    @staticmethod
    def serialize_server_config(server_config: McpServerConfig) -> Optional[dict]:
        """将服务器配置对象序列化为字典"""
        config_mapping = {
            McpStdioServerConfig: ConfigSerializer._serialize_stdio_config,
            McpSSEServerConfig: ConfigSerializer._serialize_sse_config,
            McpHTTPServerConfig: ConfigSerializer._serialize_http_config,
            McpWebSocketServerConfig: ConfigSerializer._serialize_websocket_config,
            McpSdkServerConfig: ConfigSerializer._serialize_sdk_config
        }
        
        config_type = type(server_config)
        if config_type in config_mapping:
            return config_mapping[config_type](server_config)
        else:
            return None
    
    @staticmethod
    def _serialize_stdio_config(server_config: McpStdioServerConfig) -> dict:
        """序列化Stdio服务器配置"""
        return {
            "type": "stdio",
            "command": server_config.command,
            "args": server_config.args,
            "env": server_config.env
        }
    
    @staticmethod
    def _serialize_sse_config(server_config: McpSSEServerConfig) -> dict:
        """序列化SSE服务器配置"""
        return {
            "type": "sse",
            "url": server_config.url,
            "headers": server_config.headers,
            "headersHelper": server_config.headers_helper,
            "oauth": server_config.oauth
        }
    
    @staticmethod
    def _serialize_http_config(server_config: McpHTTPServerConfig) -> dict:
        """序列化HTTP服务器配置"""
        return {
            "type": "http",
            "url": server_config.url,
            "headers": server_config.headers,
            "headersHelper": server_config.headers_helper,
            "oauth": server_config.oauth
        }
    
    @staticmethod
    def _serialize_websocket_config(server_config: McpWebSocketServerConfig) -> dict:
        """序列化WebSocket服务器配置"""
        return {
            "type": "ws",
            "url": server_config.url,
            "headers": server_config.headers,
            "headersHelper": server_config.headers_helper
        }
    
    @staticmethod
    def _serialize_sdk_config(server_config: McpSdkServerConfig) -> dict:
        """序列化SDK服务器配置"""
        return {
            "type": "sdk",
            "name": server_config.name
        }
