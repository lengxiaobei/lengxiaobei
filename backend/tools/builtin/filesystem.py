"""Filesystem tools.

参考来源：OpenClaw Toolkits 的文件工具：所有路径必须限制在项目根目录内。
"""

from __future__ import annotations

from pathlib import Path


PROTECTED_NAMES = {".env", ".env.local"}


def _resolve_project_path(path: str, root: Path) -> Path:
    target = (root / path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise ValueError("path escapes project root")
    if target.name in PROTECTED_NAMES:
        raise PermissionError("refusing to expose local secret/config file")
    return target


def read_text(path: str, root: Path, limit: int = 12000) -> str:
    """安全读取项目内文本文件。"""
    target = _resolve_project_path(path, root)
    return target.read_text(encoding="utf-8", errors="replace")[:limit]


def write_text(path: str, content: str, root: Path, create_parents: bool = True) -> dict:
    """Write a text file inside the project root."""
    target = _resolve_project_path(path, root)
    if create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": str(target.relative_to(root.resolve())), "bytes": len(content.encode("utf-8"))}


def append_text(path: str, content: str, root: Path, create_parents: bool = True) -> dict:
    """Append text to a file inside the project root."""
    target = _resolve_project_path(path, root)
    if create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(content)
    return {"path": str(target.relative_to(root.resolve())), "bytes": len(content.encode("utf-8"))}


def delete_path(path: str, root: Path) -> dict:
    """Delete a file inside the project root."""
    target = _resolve_project_path(path, root)
    if target.is_dir():
        raise IsADirectoryError("filesystem_delete only deletes files")
    target.unlink(missing_ok=True)
    return {"path": str(target.relative_to(root.resolve())), "deleted": True}


def edit_text(path: str, old_string: str, new_string: str, root: Path) -> dict:
    """Precisely replace a substring in a text file inside the project root.

    Mirrors Claude Code's Edit tool: the old_string must match exactly once.
    """
    target = _resolve_project_path(path, root)
    original = target.read_text(encoding="utf-8", errors="replace")
    occurrences = original.count(old_string)
    if occurrences == 0:
        raise ValueError(f"old_string not found in {path}")
    if occurrences > 1:
        raise ValueError(f"old_string appears {occurrences} times in {path}; must be unique for precise edit")
    updated = original.replace(old_string, new_string, 1)
    target.write_text(updated, encoding="utf-8")
    return {
        "path": str(target.relative_to(root.resolve())),
        "replaced": True,
        "old_length": len(old_string),
        "new_length": len(new_string),
    }


def list_files(path: str = ".", root: Path | None = None, recursive: bool = False) -> dict:
    """List files and directories inside the project root."""
    target_root = root or Path(".")
    target = _resolve_project_path(path, target_root)
    if not target.exists():
        return {"path": str(target.relative_to(target_root.resolve())), "error": "path does not exist", "entries": []}
    if target.is_file():
        return {
            "path": str(target.relative_to(target_root.resolve())),
            "type": "file",
            "size": target.stat().st_size,
            "entries": [],
        }
    entries = []
    if recursive:
        for item in sorted(target.rglob("*")):
            rel = str(item.relative_to(target_root.resolve()))
            if "__pycache__" in rel or ".git" in rel.split("/") or ".venv" in rel:
                continue
            entries.append({
                "path": rel,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
    else:
        for item in sorted(target.iterdir()):
            rel = str(item.relative_to(target_root.resolve()))
            if item.name.startswith(".") and item.name not in {".github", ".claude"}:
                continue
            entries.append({
                "path": rel,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
    return {
        "path": str(target.relative_to(target_root.resolve())),
        "type": "directory",
        "entries": entries,
    }
