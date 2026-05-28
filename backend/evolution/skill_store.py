"""YAML/SQLite skill storage and review queue.

参考来源：Hermes 的技能仓库：生成技能不直接启用，而是写入 pending 队列，
由人工审核或评估器推进状态。
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SkillStore:
    """文件系统 + SQLite 技能仓库。"""

    def __init__(self, skills_dir: Path, sqlite: Any | None = None):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite = sqlite

    def save(self, skill: dict[str, Any], *, source_run_id: str | None = None) -> Path:
        """保存 pending 技能草稿，局部参考 Hermes skill_store。"""
        import time

        name = self._safe_name(str(skill.get("name") or "skill"))
        skill = dict(skill)
        now = time.time()
        skill["name"] = name
        skill.setdefault("created_at", now)
        skill["updated_at"] = now
        if source_run_id:
            skill["source_run_id"] = source_run_id
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
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse skill file %s: %s", name, e)
            return {"name": safe, "status": self._status(path), "raw": text}

    def set_status(self, name: str, status: str) -> dict[str, Any] | None:
        return self.review(name=name, status=status)

    def review(
        self,
        name: str,
        status: str,
        *,
        reviewer: str = "human",
        notes: str | None = None,
        evidence: list[str] | None = None,
        checks: dict[str, Any] | None = None,
        rollback_plan: str | None = None,
    ) -> dict[str, Any] | None:
        safe = self._safe_name(name)
        skill = self.load(safe)
        if not skill:
            return None
        skill["status"] = status
        review = {
            "status": status,
            "reviewer": reviewer or "human",
            "notes": notes,
            "evidence": list(evidence or []),
            "checks": dict(checks or {}),
            "rollback_plan": rollback_plan,
            "reviewed_at": time.time(),
        }
        history = list(skill.get("review_history") or [])
        history.append(review)
        skill["review_history"] = history
        skill["latest_review"] = review
        self.save(skill)
        return self.load(safe)

    def record_result(self, name: str, ok: bool) -> None:
        if self.sqlite:
            self.sqlite.record_skill_result(self._safe_name(name), ok)

    def get_stats(self, name: str) -> dict[str, Any] | None:
        """Get skill with success rate stats."""
        if self.sqlite:
            return self.sqlite.get_skill_stats(self._safe_name(name))
        return self.load(name)

    def list_with_stats(self, status: str | None = None) -> list[dict[str, Any]]:
        """List skills with success rate, sorted by success_rate desc."""
        if self.sqlite:
            return self.sqlite.list_skills_with_stats(status=status)
        return self.list(status=status)

    def auto_demote(self, min_uses: int = 5, min_success_rate: float = 30.0) -> list[str]:
        """Auto-demote skills with low success rate. Returns demoted skill names."""
        if not self.sqlite:
            return []
        return self.sqlite.auto_demote_skills(min_uses=min_uses, min_success_rate=min_success_rate)

    def upgrade_version(self, name: str) -> int:
        """Increment skill version. Returns new version number."""
        if not self.sqlite:
            return 0
        return self.sqlite.upgrade_skill_version(self._safe_name(name))

    def _status(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        return "approved" if '"status": "approved"' in text or "status: approved" in text else "pending"

    def _safe_name(self, name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "skill"
