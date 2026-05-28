"""Hermes-style SKILL.md skill system for lengxiaobei.

Parses YAML frontmatter + Markdown body, stores as files on disk.
Compatible with Hermes SKILL.md format.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any


# ── Frontmatter parser ──────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_skill_md(text: str) -> tuple[dict[str, Any], str]:
    """Parse SKILL.md into (frontmatter_dict, markdown_body)."""
    meta: dict[str, Any] = {}
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m:
        raw_yaml = m.group(1)
        body = text[m.end():]
        meta = _parse_yaml_lite(raw_yaml)
    return meta, body


def _parse_yaml_lite(raw: str) -> dict[str, Any]:
    """Minimal YAML parser for flat key-value + lists. No PyYAML dep needed."""
    result: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Key: value
        if ":" in stripped and not stripped.startswith("-"):
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                current_key = key
                result[key] = []
            elif val.startswith("[") and val.endswith("]"):
                # Inline list [a, b, c]
                items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
                result[key] = items
            elif val.startswith("'") and val.endswith("'"):
                result[key] = val[1:-1]
            elif val.startswith('"') and val.endswith('"'):
                result[key] = val[1:-1]
            else:
                # Try int/float/bool
                result[key] = _coerce(val)
            current_key = key if isinstance(result.get(key), list) else None
        elif stripped.startswith("- ") and current_key:
            item = stripped[2:].strip().strip('"').strip("'")
            result[current_key].append(item)
    return result


def _coerce(val: str) -> Any:
    if val.lower() in ("true", "yes"):
        return True
    if val.lower() in ("false", "no"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def render_skill_md(meta: dict[str, Any], body: str) -> str:
    """Render a skill back to SKILL.md format."""
    lines = ["---"]
    for key, val in meta.items():
        if isinstance(val, list):
            lines.append(f"{key}: [{', '.join(str(v) for v in val)}]")
        elif isinstance(val, bool):
            lines.append(f"{key}: {'true' if val else 'false'}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    lines.append("")
    lines.append(body.strip())
    return "\n".join(lines) + "\n"


# ── Skill MD Store ──────────────────────────────────────────────────

class SkillMDStore:
    """File-based skill store using SKILL.md format.

    Skills are stored as individual SKILL.md files under a base directory,
    optionally organized by category subdirectories.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def load_from_dir(self, path: Path | None = None) -> list[dict[str, Any]]:
        """Recursively scan a directory for SKILL.md files."""
        scan_dir = path or self.base_dir
        skills: list[dict[str, Any]] = []
        if not scan_dir.exists():
            return skills
        for root, _dirs, files in os.walk(scan_dir):
            for fname in files:
                if fname == "SKILL.md":
                    fpath = Path(root) / fname
                    skill = self._load_file(fpath)
                    if skill:
                        skills.append(skill)
        return skills

    def get(self, name: str) -> dict[str, Any] | None:
        """Get a skill by name."""
        for skill in self.load_from_dir():
            if skill.get("name") == name:
                return skill
        return None

    def list_skills(
        self,
        category: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """List skills with optional filtering."""
        scan_dir = self.base_dir / category if category else self.base_dir
        skills = self.load_from_dir(scan_dir)
        if tag:
            skills = [s for s in skills if tag in (s.get("tags") or [])]
        return skills

    def save(self, skill: dict[str, Any]) -> Path:
        """Save a skill as a SKILL.md file. Returns the file path."""
        name = skill.get("name", "unnamed")
        category = skill.get("category", "")
        skill_dir = self.base_dir / category / name if category else self.base_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        meta = {k: v for k, v in skill.items() if k not in ("body", "content", "_path")}
        body = skill.get("body") or skill.get("content") or ""
        content = render_skill_md(meta, body)

        fpath = skill_dir / "SKILL.md"
        fpath.write_text(content, encoding="utf-8")
        return fpath

    def patch(self, name: str, old_string: str, new_string: str) -> dict[str, Any] | None:
        """Patch a skill's body by replacing old_string with new_string."""
        skill = self.get(name)
        if not skill:
            return None
        fpath = skill.get("_path")
        if not fpath:
            return None
        text = Path(fpath).read_text(encoding="utf-8")
        if old_string not in text:
            return {"error": "old_string not found in skill content"}
        updated = text.replace(old_string, new_string, 1)
        Path(fpath).write_text(updated, encoding="utf-8")
        return self._load_file(Path(fpath))

    def delete(self, name: str) -> bool:
        """Delete a skill directory."""
        for skill in self.load_from_dir():
            if skill.get("name") == name:
                fpath = skill.get("_path")
                if fpath:
                    p = Path(fpath)
                    if p.exists():
                        p.unlink()
                        # Remove empty parent dirs
                        try:
                            p.parent.rmdir()
                        except OSError:
                            pass
                        return True
        return False

    def _load_file(self, fpath: Path) -> dict[str, Any] | None:
        """Load a single SKILL.md file."""
        try:
            text = fpath.read_text(encoding="utf-8")
            meta, body = parse_skill_md(text)
            meta["body"] = body
            meta["_path"] = str(fpath)
            # Infer category from directory structure
            rel = fpath.relative_to(self.base_dir)
            if len(rel.parts) > 1:
                meta.setdefault("category", rel.parts[0])
            return meta
        except (OSError, ValueError):
            return None
