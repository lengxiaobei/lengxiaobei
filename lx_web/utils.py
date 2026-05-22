"""lx_web utilities — helper functions extracted from lx_web.py for modularity."""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def jsonable(value):
    """Recursively convert value to JSON-serializable form."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    if hasattr(value, "__dict__"):
        return jsonable(value.__dict__)
    return str(value)


def read_excerpt(project_root: Path, rel_path: str, limit: int = 900) -> str:
    """Read a small excerpt from a file in project_root."""
    path = project_root / rel_path
    if not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""
    if len(content) <= limit:
        return content
    return content[:limit].rstrip() + "\n..."


def read_allowed_file(project_root: Path, readable_files: set, rel_path: str, limit: int = 12000) -> dict:
    """Read a file if it's in the allowed whitelist."""
    if not rel_path:
        return {"status": "error", "error": "missing path parameter"}
    if rel_path not in readable_files:
        return {"status": "error", "error": f"file not in readable whitelist: {rel_path}"}
    path = project_root / rel_path
    if not path.is_file():
        return {"status": "error", "error": f"file not found: {rel_path}"}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"status": "error", "error": str(e)}
    if len(content) > limit:
        content = content[:limit] + "\n... (truncated)"
    return {"status": "ok", "path": rel_path, "content": content, "size": len(content)}


def records_summary(project_root: Path, rel_path: str) -> dict:
    """Summarize a JSON records file."""
    path = project_root / rel_path
    if not path.is_file():
        return {"count": 0, "status": "not_found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = None
    return {
        "path": rel_path,
        "count": len(data) if isinstance(data, list) else (len(data) if isinstance(data, dict) else 0),
        "type": "list" if isinstance(data, list) else type(data).__name__,
    }


def atomic_record_list(path: Path, record: dict, max_records: int = 200) -> None:
    """Atomically append a record to a JSON list file."""
    records = []
    if path.exists():
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            records = []
    if not isinstance(records, list):
        records = []
    records.append(record)
    if len(records) > max_records:
        records = records[-max_records:]
    tmp = path.with_name(f".{path.name}.tmp-{int(time.time() * 1000)}")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_pending_lessons(project_root: Path, limit: int = 5) -> list:
    """Load pending agent lessons."""
    path = project_root / "memory" / "agent_lessons.json"
    if not path.is_file():
        return []
    try:
        lessons = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(lessons, list):
        return []
    pending = [item for item in lessons if isinstance(item, dict) and item.get("status") == "pending"]
    return pending[:limit]


def load_learning_plan(project_root: Path) -> list:
    """Load autonomy learning plan."""
    path = project_root / "memory" / "autonomy_learning_plan.json"
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_learning_plan(project_root: Path, plan: list) -> None:
    """Save autonomy learning plan."""
    path = project_root / "memory" / "autonomy_learning_plan.json"
    tmp = path.with_name(f".{path.name}.tmp-{int(time.time() * 1000)}")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def next_learning_topic(project_root: Path) -> dict:
    """Get the next pending learning topic."""
    plan = load_learning_plan(project_root)
    pending = [item for item in plan if isinstance(item, dict) and item.get("status") in ("pending", "failed")]
    return pending[0] if pending else {"status": "none", "message": "no topics in plan"}


def mark_learning_topic(project_root: Path, topic_id: str, updates: dict) -> None:
    """Update a learning topic's status."""
    plan = load_learning_plan(project_root)
    for item in plan:
        if isinstance(item, dict) and item.get("id") == topic_id:
            item.update(updates)
            break
    save_learning_plan(project_root, plan)


def extract_repair_targets(project_root: Path, test_result: dict, limit: int = 3) -> list:
    """Extract fixable source file paths from test failure output."""
    import re

    text = ""
    outputs = test_result.get("outputs") or []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        if item.get("returncode") == 0:
            continue
        if item.get("stdout"):
            text += str(item.get("stdout", ""))
        if item.get("stderr"):
            text += str(item.get("stderr", ""))

    if not text:
        return []

    candidates = []
    patterns = [
        r"['\"]((?:src/[^'\"]+|lx_web)\.py)['\"]",
        r'File "([^"]+)"',
        r"((?:src|tests)/[A-Za-z0-9_./-]+\.py|lx_web\.py)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            raw = str(match).strip()
            path = Path(raw)
            try:
                if path.is_absolute():
                    rel = path.resolve().relative_to(project_root)
                    raw = str(rel)
            except Exception:
                continue
            raw = raw.replace("\\", "/").strip("./")
            if raw == "lx_web.py" or raw.startswith("src/"):
                if (project_root / raw).is_file() and raw not in candidates:
                    candidates.append(raw)
            if len(candidates) >= limit:
                return candidates
    return candidates


def test_failure_text(test_result: dict, limit: int = 3000) -> str:
    """Extract failure text from test result."""
    outputs = test_result.get("outputs") or []
    chunks = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        if item.get("returncode") == 0:
            continue
        chunks.append(f"$ {item.get('command', '')}")
        if item.get("stdout"):
            chunks.append(str(item["stdout"]))
        if item.get("stderr"):
            chunks.append(str(item["stderr"]))
    return "\n".join(chunks)[-limit:]