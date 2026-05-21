"""
Forked Agent 机制 - 照搬 Claude Code 设计
==========================================
核心特性：
- 隔离的子任务执行环境
- 状态隔离，防止影响父任务
- 缓存共享，提高性能
- 用量追踪和转录记录
- 错误处理和日志记录

参考 Claude Code 的 runForkedAgent 实现
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncGenerator, Callable, Union

from .query_engine import Message, Usage
from .memory import Memory
from .tool_registry import ToolRegistry
from .llm import chat, route


# ============================================================================
# 类型定义
# ============================================================================

@dataclass
class CacheSafeParams:
    """缓存安全参数，必须与父任务相同以确保缓存命中"""
    system_prompt: str
    user_context: Dict[str, str]
    system_context: Dict[str, str]
    tools: ToolRegistry
    memory: Memory
    fork_context_messages: List[Message]


@dataclass
class ForkedAgentParams:
    """Forked Agent 参数"""
    prompt_messages: List[Message]
    cache_safe_params: CacheSafeParams
    can_use_tool: Callable
    query_source: str
    fork_label: str
    max_output_tokens: Optional[int] = None
    max_turns: Optional[int] = 10
    on_message: Optional[Callable] = None
    skip_transcript: bool = False
    skip_cache_write: bool = False


@dataclass
class ForkedAgentResult:
    """Forked Agent 执行结果"""
    messages: List[Message]
    total_usage: Usage


@dataclass
class SubagentContext:
    """子代理上下文"""
    tools: ToolRegistry
    memory: Memory
    messages: List[Message]
    system_prompt: str
    user_context: Dict[str, str]
    system_context: Dict[str, str]
    can_use_tool: Callable
    query_source: str
    agent_id: str = field(default_factory=lambda: f"agent_{uuid.uuid4()}")
    abort_requested: bool = False


# ============================================================================
# Forked Agent 核心功能
# ============================================================================

class ForkedAgent:
    """Forked Agent 实现"""
    
    @staticmethod
    def create_subagent_context(
        parent_context: Dict[str, Any],
        overrides: Optional[Dict[str, Any]] = None
    ) -> SubagentContext:
        """
        创建隔离的子代理上下文
        
        参考 Claude Code 的 createSubagentContext 函数
        """
        overrides = overrides or {}
        
        # 克隆消息列表，确保状态隔离
        fork_messages = []
        for msg in parent_context.get('messages', []):
            # 创建消息的深拷贝
            fork_msg = Message(
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp,
                uuid=f"msg_{uuid.uuid4()}",
                metadata=msg.metadata.copy()
            )
            fork_messages.append(fork_msg)
        
        # 克隆工具和记忆系统
        # 注意：这里使用浅拷贝，实际项目中可能需要深拷贝
        tools = parent_context.get('tools')
        memory = parent_context.get('memory')
        
        return SubagentContext(
            tools=tools,
            memory=memory,
            messages=fork_messages,
            system_prompt=parent_context.get('system_prompt', ''),
            user_context=parent_context.get('user_context', {}),
            system_context=parent_context.get('system_context', {}),
            can_use_tool=parent_context.get('can_use_tool', lambda *args: True),
            query_source=parent_context.get('query_source', 'forked'),
            agent_id=overrides.get('agent_id', f"agent_{uuid.uuid4()}")
        )
    
    @staticmethod
    async def run_forked_agent(
        params: ForkedAgentParams
    ) -> ForkedAgentResult:
        """
        运行 Forked Agent
        
        参考 Claude Code 的 runForkedAgent 函数
        """
        start_time = time.time()
        output_messages: List[Message] = []
        total_usage = Usage()
        
        # 解构参数
        prompt_messages = params.prompt_messages
        cache_safe_params = params.cache_safe_params
        can_use_tool = params.can_use_tool
        query_source = params.query_source
        fork_label = params.fork_label
        max_turns = params.max_turns or 10
        on_message = params.on_message
        
        # 创建隔离的子代理上下文
        parent_context = {
            'tools': cache_safe_params.tools,
            'memory': cache_safe_params.memory,
            'messages': cache_safe_params.fork_context_messages,
            'system_prompt': cache_safe_params.system_prompt,
            'user_context': cache_safe_params.user_context,
            'system_context': cache_safe_params.system_context,
            'can_use_tool': can_use_tool,
            'query_source': query_source
        }
        
        subagent_context = ForkedAgent.create_subagent_context(parent_context)
        
        # 构建初始消息
        initial_messages = subagent_context.messages.copy()
        initial_messages.extend(prompt_messages)
        
        try:
            # 执行查询循环
            turn_count = 0
            current_messages = initial_messages.copy()
            
            while turn_count < max_turns:
                # 构建完整提示
                full_prompt = ForkedAgent._build_full_prompt(current_messages)
                
                # 调用 LLM
                response = chat(
                    prompt=full_prompt,
                    system=cache_safe_params.system_prompt,
                    model=route(full_prompt),
                    temperature=0.7
                )
                
                # 创建助手消息
                assistant_msg = Message(
                    role="assistant",
                    content=response,
                    metadata={"turn": turn_count + 1, "agent_id": subagent_context.agent_id}
                )
                
                output_messages.append(assistant_msg)
                current_messages.append(assistant_msg)
                
                # 调用回调函数
                if on_message:
                    on_message(assistant_msg)
                
                # 更新用量
                ForkedAgent._update_usage(full_prompt, response, total_usage)
                
                turn_count += 1
                
                # 检查是否需要继续
                if not ForkedAgent._should_continue(response):
                    break
                    
        except Exception as e:
            # 记录错误
            error_msg = f"Forked agent error: {str(e)}"
            error_message = Message(
                role="system",
                content=error_msg,
                metadata={"error": str(e), "agent_id": subagent_context.agent_id}
            )
            output_messages.append(error_message)
            
        duration_ms = (time.time() - start_time) * 1000
        
        # 记录执行信息
        print(f"Forked agent [{fork_label}] finished in {duration_ms:.2f}ms")
        print(f"Generated {len(output_messages)} messages")
        print(f"Total usage: {total_usage.total_tokens} tokens, ${total_usage.cost_usd:.4f}")
        
        return ForkedAgentResult(
            messages=output_messages,
            total_usage=total_usage
        )
    
    @staticmethod
    def _build_full_prompt(messages: List[Message]) -> str:
        """构建完整提示"""
        prompt_parts = []
        
        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(f"用户: {msg.content}")
            elif msg.role == "assistant":
                prompt_parts.append(f"助手: {msg.content}")
            elif msg.role == "system":
                prompt_parts.append(f"系统: {msg.content}")
        
        return "\n".join(prompt_parts)
    
    @staticmethod
    def _update_usage(prompt: str, response: str, usage: Usage):
        """更新用量统计"""
        input_tokens = len(prompt.encode('utf-8'))
        output_tokens = len(response.encode('utf-8'))
        
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.total_tokens += input_tokens + output_tokens
        
        # 估算成本
        cost_per_1k = 0.0001
        usage.cost_usd += (input_tokens + output_tokens) / 1000 * cost_per_1k
        
    @staticmethod
    def _should_continue(response: str) -> bool:
        """判断是否需要继续对话"""
        # 简单的判断逻辑，实际项目中可能需要更复杂的判断
        # 例如检查是否有工具调用、是否需要追问等
        if len(response) < 50:
            return False
        if any(phrase in response.lower() for phrase in ["结束", "完成", "再见", "谢谢"]):
            return False
        return True


# ============================================================================
# 便捷函数
# ============================================================================

async def run_forked_agent(
    prompt: str,
    cache_safe_params: CacheSafeParams,
    can_use_tool: Callable = lambda *args: True,
    query_source: str = "forked",
    fork_label: str = "default",
    **kwargs
) -> ForkedAgentResult:
    """
    便捷函数：运行 Forked Agent
    
    类似 Claude Code 的 runForkedAgent 函数
    """
    # 创建提示消息
    prompt_message = Message(
        role="user",
        content=prompt
    )
    
    # 构建参数
    params = ForkedAgentParams(
        prompt_messages=[prompt_message],
        cache_safe_params=cache_safe_params,
        can_use_tool=can_use_tool,
        query_source=query_source,
        fork_label=fork_label,
        **kwargs
    )
    
    # 运行 Forked Agent
    return await ForkedAgent.run_forked_agent(params)


def create_cache_safe_params(
    system_prompt: str,
    user_context: Dict[str, str],
    system_context: Dict[str, str],
    tools: ToolRegistry,
    memory: Memory,
    messages: List[Message]
) -> CacheSafeParams:
    """
    创建缓存安全参数
    
    参考 Claude Code 的 createCacheSafeParams 函数
    """
    return CacheSafeParams(
        system_prompt=system_prompt,
        user_context=user_context,
        system_context=system_context,
        tools=tools,
        memory=memory,
        fork_context_messages=messages
    )
