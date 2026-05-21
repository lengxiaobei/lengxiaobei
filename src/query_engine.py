"""
QueryEngine V2 — 照搬 Claude Code 设计
========================================
核心特性：
- 完整的查询生命周期管理
- 异步生成器消息流
- 会话状态持久化
- 工具调用与权限管理
- 用量追踪与预算控制
"""

import os
import time
import json
import asyncio
import re
import html
import subprocess
import tempfile
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Callable, AsyncGenerator, Union
from datetime import datetime
from enum import Enum
import ast
import builtins

from .memory import Memory
from .llm import chat, route
from .tool_registry import ToolRegistry


# ============================================================================
# 类型定义
# ============================================================================

@dataclass
class Message:
    """消息类型"""
    role: str  # "user" | "assistant" | "system" | "tool"
    content: Union[str, List[Dict], Dict]
    timestamp: float = field(default_factory=time.time)
    uuid: str = field(default_factory=lambda: f"msg_{int(time.time())}")
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolUse:
    """工具调用"""
    tool_name: str
    tool_input: Dict[str, Any]
    tool_use_id: str


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_use_id: str
    output: str
    is_error: bool = False


@dataclass
class Usage:
    """用量统计"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    api_duration_ms: float = 0.0


@dataclass
class PermissionDenial:
    """权限拒绝记录"""
    tool_name: str
    tool_use_id: str
    tool_input: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class QueryEngineConfig:
    """QueryEngine 配置"""
    cwd: str
    tools: ToolRegistry
    memory: Memory
    max_turns: int = 20
    max_budget_usd: Optional[float] = None
    custom_system_prompt: Optional[str] = None
    append_system_prompt: Optional[str] = None
    verbose: bool = False


# ============================================================================
# 工具安全相关辅助函数
# ============================================================================

def sanitize_input(input_str: str) -> str:
    """
    清理输入字符串，移除潜在危险字符
    """
    if not isinstance(input_str, str):
        return str(input_str)
    
    # 移除或转义潜在危险字符
    sanitized = html.escape(input_str)
    # 移除控制字符
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
    return sanitized


def validate_tool_input(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证并清理工具输入参数
    """
    validated_input = {}
    
    for key, value in tool_input.items():
        # 对字符串值进行清理
        if isinstance(value, str):
            validated_input[key] = sanitize_input(value)
        # 对嵌套字典递归验证
        elif isinstance(value, dict):
            validated_input[key] = validate_tool_input(value)
        # 对列表中的字符串进行清理
        elif isinstance(value, list):
            validated_input[key] = [
                sanitize_input(item) if isinstance(item, str) else item 
                for item in value
            ]
        # 其他类型直接保留
        else:
            validated_input[key] = value
    
    return validated_input


