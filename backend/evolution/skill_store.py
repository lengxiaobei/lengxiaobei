"""YAML/SQLite skill storage and review queue.

参考来源：Hermes 的技能仓库：生成技能不直接启用，而是写入 pending 队列，
由人工审核或评估器推进状态。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SkillStore:
    """文件系统 + SQLite 技能仓库。"""

    def __init__(self, skills_dir: Path, sqlite: Any | None = None):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite = sqlite

    def save(self, skill: dict[str, Any]) -> Path:
        """保存 pending 技能草稿，局部参考 Hermes skill_store。"""
        name = self._safe_name(str(skill.get("name") or "skill"))
        skill["name"] = name
        path = self.skills_dir / f"{name}.yaml"
        body = "# Reference: Hermes skill-store; pending by default for human review\n"
        body += json.dumps(skill, ensure_ascii=False, indent=2)
        path.write_text(body, encoding="utf-8")
        if self.sqlite:
            self.sqlite.upsert_skill(name, str(skill.get("trigger") or "manual"), skill, str(skill.get("status") or "pending"))
        return path

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        items = self.sqlite.list_skills(status=status) if self.sqlite else []
        by_name = {item["name"]: item for item in items}
        for path in sorted(self.skills_dir.glob("*.yaml")):
            if path.stem not in by_name:
                by_name[path.stem] = {"name": path.stem, "path": str(path), "status": self._status(path), "body": self.load(path.stem) or {}}
            else:
                by_name[path.stem]["path"] = str(path)
        return sorted(by_name.values(), key=lambda item: item.get("updated_at", 0), reverse=True)

    def load(self, name: str) -> dict[str, Any] | None:
        safe = self._safe_name(name)
        if self.sqlite:
            record = self.sqlite.get_skill(safe)
            if record:
                return record.get("body") or record
        path = self.skills_dir / f"{safe}.yaml"
        if not path.exists():
            return None
        text = "\n".join(line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if not line.startswith("#"))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"name": safe, "status": self._status(path), "raw": text}

    def set_status(self, name: str, status: str) -> dict[str, Any] | None:
        safe = self._safe_name(name)
        skill = self.load(safe)
        if not skill:
            return None
        skill["status"] = status
        self.save(skill)
        if self.sqlite:
            return self.sqlite.update_skill_status(safe, status)
        return skill

    def record_result(self, name: str, ok: bool) -> None:
        if self.sqlite:
            self.sqlite.record_skill_result(self._safe_name(name), ok)

    def _status(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        return "approved" if '"status": "approved"' in text or "status: approved" in text else "pending"

    def _safe_name(self, name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "skill"
