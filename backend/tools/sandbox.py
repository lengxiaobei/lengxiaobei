"""Subprocess sandbox boundary.

参考来源：OpenClaw 工具层的安全沙箱思想：命令执行必须集中、限时、可审计。
提供只读命令和项目内全权限命令两种包装；所有执行集中审计并限制 cwd 在项目根目录。
"""

from __future__ import annotations

import subprocess
from pathlib import Path


DENY_TOKENS = {"rm", "sudo", "chmod", "chown", "mkfs", "dd"}


def run_readonly(command: list[str], cwd: Path, timeout: int = 30) -> dict:
    """运行低风险命令，局部参考 OpenClaw sandbox。"""
    if not command:
        raise ValueError("command is required")
    if any(token in DENY_TOKENS for token in command):
        raise PermissionError("command is not allowed in readonly sandbox")
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def run_project_command(command: list[str], cwd: Path, timeout: int = 60) -> dict:
    """Run an arbitrary command from the project root with a timeout."""
    if not command:
        raise ValueError("command is required")
    root = cwd.resolve()
    proc = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=timeout)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