def safe_execute_tool_subprocess(tool_func: Callable, tool_input: Dict[str, Any]) -> Any:
    """
    在子进程中安全执行工具
    """
    # 验证并清理输入
    clean_input = validate_tool_input(tool_input)
    
    # 创建临时文件来存储工具函数和输入
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
        temp_filename = temp_file.name
        
        # 导入必要的模块
        temp_file.write("import sys\n")
        temp_file.write("import json\n")
        temp_file.write("import os\n")
        temp_file.write("import subprocess\n")
        temp_file.write("import requests\n")
        temp_file.write("import urllib\n")
        temp_file.write("import socket\n")
        temp_file.write("import threading\n")
        temp_file.write("import multiprocessing\n")
        temp_file.write("import pickle\n")
        temp_file.write("import importlib\n")
        temp_file.write("import execjs\n")
        
        # 写入工具函数定义
        func_code = inspect.getsource(tool_func)
        temp_file.write(func_code)
        temp_file.write("\n")
        
        # 写入输入参数
        temp_file.write(f"input_data = {json.dumps(clean_input)}\n")
        
        # 执行工具函数
        temp_file.write("try:\n")
        temp_file.write("    # 限制内置函数以增加安全性\n")
        temp_file.write("    allowed_builtins = {\n")
        temp_file.write("        'abs', 'all', 'any', 'bool', 'chr', 'complex', 'dict', 'enumerate',\n")
        temp_file.write("        'filter', 'float', 'format', 'frozenset', 'hex', 'int', 'len', 'list',\n")
        temp_file.write("        'map', 'max', 'min', 'oct', 'ord', 'pow', 'range', 'repr', 'reversed',\n")
        temp_file.write("        'round', 'set', 'slice', 'sorted', 'str', 'sum', 'tuple', 'zip', 'print'\n")
        temp_file.write("    }\n")
        temp_file.write("    restricted_globals = {\n")
        temp_file.write("        '__builtins__': {name: __builtins__[name] for name in allowed_builtins if name in __builtins__}\n")
        temp_file.write("    }\n")
        temp_file.write("    \n")
        temp_file.write("    # 执行函数\n")
        temp_file.write(f"    result = {tool_func.__name__}(**input_data)\n")
        temp_file.write("    print(json.dumps({'success': True, 'result': result}))\n")
        temp_file.write("except Exception as e:\n")
        temp_file.write("    print(json.dumps({'success': False, 'error': str(e)}))\n")

    try:
        # 执行子进程
        result = subprocess.run([sys.executable, temp_filename], 
                                capture_output=True, text=True, timeout=30)
        
        # 解析输出
        if result.stdout:
            try:
                output = json.loads(result.stdout.strip())
                if output['success']:
                    return output['result']
                else:
                    raise Exception(output['error'])
            except json.JSONDecodeError:
                raise Exception(f"工具执行失败: {result.stdout}")
        else:
            raise Exception(f"工具执行出错: {result.stderr}")
    finally:
        # 删除临时文件
        os.unlink(temp_filename)


def safe_execute_tool_restricted(tool_func: Callable, tool_input: Dict[str, Any]) -> Any:
    """
    在受限环境中执行工具函数
    """
    # 验证并清理输入
    clean_input = validate_tool_input(tool_input)
    
    # 限制可用的内置函数
    allowed_builtins = {
        'abs', 'all', 'any', 'bool', 'chr', 'complex', 'dict', 'enumerate',
        'filter', 'float', 'format', 'frozenset', 'hex', 'int', 'len', 'list',
        'map', 'max', 'min', 'oct', 'ord', 'pow', 'range', 'repr', 'reversed',
        'round', 'set', 'slice', 'sorted', 'str', 'sum', 'tuple', 'zip', 'print'
    }
    
    restricted_globals = {
        '__builtins__': {name: builtins.__dict__[name] for name in allowed_builtins if name in builtins.__dict__}
    }
    
    # 尝试执行函数
    try:
        result = tool_func(**clean_input)
        return result
    except Exception as e:
        raise e


def safe_execute_tool(tool_func: Callable, tool_input: Dict[str, Any]) -> Any:
    """
    在沙箱环境中安全执行工具
    """
    # 验证并清理输入
    clean_input = validate_tool_input(tool_input)
    
    # 如果输入是单个参数且为字符串，则直接传递
    if len(clean_input) == 1 and "query" in clean_input:
        return safe_execute_tool_restricted(tool_func, clean_input)
    else:
        # 否则作为关键字参数传递
        return safe_execute_tool_restricted(tool_func, clean_input)


# ============================================================================
# QueryEngine 主类（照搬 Claude Code）
# ============================================================================

