"""Structured code change logging for autonomous edits."""

from __future__ import annotations

import difflib
import hashlib
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .utils import atomic_write_json, load_json


class CodeChangeLogger:
    """Record auditable source changes made by LengXiaobei."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.path = self.project_root / "memory" / "code_change_logs.json"
        self.path.parent.mkdir(exist_ok=True)

    def snapshot(self, rel_paths: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        snap: Dict[str, Dict[str, Any]] = {}
        for rel_path in sorted({self._normalize(path) for path in rel_paths if path}):
            if not rel_path:
                continue
            path = (self.project_root / rel_path).resolve()
            try:
                path.relative_to(self.project_root)
            except ValueError:
                continue
            if not path.exists() or not path.is_file():
                snap[rel_path] = {"exists": False, "sha256": "", "content": ""}
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            snap[rel_path] = {
                "exists": True,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "content": content,
            }
        return snap

    def record(
        self,
        *,
        actor: str,
        trigger: str,
        summary: str,
        before: Dict[str, Dict[str, Any]],
        after_paths: Iterable[str],
        result: Dict[str, Any],
        verification: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        after = self.snapshot(after_paths)
        files = []
        for rel_path in sorted(set(before) | set(after)):
            before_item = before.get(rel_path, {"exists": False, "sha256": "", "content": ""})
            after_item = after.get(rel_path, {"exists": False, "sha256": "", "content": ""})
            if before_item.get("sha256") == after_item.get("sha256"):
                continue
            files.append({
                "path": rel_path,
                "before_sha256": before_item.get("sha256", ""),
                "after_sha256": after_item.get("sha256", ""),
                "diff": self._diff(rel_path, before_item.get("content", ""), after_item.get("content", "")),
            })

        record = {
            "id": f"change_{int(time.time())}",
            "created_at": time.time(),
            "actor": actor,
            "trigger": trigger,
            "summary": summary,
            "files": files,
            "changed_files": [item["path"] for item in files],
            "result_status": result.get("status", "unknown") if isinstance(result, dict) else "unknown",
            "result": self._compact(result),
            "verification": self._compact(verification or {}),
            "metadata": metadata or {},
            "git_status": self._git_status(),
        }

        records = load_json(str(self.path), default=[])
        if not isinstance(records, list):
            records = []
        records.append(record)
        atomic_write_json(str(self.path), records[-300:])
        return record

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        records = load_json(str(self.path), default=[])
        if not isinstance(records, list):
            return []
        return records[-limit:]

    def _diff(self, rel_path: str, before: str, after: str) -> str:
        return "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            n=3,
        ))[:20000]

    def _git_status(self) -> str:
        try:
            proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.stdout[-4000:]
        except Exception:
            return ""

    @staticmethod
    def _normalize(path: str) -> str:
        normalized = str(path).replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    @staticmethod
    def _compact(value: Dict[str, Any]) -> Dict[str, Any]:
        text_limit = 2000
        if not isinstance(value, dict):
            return {}
        compacted: Dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, str):
                compacted[key] = item[:text_limit]
            elif isinstance(item, dict):
                compacted[key] = CodeChangeLogger._compact(item)
            elif isinstance(item, list):
                compacted[key] = [
                    CodeChangeLogger._compact(x) if isinstance(x, dict) else str(x)[:text_limit]
                    for x in item[:20]
                ]
            else:
                compacted[key] = item
        return compacted
