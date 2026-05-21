#!/usr/bin/env python3
"""
集成模块 - 连接冷小北与 OpenClaw 和 Claude Code

架构原则：
- 冷小北（核心）保留：进化引擎、KAIROS 决策、GEPA 循环、SKILL 持久化
- 冷小北可调用：OpenClaw 的全部功能、Claude Code 的全部功能
- 有就用，没有才自己写
"""

import os
import json
import subprocess
import asyncio
from typing import Optional, Dict, Any, List


class OpenClawIntegration:
    """OpenClaw 集成"""

    def __init__(self, openclaw_path: str):
        self.openclaw_path = openclaw_path
        self.executable = os.path.join(openclaw_path, "openclaw.mjs")

    def is_available(self) -> bool:
        """检查 OpenClaw 是否可用"""
        return os.path.exists(self.executable)

    def run_command(self, args: List[str], timeout: int = 30) -> Dict[str, Any]:
        """运行 OpenClaw 命令"""
        try:
            command = ["node", self.executable] + args
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "命令执行超时"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def run_command_async(self, args: List[str], timeout: int = 30) -> Dict[str, Any]:
        """异步运行 OpenClaw 命令"""
        def sync_run():
            return self.run_command(args, timeout)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_run)

    def analyze_code(self, code: str) -> Dict[str, Any]:
        """分析代码"""
        return self.run_command(["analyze", "-c", code])

    def generate_code(self, prompt: str) -> Dict[str, Any]:
        """生成代码"""
        return self.run_command(["generate", "-p", prompt])

    def optimize_performance(self, code: str) -> Dict[str, Any]:
        """优化性能"""
        return self.run_command(["optimize", "-c", code])

    def security_scan(self, target: str) -> Dict[str, Any]:
        """安全扫描"""
        return self.run_command(["security", "scan", "-t", target])


class ClaudeCodeIntegration:
    """Claude Code 集成 - 通过代理服务器调用 LLM"""

    def __init__(self, claude_code_path: str):
        self.claude_code_path = claude_code_path
        self.executable = os.path.join(claude_code_path, "claude-code", "dist", "entrypoints", "cli.js")
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = os.environ.get("ANTHROPIC_BASE_URL",
            "http://localhost:8082/v1/messages")

    def is_available(self) -> bool:
        """检查 Claude Code 是否可用"""
        if not self.api_key:
            return False
        if not os.path.exists(self.executable):
            return False
        return True

    def _call_api(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """直接调用 API 代理服务器，带重试机制"""
        import requests, time

        for attempt in range(3):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key
                }
                data = {
                    "model": "sonnet",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens
                }

                response = requests.post(self.base_url, headers=headers, json=data, timeout=90)
                response.raise_for_status()

                result = response.json()
                content = result.get("content", [])
                text = ""
                for item in content:
                    if item.get("type") == "text":
                        text += item.get("text", "")

                if text.strip():
                    return {
                        "success": True,
                        "stdout": text,
                        "stderr": "",
                        "returncode": 0
                    }

            except requests.exceptions.Timeout:
                if attempt < 2:
                    time.sleep(2)
                    continue
                return {"success": False, "error": "API 调用超时(已重试3次)"}
            except requests.exceptions.RequestException as e:
                if attempt < 2:
                    time.sleep(1)
                    continue
                return {"success": False, "error": str(e)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "API 返回空内容"}

    def llm_chat(self, prompt: str, max_tokens: int = 2000) -> Dict[str, Any]:
        """通用 LLM 对话"""
        return self._call_api(prompt, max_tokens=max_tokens)

    def code_completion(self, code: str) -> Dict[str, Any]:
        """代码补全"""
        return self._call_api(code, max_tokens=2000)

    def debug_assistant(self, error: str, context: str = "") -> Dict[str, Any]:
        """调试助手"""
        prompt = f"错误信息: {error}\n上下文: {context}\n请帮助调试这个错误。"
        return self._call_api(prompt, max_tokens=2000)

    def documentation_generator(self, target: str) -> Dict[str, Any]:
        """文档生成"""
        prompt = f"请为以下目标生成文档: {target}"
        return self._call_api(prompt, max_tokens=3000)

    def test_generator(self, code: str) -> Dict[str, Any]:
        """测试生成"""
        prompt = f"请为以下代码生成测试: {code}"
        return self._call_api(prompt, max_tokens=2000)