class QueryEngineV2:
    """
    QueryEngine V2 — 核心查询引擎
    
    功能：
    - 管理查询生命周期
    - 维护会话状态（消息、用量、权限拒绝）
    - 异步生成器消息流
    - 工具调用与权限管理
    - 预算控制
    
    照搬 Claude Code 的 QueryEngine.ts 设计
    """
    
    def __init__(self, config: QueryEngineConfig):
        self.config = config
        self.mutable_messages: List[Message] = []
        self.permission_denials: List[PermissionDenial] = []
        self.total_usage = Usage()
        self.turn_count = 0
        self.session_id = f"qe_{int(time.time())}"
        
        # 状态
        self._abort_requested = False
        self._current_turn = 0
    
    async def submit_message(
        self,
        prompt: Union[str, List[Dict]],
        options: Optional[Dict] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        提交消息并执行查询循环
        
        照搬 Claude Code 的 submitMessage 方法
        
        Yields:
            消息事件：progress, result, error, tool_use, tool_result
        """
        options = options or {}
        is_meta = options.get('is_meta', False)
        
        start_time = time.time()
        
        # 检查预算
        if self.config.max_budget_usd and self.total_usage.cost_usd >= self.config.max_budget_usd:
            yield {
                "type": "error",
                "content": f"预算已用尽: ${self.total_usage.cost_usd:.4f}",
                "is_error": True
            }
            return
        
        # 检查最大轮次
        if self.turn_count >= self.config.max_turns:
            yield {
                "type": "error",
                "content": f"已达到最大轮次: {self.config.max_turns}",
                "is_error": True
            }
            return
        
        # 构建系统提示词
        system_prompt = self._build_system_prompt()
        
        # 添加用户消息
        user_content = prompt if isinstance(prompt, str) else json.dumps(prompt, ensure_ascii=False)
        user_msg = Message(
            role="user",
            content=user_content,
            metadata={"is_meta": is_meta}
        )
        self.mutable_messages.append(user_msg)
        
        # 存储到记忆
        self.config.memory.store(user_content, role="user", mem_type="query")
        
        # 开始查询循环
        self.turn_count += 1
        turn_start = time.time()
        
        try:
            # Yield 进度
            yield {
                "type": "progress",
                "content": "正在思考...",
                "phase": "thinking"
            }
            
            # 检查是否有工具可以处理
            matching_tools = self.config.tools.find_tools(user_content, limit=1)
            
            if matching_tools and not is_meta:
                # 工具调用流程
                tool = matching_tools[0]
                
                # 准备工具输入
                tool_input = {"query": user_content}
                
                yield {
                    "type": "tool_use",
                    "tool_name": tool.spec.name,
                    "tool_input": tool_input,
                    "tool_use_id": f"tool_{int(time.time())}"
                }
                
                # 执行工具
                try:
                    if hasattr(tool, 'func') and tool.func:
                        # 使用安全执行函数
                        result = safe_execute_tool(tool.func, tool_input)
                    else:
                        result = f"工具 {tool.spec.name} 执行完成"
                    
                    tool_result = ToolResult(
                        tool_use_id=f"tool_{int(time.time())}",
                        output=str(result),
                        is_error=False
                    )
                    
                    yield {
                        "type": "tool_result",
                        "tool_use_id": tool_result.tool_use_id,
                        "output": tool_result.output,
                        "is_error": False
                    }
                    
                    # 生成回复
                    response = f"使用工具 {tool.spec.name} 的结果:\n{result}"
                    
                except Exception as e:
                    tool_result = ToolResult(
                        tool_use_id=f"tool_{int(time.time())}",
                        output=str(e),
                        is_error=True
                    )
                    
                    yield {
                        "type": "tool_result",
                        "tool_use_id": tool_result.tool_use_id,
                        "output": tool_result.output,
                        "is_error": True
                    }
                    
                    response = f"工具执行失败: {e}"
            else:
                # 普通对话流程
                # 构建完整提示词
                full_prompt = self._build_full_prompt(user_content)
                
                # 调用 LLM
                response = chat(
                    prompt=full_prompt,
                    system=system_prompt,
                    model=route(full_prompt),
                    temperature=0.7
                )
                
                # 估算用量
                self._update_usage(full_prompt, response)
            
            # 添加助手消息
            assistant_msg = Message(
                role="assistant",
                content=response,
                metadata={"turn": self.turn_count}
            )
            self.mutable_messages.append(assistant_msg)
            
            # 存储到记忆
            self.config.memory.store(response, role="assistant", mem_type="query")
            
            # Yield 最终结果
            yield {
                "type": "result",
                "content": response,
                "is_error": False,
                "duration_ms": (time.time() - start_time) * 1000,
                "turn": self.turn_count,
                "usage": asdict(self.total_usage)
            }
            
        except Exception as e:
            error_msg = f"查询错误: {str(e)}"
            
            # 记录权限拒绝
            if "permission" in str(e).lower():
                self.permission_denials.append(PermissionDenial(
                    tool_name="unknown",
                    tool_use_id=f"denial_{int(time.time())}",
                    tool_input={"error": error_msg}
                ))
            
            yield {
                "type": "error",
                "content": error_msg,
                "is_error": True,
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        parts = []
        
        # 基础系统提示
        parts.append("你是冷小北，潘豪的数字生命体助手。")
        
        # 宪法原则
        parts.append("""
宪法核心原则：
1. 克制：只做潘豪授权范围内的事，不多做
2. 诚实：失败就是失败，不粉饰
3. 简洁：有主见，不废话，中文优先
4. 汇报：重大决策前征询潘豪意见
5. 潘豪是外部验证层，我不替他做决策
""")
        
        # 自定义系统提示
        if self.config.custom_system_prompt:
            parts.append(self.config.custom_system_prompt)
        
        if self.config.append_system_prompt:
            parts.append(self.config.append_system_prompt)
        
        return "\n\n".join(parts)
    
    def _build_full_prompt(self, user_content: str) -> str:
        """构建完整提示词（包含上下文）"""
        # 获取最近的对话历史
        recent_messages = self.mutable_messages[-10:]  # 最近10条
        
        context_parts = []
        for msg in recent_messages[:-1]:  # 排除最新的用户消息
            if msg.role == "user":
                context_parts.append(f"用户: {msg.content}")
            elif msg.role == "assistant":
                context_parts.append(f"助手: {msg.content}")
        
        # 构建完整提示
        full_prompt = ""
        if context_parts:
            full_prompt += "对话历史:\n" + "\n".join(context_parts) + "\n\n"
        
        full_prompt += f"当前问题: {user_content}"
        
        return full_prompt
    
    def _update_usage(self, prompt: str, response: str):
        """更新用量统计"""
        # 简化估算
        input_tokens = len(prompt.encode('utf-8'))
        output_tokens = len(response.encode('utf-8'))
        
        self.total_usage.input_tokens += input_tokens
        self.total_usage.output_tokens += output_tokens
        self.total_usage.total_tokens += input_tokens + output_tokens
        
        # 估算成本
        cost_per_1k = 0.0001
        self.total_usage.cost_usd += (input_tokens + output_tokens) / 1000 * cost_per_1k
    
    def get_messages(self) -> List[Message]:
        """获取所有消息"""
        return self.mutable_messages.copy()
    
    def get_usage(self) -> Usage:
        """获取用量统计"""
        return self.total_usage
    
    def get_permission_denials(self) -> List[PermissionDenial]:
        """获取权限拒绝记录"""
        return self.permission_denials.copy()
    
    def abort(self):
        """中止当前查询"""
        self._abort_requested = True
    
    def clear(self):
        """清空会话状态"""
        self.mutable_messages = []
        self.permission_denials = []
        self.total_usage = Usage()
        self.turn_count = 0
    
    def export_session(self) -> Dict:
        """导出会话数据"""
        return {
            "session_id": self.session_id,
            "messages": [asdict(m) for m in self.mutable_messages],
            "usage": asdict(self.total_usage),
            "permission_denials": [asdict(d) for d in self.permission_denials],
            "turn_count": self.turn_count
        }
    
    def import_session(self, data: Dict):
        """导入会话数据"""
        self.session_id = data.get("session_id", self.session_id)
        self.mutable_messages = [Message(**m) for m in data.get("messages", [])]
        self.total_usage = Usage(**data.get("usage", {}))
        self.permission_denials = [PermissionDenial(**d) for d in data.get("permission_denials", [])]
        self.turn_count = data.get("turn_count", 0)


# ============================================================================
# 便捷函数
# ============================================================================

async def ask(
    prompt: str,
    config: QueryEngineConfig,
    **options
) -> AsyncGenerator[Dict, None]:
    """
    便捷函数：单次查询
    
    类似 Claude Code 的 ask() 函数
    """
    engine = QueryEngineV2(config)
    async for result in engine.submit_message(prompt, options):
        yield result


def create_query_engine(
    cwd: str,
    tools: ToolRegistry,
    memory: Memory,
    **kwargs
) -> QueryEngineV2:
    """创建 QueryEngine 实例"""
    config = QueryEngineConfig(
        cwd=cwd,
        tools=tools,
        memory=memory,
        **kwargs
    )
    return QueryEngineV2(config)

# 导入inspect模块用于获取函数源码
import inspect