"""
工具执行层 — 分级权限管控，安全执行用户操作
"""

import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ExecResult:
    success: bool
    output: str
    exit_code: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


class SafetyGate:
    """安全门控：根据风险等级决定是否放行"""

    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"

    _FORBIDDEN_COMMANDS = ["rm -rf /", "dd if=", "mkfs.", ":(){ :|:& };:"]
    _CONFIRMATION_REQUIRED = ["rm ", "shutdown", "reboot", "sudo ", "chmod 777"]
    _READ_ONLY = ["ls", "cat", "head", "tail", "grep", "find", "wc", "file", "stat",
                  "echo", "pwd", "which", "whoami", "hostname", "uname", "date"]

    @classmethod
    def assess(cls, command: str) -> str:
        cmd_lower = command.strip().lower()
        for fb in cls._FORBIDDEN_COMMANDS:
            if fb.lower() in cmd_lower:
                return cls.RISK_CRITICAL
        for cr in cls._CONFIRMATION_REQUIRED:
            if cr.lower() in cmd_lower:
                return cls.RISK_HIGH
        first_word = cmd_lower.split()[0] if cmd_lower.split() else ""
        if first_word in cls._READ_ONLY:
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

    def __init__(self, config):
        self.config = config
        self.default_timeout = int(config.get("tools", "timeout", default=30))
        self.max_retries = int(config.get("tools", "max_retries", default=3))
        self.history: List[ExecResult] = []

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
        except Exception as e:
            result = ExecResult(success=False, output=str(e), exit_code=-1)

        self.history.append(result)
        return result

    def run_safe(self, command: str, **kwargs) -> ExecResult:
        """执行只读类命令（绕过确认），其他命令通过正常流程"""
        return self.run(command, **kwargs)