class IntegrationManager:
    """集成管理器"""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.openclaw = None
        self.claude_code = None
        self._init_integrations()

    def _init_integrations(self):
        """初始化集成"""
        openclaw_paths = [
            os.path.join(self.project_root, "..", "openclaw"),
            os.path.join(os.path.dirname(self.project_root), "openclaw")
        ]

        for path in openclaw_paths:
            if os.path.exists(os.path.join(path, "openclaw.mjs")):
                self.openclaw = OpenClawIntegration(path)
                if self.openclaw.is_available():
                    print(f"[集成] OpenClaw 已找到: {path}")
                break

        claude_code_paths = [
            os.path.join(self.project_root, "..", "claude-code-binary"),
            os.path.join(os.path.dirname(self.project_root), "claude-code-binary")
        ]

        for path in claude_code_paths:
            if os.path.exists(os.path.join(path, "claude-code")):
                self.claude_code = ClaudeCodeIntegration(path)
                if self.claude_code.is_available():
                    print(f"[集成] Claude Code 已找到: {path}")
                break

    def call_openclaw(self, function_name: str, **kwargs) -> Dict[str, Any]:
        """调用 OpenClaw 功能"""
        if not self.openclaw:
            return {"success": False, "error": "OpenClaw 未找到"}

        method_map = {
            "analyze_code": lambda: self.openclaw.analyze_code(kwargs.get("code", "")),
            "generate_code": lambda: self.openclaw.generate_code(kwargs.get("prompt", "")),
            "optimize_performance": lambda: self.openclaw.optimize_performance(kwargs.get("code", "")),
            "security_scan": lambda: self.openclaw.security_scan(kwargs.get("target", ""))
        }

        if function_name in method_map:
            return method_map[function_name]()

        return self.openclaw.run_command([function_name] + self._kwargs_to_args(kwargs))

    async def call_openclaw_async(self, function_name: str, **kwargs) -> Dict[str, Any]:
        """异步调用 OpenClaw 功能"""
        if not self.openclaw:
            return {"success": False, "error": "OpenClaw 未找到"}

        result = self.call_openclaw(function_name, **kwargs)
        return result

    def call_claude_code(self, function_name: str, **kwargs) -> Dict[str, Any]:
        """调用 Claude Code 功能"""
        if not self.claude_code:
            return {"success": False, "error": "Claude Code 未找到"}

        method_map = {
            "llm_chat": lambda: self.claude_code.llm_chat(kwargs.get("prompt", "")),
            "code_completion": lambda: self.claude_code.code_completion(kwargs.get("code", "")),
            "debug_assistant": lambda: self.claude_code.debug_assistant(
                kwargs.get("error", ""),
                kwargs.get("context", "")
            ),
            "documentation_generator": lambda: self.claude_code.documentation_generator(kwargs.get("target", "")),
            "test_generator": lambda: self.claude_code.test_generator(kwargs.get("code", ""))
        }

        if function_name in method_map:
            return method_map[function_name]()

        return self.claude_code._call_api(str(kwargs), max_tokens=2000)

    async def call_claude_code_async(self, function_name: str, **kwargs) -> Dict[str, Any]:
        """异步调用 Claude Code 功能"""
        if not self.claude_code:
            return {"success": False, "error": "Claude Code 未找到"}

        result = self.call_claude_code(function_name, **kwargs)
        return result

    def _kwargs_to_args(self, kwargs: Dict[str, Any]) -> List[str]:
        """将 kwargs 转换为命令行参数"""
        args = []
        for key, value in kwargs.items():
            args.append(f"--{key}")
            args.append(str(value))
        return args

    def get_available_functions(self) -> Dict[str, List[str]]:
        """获取可用的功能列表"""
        functions = {
            "openclaw": [],
            "claude_code": []
        }

        if self.openclaw and self.openclaw.is_available():
            functions["openclaw"] = [
                "analyze_code",
                "generate_code",
                "optimize_performance",
                "security_scan"
            ]

        if self.claude_code and self.claude_code.is_available():
            functions["claude_code"] = [
                "code_completion",
                "debug_assistant",
                "documentation_generator",
                "test_generator"
            ]

        return functions

    def is_openclaw_available(self) -> bool:
        """检查 OpenClaw 是否可用"""
        return self.openclaw is not None and self.openclaw.is_available()

    def is_claude_code_available(self) -> bool:
        """检查 Claude Code 是否可用"""
        return self.claude_code is not None and self.claude_code.is_available()


def create_integration_manager(project_root: str = None) -> IntegrationManager:
    """创建集成管理器"""
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return IntegrationManager(project_root)


__all__ = [
    'OpenClawIntegration',
    'ClaudeCodeIntegration',
    'IntegrationManager',
    'create_integration_manager'
]