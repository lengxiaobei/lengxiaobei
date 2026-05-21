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
    """安全门控：基于白名单 + 黑名单的5级权限控制（对齐 AUTONOMY.md）"""

    RISK_LOW = "low"              # 可自主执行
    RISK_MEDIUM = "medium"        # 可自主执行但需记录
    RISK_HIGH = "high"            # 必须先确认
    RISK_CRITICAL = "critical"    # 默认禁止，除非宿主明确授权
    RISK_FORBIDDEN = "forbidden"  # 永久禁止

    # 低风险命令白名单 — 仅限真正只读/无副作用的命令
    _LOW_RISK_COMMANDS = {
        # 文件查看（只读）
        "ls", "cat", "head", "tail", "grep", "find", "wc", "file", "stat",
        "diff", "tree", "du", "df",
        # 系统信息（只读）
        "echo", "pwd", "which", "whoami", "hostname", "uname", "date",
        "env", "printenv", "id", "uptime",
        # 文本处理（只读管道）
        "sort", "uniq", "cut", "tr", "awk",
        # 网络探测（只读）
        "ping", "dig", "nslookup",
    }

    # 中等风险 — 可执行但副作用有限，自主运行时可执行但需记录
    _MEDIUM_RISK_COMMANDS = {
        # 压缩/解压（可创建/覆盖文件）
        "tar", "gzip", "gunzip", "zip", "unzip",
        # 文本处理（可原地修改，但通常用于管道）
        "sed",
        # 管道组合
        "xargs",
    }

    # 高风险命令 — 需明确确认
    # 包含：可执行任意代码、可安装软件、可推送代码、可下载文件、可修改文件系统
    _HIGH_RISK_COMMANDS = {
        # 破坏性操作
        "rm", "shutdown", "reboot", "sudo", "kill", "killall",
        "systemctl", "service", "launchctl",
        # 文件修改操作
        "mkdir", "cp", "mv", "touch", "chmod", "chown",
        # 开发工具（可执行任意代码：python -c "..."）
        "python3", "python", "node", "cargo", "rustc", "go",
        # 包管理器（可安装/修改环境）
        "pip", "pip3", "npm", "npx",
        # 网络下载（可写入文件/下载恶意内容）
        "curl", "wget",
    }

    # 极高风险 — 默认禁止，除非宿主明确授权
    _CRITICAL_RISK_COMMANDS = {
        # 支付/采购相关
        "stripe", "paypal", "aws", "gcloud", "az",
        # 发布相关
        "docker", "kubectl", "helm",
        # 宿主身份
        "ssh", "scp", "rsync",
    }

    # 永久禁止 — 对齐 AUTONOMY.md 安全底线
    _FORBIDDEN_PATTERNS = [
        "rm -rf /", "rm -rf /*", "dd if=", "mkfs.",
        ":(){ :|:& };:",  # fork bomb
        # 违法/攻击
        "nmap -sS", "hydra", "sqlmap", "metasploit",
        # 隐私泄露
        "keychain", "security find-generic-password",
        # 绕过宿主
        "launchctl load", "defaults write loginwindow",
    ]

    # 禁止的参数模式
    _FORBIDDEN_ARG_PATTERNS = [
        "-exec rm", "| sh", "| bash", "| python", "| perl",
        "> /dev/sd", "$(rm", "`rm", "&& rm",
    ]

    @classmethod
    def assess(cls, command: str) -> str:
        cmd_stripped = command.strip()
        cmd_lower = cmd_stripped.lower()

        # 检查永久禁止模式
        for pattern in cls._FORBIDDEN_PATTERNS:
            if pattern.lower() in cmd_lower:
                return cls.RISK_FORBIDDEN

        # 检查禁止参数模式
        for pattern in cls._FORBIDDEN_ARG_PATTERNS:
            if pattern.lower() in cmd_lower:
                return cls.RISK_FORBIDDEN

        # 提取命令名
        try:
            parts = shlex.split(cmd_stripped)
        except ValueError:
            return cls.RISK_HIGH

        if not parts:
            return cls.RISK_MEDIUM

        cmd_name = parts[0]
        if "/" in cmd_name:
            cmd_name = cmd_name.rsplit("/", 1)[-1]

        # git 按子命令细分风险等级
        if cmd_name == "git" and len(parts) >= 2:
            subcmd = parts[1]
            # 只读子命令 -> low
            git_readonly = {"status", "diff", "log", "show", "branch", "tag",
                            "remote", "stash", "blame", "shortlog", "describe",
                            "reflog", "ls-files", "ls-remote", "rev-parse"}
            if subcmd in git_readonly:
                return cls.RISK_LOW
            # 写操作子命令 -> high
            git_write = {"add", "commit", "reset", "checkout", "merge", "rebase",
                         "cherry-pick", "stash pop", "stash drop", "branch -d",
                         "branch -D", "tag -d", "clean", "restore", "switch"}
            if subcmd in git_write:
                return cls.RISK_HIGH
            # 发布子命令 -> critical
            git_publish = {"push", "fetch", "pull", "clone", "submodule"}
            if subcmd in git_publish:
                return cls.RISK_CRITICAL
            # 其他 git 子命令默认 high
            return cls.RISK_HIGH

        # 极高风险
        if cmd_name in cls._CRITICAL_RISK_COMMANDS:
            return cls.RISK_CRITICAL

        # 高风险
        if cmd_name in cls._HIGH_RISK_COMMANDS:
            return cls.RISK_HIGH

        # 低风险
        if cmd_name in cls._LOW_RISK_COMMANDS:
            return cls.RISK_LOW

        # 中等风险
        if cmd_name in cls._MEDIUM_RISK_COMMANDS:
            return cls.RISK_MEDIUM

        return cls.RISK_MEDIUM

    @classmethod
    def is_allowed(cls, command: str) -> bool:
        return cls.assess(command) not in (cls.RISK_CRITICAL, cls.RISK_FORBIDDEN)

    @classmethod
    def needs_confirmation(cls, command: str) -> bool:
        return cls.assess(command) in (cls.RISK_HIGH, cls.RISK_CRITICAL, cls.RISK_FORBIDDEN)


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
        if risk == SafetyGate.RISK_FORBIDDEN:
            return ExecResult(success=False, output="永久禁止的命令，不可执行", exit_code=-1)
        if risk == SafetyGate.RISK_CRITICAL:
            return ExecResult(success=False, output="极高风险命令，需宿主明确授权", exit_code=-1)

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
        """执行只读类命令（仅低风险命令跳过确认）"""
        risk = SafetyGate.assess(command)
        if risk in (SafetyGate.RISK_FORBIDDEN, SafetyGate.RISK_CRITICAL):
            return ExecResult(success=False, output=f"风险等级 {risk}，已拦截", exit_code=-1)
        # 仅低风险命令直接执行，跳过确认
        if risk == SafetyGate.RISK_LOW:
            return self.run(command, requires_approval=lambda _: True, **kwargs)
        # 中等和高风险走正常确认流程
        return self.run(command, **kwargs)
