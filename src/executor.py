"""
工具执行层 — 三级权限管控，对齐 hard_boundary

三类：
- ALLOWED            — 只读/诊断命令，直接执行
- NEEDS_CONFIRMATION — 涉及写操作/安装/发布/身份，需确认
- FORBIDDEN          — 攻击/破坏/隐私泄露，绝对禁止
"""

import shlex
import subprocess
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from .hard_boundary import BoundaryResult

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    success: bool
    output: str
    exit_code: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


class SafetyGate:
    """
    安全门控 — 三级分类，对齐 hard_boundary

    云模型判断好坏，本地只做底线拦截：
    - ALLOWED: 只读命令，直接放行
    - NEEDS_CONFIRMATION: 写操作/安装/发布/身份，需宿主确认
    - FORBIDDEN: 攻击/破坏/隐私泄露，绝对禁止
    """

    # 允许自主执行的命令 — 只读/无副作用
    _ALLOWED_COMMANDS = {
        # 文件查看
        "ls", "cat", "head", "tail", "grep", "find", "wc", "file", "stat",
        "diff", "tree", "du", "df",
        # 系统信息
        "echo", "pwd", "which", "whoami", "hostname", "uname", "date",
        "env", "printenv", "id", "uptime",
        # 文本处理（管道）
        "sort", "uniq", "cut", "tr", "awk",
        # 网络探测
        "ping", "dig", "nslookup",
        # 压缩查看
        "tar", "gzip", "gunzip", "zip", "unzip",
        # 文本替换（通常用于管道）
        "sed",
        # 管道组合
        "xargs",
    }

    # 需确认的命令 — 涉及写操作/安装/发布/身份
    _NEEDS_CONFIRMATION_COMMANDS = {
        # 文件修改
        "mkdir", "cp", "mv", "touch", "chmod", "chown",
        # 开发工具（可执行任意代码）
        "python3", "python", "node", "cargo", "rustc", "go",
        # 包管理器
        "pip", "pip3", "npm", "npx",
        # 网络下载
        "curl", "wget",
        # 破坏性操作
        "rm", "kill", "killall",
        # 发布/部署
        "docker", "kubectl", "helm",
        # 宿主身份
        "ssh", "scp", "rsync",
        # 云资源
        "aws", "gcloud", "az",
    }

    # 绝对禁止的模式
    _FORBIDDEN_PATTERNS = [
        "rm -rf /", "rm -rf /*", "dd if=", "mkfs.",
        ":(){ :|:& };:",  # fork bomb
        "nmap -sS", "hydra", "sqlmap", "metasploit",
        "keychain", "security find-generic-password",
        "launchctl load", "defaults write loginwindow",
    ]

    _FORBIDDEN_ARG_PATTERNS = [
        "-exec rm", "| sh", "| bash", "| python", "| perl",
        "> /dev/sd", "$(rm", "`rm", "&& rm",
    ]

    @classmethod
    def assess(cls, command: str) -> BoundaryResult:
        """评估命令的三级分类"""
        cmd_stripped = command.strip()
        cmd_lower = cmd_stripped.lower()

        # 绝对禁止
        for pattern in cls._FORBIDDEN_PATTERNS:
            if pattern.lower() in cmd_lower:
                return BoundaryResult.FORBIDDEN
        for pattern in cls._FORBIDDEN_ARG_PATTERNS:
            if pattern.lower() in cmd_lower:
                return BoundaryResult.FORBIDDEN

        # 提取命令名
        try:
            parts = shlex.split(cmd_stripped)
        except ValueError:
            return BoundaryResult.NEEDS_CONFIRMATION

        if not parts:
            return BoundaryResult.ALLOWED

        cmd_name = parts[0]
        if "/" in cmd_name:
            cmd_name = cmd_name.rsplit("/", 1)[-1]

        # git 按子命令细分
        if cmd_name == "git" and len(parts) >= 2:
            subcmd = parts[1]
            git_readonly = {"status", "diff", "log", "show", "branch", "tag",
                            "remote", "stash", "blame", "shortlog", "describe",
                            "reflog", "ls-files", "ls-remote", "rev-parse"}
            if subcmd in git_readonly:
                return BoundaryResult.ALLOWED
            # git push/fetch/pull 涉及发布到远程
            git_publish = {"push", "fetch", "pull", "clone", "submodule"}
            if subcmd in git_publish:
                return BoundaryResult.NEEDS_CONFIRMATION
            # 其他 git 子命令（add/commit/merge 等）
            return BoundaryResult.NEEDS_CONFIRMATION

        # sudo / shutdown / reboot — 需确认
        if cmd_name in ("sudo", "shutdown", "reboot", "systemctl", "service", "launchctl"):
            return BoundaryResult.NEEDS_CONFIRMATION

        # 需确认
        if cmd_name in cls._NEEDS_CONFIRMATION_COMMANDS:
            return BoundaryResult.NEEDS_CONFIRMATION

        # 允许
        if cmd_name in cls._ALLOWED_COMMANDS:
            return BoundaryResult.ALLOWED

        # 未知命令默认需确认
        return BoundaryResult.NEEDS_CONFIRMATION

    @classmethod
    def is_allowed(cls, command: str) -> bool:
        return cls.assess(command) != BoundaryResult.FORBIDDEN

    @classmethod
    def needs_confirmation(cls, command: str) -> bool:
        return cls.assess(command) == BoundaryResult.NEEDS_CONFIRMATION


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
        boundary = SafetyGate.assess(command)

        if boundary == BoundaryResult.FORBIDDEN:
            return ExecResult(success=False, output="绝对禁止的命令", exit_code=-1)

        if boundary == BoundaryResult.NEEDS_CONFIRMATION:
            if requires_approval is None or not requires_approval(command):
                return ExecResult(
                    success=False,
                    output=f"命令需宿主确认: {command}",
                    exit_code=-1,
                )

        timeout = timeout or self.default_timeout
        try:
            try:
                args = shlex.split(command)
                proc = subprocess.run(
                    args, capture_output=True, text=True, timeout=timeout,
                )
            except ValueError:
                # shlex 解析失败，拒绝执行（不再回退 shell=True）
                return ExecResult(
                    success=False,
                    output="命令格式异常，拒绝执行",
                    exit_code=-1,
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
        """执行只读类命令（仅 ALLOWED 命令跳过确认）"""
        boundary = SafetyGate.assess(command)
        if boundary == BoundaryResult.FORBIDDEN:
            return ExecResult(success=False, output="绝对禁止的命令", exit_code=-1)
        if boundary == BoundaryResult.ALLOWED:
            return self.run(command, requires_approval=lambda _: True, **kwargs)
        # NEEDS_CONFIRMATION 走正常确认流程
        return self.run(command, **kwargs)
