"""
Hooks 系统架构 — 照搬 Claude Code 设计
====================================
核心功能：
- 模块化的状态管理、权限控制、输入处理
- 支持多种钩子类型：命令、提示词、HTTP、代理
- 基于事件触发的钩子系统
- 条件过滤和异步执行
"""

import os
import time
import json
import asyncio
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Union
from enum import Enum
import shlex

from .executor import SafetyGate

logger = logging.getLogger(__name__)


# ============================================================================# 事件类型定义# ============================================================================

class HookEvent(Enum):
    """钩子事件类型"""
    BEFORE_TOOL_USE = "before_tool_use"
    AFTER_TOOL_USE = "after_tool_use"
    BEFORE_QUERY = "before_query"
    AFTER_QUERY = "after_query"
    ON_ERROR = "on_error"
    ON_SESSION_START = "on_session_start"
    ON_SESSION_END = "on_session_end"
    ON_MEMORY_CONSOLIDATION = "on_memory_consolidation"
    ON_SELF_EVOLUTION = "on_self_evolution"


# ============================================================================# 钩子基类# ============================================================================

@dataclass(kw_only=True)
class BaseHook:
    """钩子基类"""
    type: str
    if_condition: Optional[str] = None  # 条件过滤
    timeout: Optional[float] = None      # 超时时间（秒）
    status_message: Optional[str] = None  # 状态消息
    once: bool = False                   # 是否只执行一次
    async_exec: bool = False             # 是否异步执行


# ============================================================================# 具体钩子类型# ============================================================================

@dataclass(kw_only=True)
class BashCommandHook(BaseHook):
    """Bash命令钩子"""
    command: str  # 要执行的命令
    type: str = "command"
    shell: str = "bash"  # shell类型
    async_rewake: bool = False  # 异步执行并在错误时唤醒
    allowed_args: Optional[List[str]] = None  # 允许的参数白名单


@dataclass(kw_only=True)
class PromptHook(BaseHook):
    """提示词钩子"""
    prompt: str  # 要执行的提示词
    type: str = "prompt"
    model: Optional[str] = None  # 使用的模型


@dataclass(kw_only=True)
class HttpHook(BaseHook):
    """HTTP钩子"""
    url: str  # 要POST的URL
    type: str = "http"
    headers: Optional[Dict[str, str]] = None  # 额外的请求头
    allowed_env_vars: Optional[List[str]] = None  # 允许的环境变量


@dataclass(kw_only=True)
class AgentHook(BaseHook):
    """代理钩子"""
    prompt: str  # 验证提示词
    type: str = "agent"
    model: Optional[str] = None  # 使用的模型


# 钩子联合类型
HookType = Union[BashCommandHook, PromptHook, HttpHook, AgentHook]


# ============================================================================# 钩子匹配器# ============================================================================

@dataclass(kw_only=True)
class HookMatcher:
    """钩子匹配器"""
    matcher: Optional[str] = None  # 匹配模式
    hooks: List[HookType]  # 要执行的钩子列表


# ============================================================================# 钩子管理器# ============================================================================

