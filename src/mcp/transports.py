"""
MCP (Model Control Protocol) 传输协议处理器
====================================
核心功能：
- 实现各种传输协议的处理器
- 支持 stdio、HTTP、SSE、WebSocket 等传输方式
- 提供统一的连接、发送和断开接口
"""

import os
import json
import asyncio
import subprocess
from typing import Dict, Any, Optional

# 可选导入
try:
    import aiohttp
except ImportError:
    aiohttp = None

from .types import (
    McpServerConfig,
    McpStdioServerConfig,
    McpHttpBasedServerConfig,
    McpSSEServerConfig,
    McpHTTPServerConfig,
    McpWebSocketServerConfig,
    McpSdkServerConfig
)


# ============================================================================# 传输协议处理器基类# ============================================================================

class BaseTransportHandler:
    """传输协议处理器基类"""
    
    def __init__(self, config: McpServerConfig):
        self.config = config
    
    async def connect(self):
        """建立连接"""
        raise NotImplementedError
    
    async def send(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        raise NotImplementedError
    
    async def disconnect(self):
        """断开连接"""
        raise NotImplementedError


class StdioTransportHandler(BaseTransportHandler):
    """Stdio传输协议处理器"""
    
    def __init__(self, config: McpStdioServerConfig):
        super().__init__(config)
        self.process = None
    
    async def connect(self):
        """建立连接"""
        env = self.config.env or os.environ.copy()
        self.process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    async def send(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        if not self.process:
            return {"error": "Not connected"}
        
        # 检查子进程是否还在运行
        if self.process.returncode is not None:
            return {"error": "Subprocess has terminated unexpectedly"}
        
        try:
            # 发送消息
            message_str = json.dumps(message) + '\n'
            self.process.stdin.write(message_str.encode())
            await self.process.stdin.drain()
            
            # 读取响应 - 添加超时机制
            try:
                response = await asyncio.wait_for(self.process.stdout.readline(), timeout=30.0)
                return json.loads(response.decode())
            except asyncio.TimeoutError:
                print("[MCP] Stdio读取响应超时")
                return {"error": "Read response timeout"}
        except Exception as e:
            print(f"[MCP] Stdio通信失败: {e}")
            return {"error": f"Communication failed: {str(e)}"}
    
    async def disconnect(self):
        """断开连接"""
        if self.process:
            # 检查子进程是否还在运行
            if self.process.returncode is None:
                try:
                    self.process.terminate()
                    await self.process.wait()
                except ProcessLookupError:
                    # 进程可能已经终止
                    pass
                except Exception as e:
                    print(f"[MCP] 终止子进程时出错: {e}")


class HttpBasedTransportHandler(BaseTransportHandler):
    """基于HTTP的传输协议处理器基类"""
    
    def __init__(self, config: McpHttpBasedServerConfig):
        super().__init__(config)
        self.session = None
    
    async def connect(self):
        """建立连接"""
        if aiohttp is None:
            raise ImportError("aiohttp is required for HTTP-based transports")
        self.session = aiohttp.ClientSession()
    
    async def disconnect(self):
        """断开连接"""
        if self.session:
            await self.session.close()


class HttpTransportHandler(HttpBasedTransportHandler):
    """HTTP传输协议处理器"""
    
    async def send(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        if not self.session:
            return {"error": "Not connected"}
        
        async with self.session.post(
            self.config.url,
            json=message,
            headers=self.config.headers
        ) as response:
            return await response.json()


class SseTransportHandler(HttpBasedTransportHandler):
    """SSE传输协议处理器"""
    
    async def send(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        if not self.session:
            return {"error": "Not connected"}
        
        async with self.session.post(
            self.config.url,
            json=message,
            headers=self.config.headers
        ) as response:
            return await response.json()


class WebSocketTransportHandler(HttpBasedTransportHandler):
    """WebSocket传输协议处理器"""
    
    async def send(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        if not self.session:
            return {"error": "Not connected"}
        
        async with self.session.ws_connect(
            self.config.url,
            headers=self.config.headers
        ) as ws:
            await ws.send_json(message)
            response = await ws.receive_json()
            return response


class SdkTransportHandler(BaseTransportHandler):
    """SDK传输协议处理器"""
    
    def __init__(self, config: McpSdkServerConfig):
        super().__init__(config)
        self.client = None
    
    async def connect(self):
        """建立连接"""
        # 实现SDK连接逻辑
        pass
    
    async def send(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息"""
        # 实现SDK发送逻辑
        return {"error": "Not implemented"}
    
    async def disconnect(self):
        """断开连接"""
        # 实现SDK断开逻辑
        pass
