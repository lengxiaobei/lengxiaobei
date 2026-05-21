"""
MCP (Model Control Protocol) 协议 — 照帮 Claude Code 设计
====================================
核心功能：
- 与外部服务器通信的标准协议
- 支持多种传输方式：stdio、SSE、HTTP、WebSocket
- 服务器连接管理
- 资源管理和认证授权
- 扩展系统能力，连接外部服务
"""

# 导入 mcp 包中的所有内容
from .mcp import *

# 为了兼容性，创建别名