class HookManager:
    """
    钩子管理器
    功能：
    1. 注册和管理钩子
    2. 基于事件触发钩子
    3. 处理钩子执行
    4. 管理钩子生命周期
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.hooks_dir = self.project_root / "hooks"
        self.hooks_dir.mkdir(exist_ok=True)
        
        # 钩子存储
        self.hooks: Dict[HookEvent, List[HookMatcher]] = {}
        self.executed_hooks: set = set()
        
        # 加载默认钩子
        self._load_default_hooks()
    
    def _load_default_hooks(self):
        """加载默认钩子"""
        # 示例：添加默认钩子
        default_hooks = {
            HookEvent.ON_SESSION_START: [
                HookMatcher(
                    hooks=[
                        BashCommandHook(
                            command="echo '冷小北会话开始'",
                            status_message="初始化会话...",
                            allowed_args=["冷小北会话开始"]
                        )
                    ]
                )
            ],
            HookEvent.ON_SESSION_END: [
                HookMatcher(
                    hooks=[
                        BashCommandHook(
                            command="echo '冷小北会话结束'",
                            status_message="清理会话...",
                            allowed_args=["冷小北会话结束"]
                        )
                    ]
                )
            ]
        }
        
        for event, matchers in default_hooks.items():
            self.hooks[event] = matchers
    
    def register_hook(self, event: HookEvent, matcher: HookMatcher):
        """注册钩子"""
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(matcher)
    
    def unregister_hook(self, event: HookEvent, matcher_index: int):
        """注销钩子"""
        if event in self.hooks and 0 <= matcher_index < len(self.hooks[event]):
            del self.hooks[event][matcher_index]
    
    async def trigger(self, event: HookEvent, context: Dict[str, Any] = None):
        """触发钩子"""
        if event not in self.hooks:
            return
        
        context = context or {}
        
        for matcher in self.hooks[event]:
            # 检查匹配条件
            if matcher.matcher and not self._match(matcher.matcher, context):
                continue
            
            # 执行钩子
            for hook in matcher.hooks:
                # 检查条件
                if hook.if_condition and not self._check_condition(hook.if_condition, context):
                    continue
                
                # 检查是否只执行一次
                hook_id = f"{event.value}_{id(hook)}"
                if hook.once and hook_id in self.executed_hooks:
                    continue
                
                # 执行钩子
                if hook.async_exec:
                    asyncio.create_task(self._execute_hook(hook, context))
                else:
                    await self._execute_hook(hook, context)
                
                # 标记已执行
                if hook.once:
                    self.executed_hooks.add(hook_id)
    
    def _match(self, matcher: str, context: Dict[str, Any]) -> bool:
        """检查匹配模式"""
        # 简单的字符串匹配
        tool_name = context.get('tool_name', '')
        return matcher in tool_name
    
    def _check_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """检查条件"""
        # 简单的条件检查
        # 实际实现应该解析权限规则语法
        return True
    
    async def _execute_hook(self, hook: HookType, context: Dict[str, Any]):
        """执行钩子"""
        try:
            if isinstance(hook, BashCommandHook):
                await self._execute_bash_hook(hook, context)
            elif isinstance(hook, PromptHook):
                await self._execute_prompt_hook(hook, context)
            elif isinstance(hook, HttpHook):
                await self._execute_http_hook(hook, context)
            elif isinstance(hook, AgentHook):
                await self._execute_agent_hook(hook, context)
        except Exception as e:
            logger.error(f"执行钩子失败: {e}")
    
    def _validate_command(self, command: str, allowed_args: Optional[List[str]] = None) -> bool:
        """
        验证命令安全性
        - 检查是否在允许的参数白名单中
        - 防止危险字符和命令注入
        """
        # 检查危险字符
        dangerous_chars = [';', '&', '|', '`', '$(', '||', '&&']
        for char in dangerous_chars:
            if char in command:
                return False
        
        # 如果有白名单，检查参数是否在白名单内
        if allowed_args:
            # 解析命令参数
            try:
                parsed_args = shlex.split(command)
                # 检查除第一个元素（命令名）外的参数
                for arg in parsed_args[1:]:
                    if arg not in allowed_args:
                        return False
            except ValueError:
                # shlex.split失败，说明命令格式有问题
                return False
        
        return True
    
    async def _execute_bash_hook(self, hook: BashCommandHook, context: Dict[str, Any]):
        """执行Bash命令钩子 — 使用 SafetyGate + shlex.split + create_subprocess_exec"""
        if hook.status_message:
            logger.info(f"[Hooks] {hook.status_message}")

        # 安全地替换上下文变量，防止命令注入
        command = hook.command
        for key, value in context.items():
            safe_value = shlex.quote(str(value))
            command = command.replace(f"${key}", safe_value)

        # SafetyGate 风险评估
        risk = SafetyGate.assess(command)
        if risk == SafetyGate.RISK_CRITICAL:
            logger.warning(f"[Hooks] 命令被 SafetyGate 拦截: {command}")
            return
        if risk in (SafetyGate.RISK_HIGH, SafetyGate.RISK_MEDIUM):
            logger.warning(f"[Hooks] 命令风险等级 {risk}，需确认: {command}")
            return

        # 使用 shlex.split 解析命令，避免 shell=True
        try:
            args = shlex.split(command)
        except ValueError as e:
            logger.warning(f"[Hooks] 命令解析失败: {e}")
            return

        if not args:
            return

        # 使用 create_subprocess_exec 替代 create_subprocess_shell
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # 设置超时
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=hook.timeout or 30
            )

            if process.returncode != 0:
                logger.warning(f"[Hooks] 命令执行失败: {stderr.decode()}")
                if hook.async_rewake:
                    pass
            else:
                logger.info(f"[Hooks] 命令执行成功: {stdout.decode()}")
        except asyncio.TimeoutError:
            process.kill()
            logger.warning(f"[Hooks] 命令执行超时")
    
    async def _execute_prompt_hook(self, hook: PromptHook, context: Dict[str, Any]):
        """执行提示词钩子"""
        if hook.status_message:
            logger.info(f"[Hooks] {hook.status_message}")
        
        # 替换上下文变量 - 对于提示词，我们不需要像命令那样严格的安全措施
        # 但仍然要小心处理，避免注入问题
        prompt = hook.prompt
        for key, value in context.items():
            prompt = prompt.replace(f"${key}", str(value))
        
        # 调用LLM
        from .llm import chat, route
        
        response = chat(
            prompt=prompt,
            system="你是一个钩子执行助手",
            model=hook.model or route(prompt),
            temperature=0.3
        )
        
        logger.info(f"[Hooks] 提示词执行结果: {response}")
    
    async def _execute_http_hook(self, hook: HttpHook, context: Dict[str, Any]):
        """执行HTTP钩子"""
        if hook.status_message:
            logger.info(f"[Hooks] {hook.status_message}")
        
        # 替换上下文变量 - 安全处理URL
        url = hook.url
        for key, value in context.items():
            # 对URL进行编码以防止注入
            import urllib.parse
            encoded_value = urllib.parse.quote(str(value), safe='')
            url = url.replace(f"${key}", encoded_value)
        
        # 处理请求头
        headers = hook.headers or {}
        for header_name, header_value in headers.items():
            # 替换环境变量
            if hook.allowed_env_vars:
                for env_var in hook.allowed_env_vars:
                    if f"${env_var}" in header_value:
                        headers[header_name] = header_value.replace(f"${env_var}", os.environ.get(env_var, ""))
        
        # 发送HTTP请求
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    json=context,
                    headers=headers,
                    timeout=hook.timeout or 30
                ) as response:
                    status = response.status
                    content = await response.text()
                    logger.info(f"[Hooks] HTTP请求结果: 状态码={status}, 内容={content}")
            except Exception as e:
                logger.warning(f"[Hooks] HTTP请求失败: {e}")
    
    async def _execute_agent_hook(self, hook: AgentHook, context: Dict[str, Any]):
        """执行代理钩子"""
        if hook.status_message:
            logger.info(f"[Hooks] {hook.status_message}")
        
        # 替换上下文变量
        prompt = hook.prompt
        for key, value in context.items():
            prompt = prompt.replace(f"${key}", str(value))
        
        # 调用LLM
        from .llm import chat, route
        
        response = chat(
            prompt=prompt,
            system="你是一个代理验证助手",
            model=hook.model or route(prompt),
            temperature=0.3
        )
        
        logger.info(f"[Hooks] 代理验证结果: {response}")
    
    def save_hooks(self):
        """保存钩子配置"""
        hooks_config = {}
        for event, matchers in self.hooks.items():
            event_hooks = []
            for matcher in matchers:
                matcher_dict = {
                    "matcher": matcher.matcher,
                    "hooks": []
                }
                for hook in matcher.hooks:
                    hook_dict = {
                        "type": hook.type,
                        "if_condition": hook.if_condition,
                        "timeout": hook.timeout,
                        "status_message": hook.status_message,
                        "once": hook.once,
                        "async_exec": hook.async_exec
                    }
                    if isinstance(hook, BashCommandHook):
                        hook_dict.update({
                            "command": hook.command,
                            "shell": hook.shell,
                            "async_rewake": hook.async_rewake,
                            "allowed_args": hook.allowed_args
                        })
                    elif isinstance(hook, PromptHook):
                        hook_dict.update({
                            "prompt": hook.prompt,
                            "model": hook.model
                        })
                    elif isinstance(hook, HttpHook):
                        hook_dict.update({
                            "url": hook.url,
                            "headers": hook.headers,
                            "allowed_env_vars": hook.allowed_env_vars
                        })
                    elif isinstance(hook, AgentHook):
                        hook_dict.update({
                            "prompt": hook.prompt,
                            "model": hook.model
                        })
                    matcher_dict["hooks"].append(hook_dict)
                event_hooks.append(matcher_dict)
            hooks_config[event.value] = event_hooks
        
        config_file = self.hooks_dir / "hooks_config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(hooks_config, f, ensure_ascii=False, indent=2)
    
    def load_hooks(self):
        """加载钩子配置"""
        config_file = self.hooks_dir / "hooks_config.json"
        if not config_file.exists():
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            for event_str, matchers_config in config.items():
                event = HookEvent(event_str)
                matchers = []
                for matcher_config in matchers_config:
                    hooks = []
                    for hook_config in matcher_config.get("hooks", []):
                        hook_type = hook_config.get("type")
                        if hook_type == "command":
                            hook = BashCommandHook(
                                command=hook_config.get("command"),
                                shell=hook_config.get("shell", "bash"),
                                if_condition=hook_config.get("if_condition"),
                                timeout=hook_config.get("timeout"),
                                status_message=hook_config.get("status_message"),
                                once=hook_config.get("once", False),
                                async_exec=hook_config.get("async_exec", False),
                                async_rewake=hook_config.get("async_rewake", False),
                                allowed_args=hook_config.get("allowed_args")
                            )
                        elif hook_type == "prompt":
                            hook = PromptHook(
                                prompt=hook_config.get("prompt"),
                                model=hook_config.get("model"),
                                if_condition=hook_config.get("if_condition"),
                                timeout=hook_config.get("timeout"),
                                status_message=hook_config.get("status_message"),
                                once=hook_config.get("once", False),
                                async_exec=hook_config.get("async_exec", False)
                            )
                        elif hook_type == "http":
                            hook = HttpHook(
                                url=hook_config.get("url"),
                                headers=hook_config.get("headers"),
                                allowed_env_vars=hook_config.get("allowed_env_vars"),
                                if_condition=hook_config.get("if_condition"),
                                timeout=hook_config.get("timeout"),
                                status_message=hook_config.get("status_message"),
                                once=hook_config.get("once", False),
                                async_exec=hook_config.get("async_exec", False)
                            )
                        elif hook_type == "agent":
                            hook = AgentHook(
                                prompt=hook_config.get("prompt"),
                                model=hook_config.get("model"),
                                if_condition=hook_config.get("if_condition"),
                                timeout=hook_config.get("timeout"),
                                status_message=hook_config.get("status_message"),
                                once=hook_config.get("once", False),
                                async_exec=hook_config.get("async_exec", False)
                            )
                        else:
                            continue
                        hooks.append(hook)
                    matcher = HookMatcher(
                        matcher=matcher_config.get("matcher"),
                        hooks=hooks
                    )
                    matchers.append(matcher)
                self.hooks[event] = matchers
        except Exception as e:
            logger.error(f"加载钩子配置失败: {e}")


# ============================================================================# 便捷函数# ============================================================================

def create_hook_manager(project_root: str) -> HookManager:
    """创建钩子管理器"""
    manager = HookManager(project_root)
    manager.load_hooks()
    return manager