"""Filesystem tools.

参考来源：OpenClaw Toolkits 的文件工具：所有路径必须限制在项目根目录内。
"""

from __future__ import annotations

from pathlib import Path


def read_text(path: str, root: Path, limit: int = 12000) -> str:
    """安全读取项目内文本文件。"""
    target = (root / path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise ValueError("path escapes project root")
    return target.read_text(encoding="utf-8", errors="replace")[:limit]
