"""
工具执行层 — 分级权限管控，安全执行用户操作
"""

import shlex
import subprocess
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    success: bool
    output: str
    exit_code: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


class SafetyGate:
    """安全门控：基于白名单 + 黑名单的分级权限控制"""

    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"

    # 允许直接执行的命令白名单
    _ALLOWED_COMMANDS = {
        # 文件查看
        "ls", "cat", "head", "tail", "grep", "find", "wc", "file", "stat",
        "diff", "tree", "du", "df",
        # 系统信息
        "echo", "pwd", "which", "whoami", "hostname", "uname", "date",
        "env", "printenv", "id", "uptime",
        # 开发工具
        "git", "python3", "python", "pip", "pip3", "node", "npm", "npx",
        "cargo", "rustc", "go",
        # 文本处理
        "sort", "uniq", "cut", "tr", "awk", "sed", "xargs",
        # 网络（只读）
        "curl", "wget", "ping", "dig", "nslookup",
        # 压缩
        "tar", "gzip", "gunzip", "zip", "unzip",
        # 其他
        "mkdir", "cp", "mv", "touch", "chmod", "chown",
    }

    # 禁止的命令模式
    _FORBIDDEN_PATTERNS = [
        "rm -rf /", "rm -rf /*", "dd if=", "mkfs.",
        ":(){ :|:& };:",  # fork bomb
    ]

    # 需要确认的高风险命令
    _CONFIRMATION_COMMANDS = {
        "rm", "shutdown", "reboot", "sudo", "kill", "killall",
        "systemctl", "service", "launchctl",
    }

    # 禁止的参数模式
    _FORBIDDEN_ARG_PATTERNS = [
        "-exec rm", "| sh", "| bash", "| python", "| perl",
        "> /dev/sd", "$(rm", "`rm", "&& rm",
    ]

    @classmethod
    def assess(cls, command: str) -> str:
        cmd_stripped = command.strip()
        cmd_lower = cmd_stripped.lower()

        # 检查禁止模式
        for pattern in cls._FORBIDDEN_PATTERNS:
            if pattern.lower() in cmd_lower:
                return cls.RISK_CRITICAL

        # 检查禁止参数模式
        for pattern in cls._FORBIDDEN_ARG_PATTERNS:
            if pattern.lower() in cmd_lower:
                return cls.RISK_CRITICAL

        # 提取命令名
        try:
            parts = shlex.split(cmd_stripped)
        except ValueError:
            # shlex 解析失败（如未闭合引号），视为高风险
            return cls.RISK_HIGH

        if not parts:
            return cls.RISK_MEDIUM

        cmd_name = parts[0]
        # 去掉路径前缀，只取命令名
        if "/" in cmd_name:
            cmd_name = cmd_name.rsplit("/", 1)[-1]

        # 检查是否需要确认
        if cmd_name in cls._CONFIRMATION_COMMANDS:
            return cls.RISK_HIGH

        # 白名单检查
        if cmd_name in cls._ALLOWED_COMMANDS:
            return cls.RISK_LOW

        return cls.RISK_MEDIUM

    @classmethod
    def is_allowed(cls, command: str) -> bool:
        return cls.assess(command) != cls.RISK_CRITICAL

    @classmethod
    def needs_confirmation(cls, command: str) -> bool:
        return cls.assess(command) in (cls.RISK_HIGH, cls.RISK_CRITICAL)


class Executor:
    """工具执行器，带安全门控和超时控制"""

    MAX_HISTORY = 200

    def __init__(self, config):
        self.config = config
        self.default_timeout = int(config.get("tools", "timeout", default=30))
        self.max_retries = int(config.get("tools", "max_retries", default=3))
        self.history: deque = deque(maxlen=self.MAX_HISTORY)

    def run(self, command: str, *, timeout: Optional[int] = None,
            requires_approval: Optional[Callable[[str], bool]] = None) -> ExecResult:
        risk = SafetyGate.assess(command)
        if risk == SafetyGate.RISK_CRITICAL:
            return ExecResult(success=False, output="高危命令已拦截，不允许执行", exit_code=-1)

        if SafetyGate.needs_confirmation(command):
            if requires_approval is None or not requires_approval(command):
                return ExecResult(
                    success=False,
                    output=f"命令需要用户确认 (风险等级: {risk}): {command}",
                    exit_code=-1,
                )

        timeout = timeout or self.default_timeout
        try:
            # 优先使用 shlex.split 避免命令注入
            try:
                args = shlex.split(command)
                proc = subprocess.run(
                    args, capture_output=True, text=True, timeout=timeout,
                )
            except ValueError:
                # shlex 解析失败时回退到 shell=True（仅对低风险命令）
                if risk != SafetyGate.RISK_LOW:
                    return ExecResult(
                        success=False,
                        output=f"命令格式异常且风险等级非低，拒绝执行",
                        exit_code=-1,
                    )
                proc = subprocess.run(
                    command, shell=True, capture_output=True, text=True, timeout=timeout,
                )

            result = ExecResult(
                success=proc.returncode == 0,
                output=proc.stdout if proc.stdout else proc.stderr,
                exit_code=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            result = ExecResult(success=False, output=f"命令超时 ({timeout}s)", exit_code=-1)
        except FileNotFoundError as e:
            result = ExecResult(success=False, output=f"命令未找到: {e}", exit_code=-1)
        except Exception as e:
            result = ExecResult(success=False, output=str(e), exit_code=-1)

        self.history.append(result)
        return result

    def run_safe(self, command: str, **kwargs) -> ExecResult:
        """执行只读类命令（低风险命令跳过确认）"""
        risk = SafetyGate.assess(command)
        if risk == SafetyGate.RISK_CRITICAL:
            return ExecResult(success=False, output="高危命令已拦截", exit_code=-1)
        # 低风险命令直接执行，跳过确认
        if risk == SafetyGate.RISK_LOW:
            return self.run(command, requires_approval=lambda _: True, **kwargs)
        return self.run(command, **kwargs)
