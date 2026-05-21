#!/usr/bin/env python3
"""
冷小北 MCP 服务器
=================

实现 MCP (Model Context Protocol) 服务器，允许 Trae IDE 与冷小北集成
"""

import json
import sys
import asyncio
import logging
import os
from typing import Dict, Any, Optional

# 添加当前目录到 Python 路径
from .evolution.engine import AutonomousEvolutionEngine as EvolutionEngine
from .debug import debug_log


class MCPServer:
    """MCP 服务器"""
    
    def __init__(self):
        self.evolution_engine = EvolutionEngine()
        self.logger = logging.getLogger(__name__)
        self.running = False
    
    async def start(self):
        """启动 MCP 服务器"""
        self.running = True
        self.logger.info("MCP 服务器启动")
        await self._handle_stdin()
    
    async def stop(self):
        """停止 MCP 服务器"""
        self.running = False
        self.logger.info("MCP 服务器停止")
    
    async def _handle_stdin(self):
        """处理标准输入"""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        
        while self.running:
            try:
                line = await reader.readline()
                if not line:
                    break
                
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                
                await self._handle_request(line)
            except Exception as e:
                self.logger.error(f"处理请求时出错: {e}")
                await self._send_response({"error": str(e)})
    
    async def _handle_request(self, request_str: str):
        """处理 MCP 请求"""
        try:
            request = json.loads(request_str)
            
            # 验证请求格式
            if not isinstance(request, dict) or "id" not in request or "method" not in request:
                await self._send_response({
                    "error": "Invalid request format"
                })
                return
            
            method = request["method"]
            params = request.get("params", {})
            request_id = request["id"]
            
            # 处理不同的方法
            if method == "analyzeCode":
                await self._handle_analyze_code(request_id, params)
            elif method == "generateCode":
                await self._handle_generate_code(request_id, params)
            elif method == "optimizeArchitecture":
                await self._handle_optimize_architecture(request_id, params)
            elif method == "runEvolution":
                await self._handle_run_evolution(request_id, params)
            elif method == "health":
                await self._handle_health(request_id)
            elif method == "tools/list":
                await self._handle_tools_list(request_id, params)
            elif method == "initialize":
                await self._handle_initialize(request_id, params)
            else:
                await self._send_response({
                    "id": request_id,
                    "error": f"Unknown method: {method}"
                })
        except json.JSONDecodeError:
            await self._send_response({
                "error": "Invalid JSON format"
            })
        except Exception as e:
            self.logger.error(f"处理请求时出错: {e}")
            await self._send_response({
                "error": str(e)
            })
    
    async def _handle_analyze_code(self, request_id: str, params: Dict[str, Any]):
        """处理代码分析请求"""
        try:
            file_path = params.get("file")
            if not file_path:
                await self._send_response({
                    "id": request_id,
                    "error": "Missing file parameter"
                })
                return
            
            from .evolution.llm_client import generate_code as llm_generate_code

            result = llm_generate_code(f"分析以下代码:\n{file_path}")
            await self._send_response({
                "id": request_id,
                "result": result
            })
        except Exception as e:
            await self._send_response({
                "id": request_id,
                "error": str(e)
            })
    
    async def _handle_generate_code(self, request_id: str, params: Dict[str, Any]):
        """处理代码生成请求"""
        try:
            prompt = params.get("prompt")
            if not prompt:
                await self._send_response({
                    "id": request_id,
                    "error": "Missing prompt parameter"
                })
                return
            
            from .evolution.llm_client import generate_code as llm_generate_code

            result = llm_generate_code(prompt)
            await self._send_response({
                "id": request_id,
                "result": result
            })
        except Exception as e:
            await self._send_response({
                "id": request_id,
                "error": str(e)
            })
    
    async def _handle_optimize_architecture(self, request_id: str, params: Dict[str, Any]):
        """处理架构优化请求"""
        try:
            project_path = params.get("project")
            if not project_path:
                await self._send_response({
                    "id": request_id,
                    "error": "Missing project parameter"
                })
                return
            
            if hasattr(self.evolution_engine, 'evolve_autonomously'):
                result = self.evolution_engine.evolve_autonomously()
            else:
                result = {"status": "skipped", "message": "engine not available"}
            await self._send_response({
                "id": request_id,
                "result": result
            })
        except Exception as e:
            await self._send_response({
                "id": request_id,
                "error": str(e)
            })
    
    async def _handle_run_evolution(self, request_id: str, params: Dict[str, Any]):
        """处理进化请求"""
        try:
            project_path = params.get("project")
            if not project_path:
                await self._send_response({
                    "id": request_id,
                    "error": "Missing project parameter"
                })
                return
            
            if hasattr(self.evolution_engine, 'evolve_autonomously'):
                self.evolution_engine.evolve_autonomously()
                result = {"status": "triggered"}
            else:
                result = {"status": "skipped"}
            await self._send_response({
                "id": request_id,
                "result": result
            })
        except Exception as e:
            await self._send_response({
                "id": request_id,
                "error": str(e)
            })
    
    async def _handle_health(self, request_id: str):
        """处理健康检查请求"""
        await self._send_response({
            "id": request_id,
            "result": {
                "status": "healthy",
                "service": "lengxiaobei-mcp-server"
            }
        })
    
    async def _handle_initialize(self, request_id: str, params: Dict[str, Any]):
        """处理初始化请求"""
        await self._send_response({
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {
                        "list": True,
                        "call": True
                    },
                    "notifications": {
                        "listChanged": True,
                        "logging": True
                    }
                },
                "serverInfo": {
                    "name": "lengxiaobei-mcp-server",
                    "version": "1.0.0"
                }
            }
        })
        
        # 发送 initialized 通知
        await self._send_notification({
            "method": "initialized",
            "params": {}
        })
    
    async def _handle_tools_list(self, request_id: str, params: Dict[str, Any]):
        """处理工具列表请求"""
        tools = [
            {
                "name": "analyzeCode",
                "title": "分析代码",
                "description": "分析代码文件，识别结构和潜在问题",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "要分析的文件路径"
                        }
                    },
                    "required": ["file"]
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "success": {
                            "type": "boolean"
                        },
                        "message": {
                            "type": "string"
                        },
                        "analysis": {
                            "type": "object"
                        }
                    }
                }
            },
            {
                "name": "generateCode",
                "title": "生成代码",
                "description": "根据提示生成代码",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "代码生成提示"
                        }
                    },
                    "required": ["prompt"]
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "success": {
                            "type": "boolean"
                        },
                        "message": {
                            "type": "string"
                        },
                        "code": {
                            "type": "string"
                        }
                    }
                }
            },
            {
                "name": "optimizeArchitecture",
                "title": "优化架构",
                "description": "分析项目架构并提供优化建议",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "项目路径"
                        }
                    },
                    "required": ["project"]
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "success": {
                            "type": "boolean"
                        },
                        "message": {
                            "type": "string"
                        },
                        "recommendations": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    }
                }
            },
            {
                "name": "runEvolution",
                "title": "运行进化",
                "description": "运行代码进化过程，自动改进代码",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "项目路径"
                        }
                    },
                    "required": ["project"]
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "success": {
                            "type": "boolean"
                        },
                        "message": {
                            "type": "string"
                        },
                        "changes": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    }
                }
            }
        ]
        
        await self._send_response({
            "id": request_id,
            "result": {
                "tools": tools,
                "total": len(tools),
                "page": 1,
                "pageSize": len(tools)
            }
        })
    
    async def _send_response(self, response: Dict[str, Any]):
        """发送响应"""
        try:
            # 添加 JSON-RPC 2.0 规范要求的字段
            if "jsonrpc" not in response:
                response["jsonrpc"] = "2.0"
            response_str = json.dumps(response) + "\n"
            sys.stdout.write(response_str)
            sys.stdout.flush()
        except Exception as e:
            self.logger.error(f"发送响应时出错: {e}")
    
    async def _send_notification(self, notification: Dict[str, Any]):
        """发送通知"""
        try:
            # 添加 JSON-RPC 2.0 规范要求的字段
            if "jsonrpc" not in notification:
                notification["jsonrpc"] = "2.0"
            notification_str = json.dumps(notification) + "\n"
            sys.stdout.write(notification_str)
            sys.stdout.flush()
        except Exception as e:
            self.logger.error(f"发送通知时出错: {e}")


def main():
    """主函数"""
    # 配置日志
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    server = MCPServer()
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("MCP 服务器被中断")
    finally:
        asyncio.run(server.stop())


if __name__ == '__main__':
    main()
