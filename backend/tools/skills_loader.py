"""Skills system aligned with OpenClaw SKILL.md spec.

参考来源：OpenClaw 的 skills 系统 —— 每个 skill 是一个目录，包含 SKILL.md（元数据+指令）
和可选的工具脚本。

植入目标：让 lengxiaobei 支持 OpenClaw 风格的 SKILL.md 规范，可加载 OpenClaw skills。
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Parsed SKILL.md metadata."""
    name: str
    description: str = ""
    location: str = ""
    version: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)  # trigger phrases/keywords
    tools: list[str] = field(default_factory=list)  # tool names this skill provides
    dependencies: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class Skill:
    """A loaded skill with its metadata and content."""
    metadata: SkillMetadata
    skill_md_path: Path
    content: str = ""  # Full SKILL.md content
    instructions: str = ""  # Extracted instruction section
    tools: dict[str, Callable] = field(default_factory=dict)  # Registered tool functions


class SkillLoader:
    """Loads and manages skills from SKILL.md files.

    Scans skill directories for SKILL.md files, parses metadata,
    and registers tools into the ToolRegistry.

    Supports OpenClaw's skill directory structure:
      skills/
        skill-name/
          SKILL.md       # metadata + instructions
          *.py           # optional tool scripts
        another-skill/
          SKILL.md
    """

    def __init__(
        self,
        skill_dirs: list[Path] | None = None,
        tool_registry: Any = None,
    ) -> None:
        self.skill_dirs = skill_dirs or []
        self.tool_registry = tool_registry
        self._skills: dict[str, Skill] = {}
        self._trigger_map: dict[str, str] = {}  # trigger -> skill_name

    def add_skill_dir(self, path: Path) -> None:
        """Add a directory to scan for skills."""
        if path not in self.skill_dirs:
            self.skill_dirs.append(path)

    def load_all(self) -> dict[str, Skill]:
        """Scan all skill directories and load skills."""
        for skill_dir in self.skill_dirs:
            if not skill_dir.exists():
                continue
            self._scan_directory(skill_dir)
        return dict(self._skills)

    def _scan_directory(self, directory: Path) -> None:
        """Recursively scan a directory for SKILL.md files."""
        for item in directory.rglob("SKILL.md"):
            try:
                skill = self._load_skill(item)
                if skill and skill.metadata.enabled:
                    self._skills[skill.metadata.name] = skill
                    # Register triggers
                    for trigger in skill.metadata.triggers:
                        self._trigger_map[trigger.lower()] = skill.metadata.name
                    logger.info("Loaded skill: %s from %s", skill.metadata.name, item)
            except Exception as exc:
                logger.warning("Failed to load skill from %s: %s", item, exc)

    def _load_skill(self, skill_md_path: Path) -> Skill | None:
        """Parse a SKILL.md file into a Skill object."""
        content = skill_md_path.read_text(encoding="utf-8")
        metadata = self._parse_metadata(content, skill_md_path)
        instructions = self._extract_instructions(content)

        skill = Skill(
            metadata=metadata,
            skill_md_path=skill_md_path,
            content=content,
            instructions=instructions,
        )

        # Load companion Python scripts as tools
        skill_dir = skill_md_path.parent
        for py_file in skill_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            self._load_tools_from_script(skill, py_file)

        return skill

    def _parse_metadata(self, content: str, path: Path) -> SkillMetadata:
        """Parse YAML frontmatter and first heading from SKILL.md."""
        name = path.parent.name
        description = ""
        version = ""
        author = ""
        tags: list[str] = []
        triggers: list[str] = []
        tools: list[str] = []
        dependencies: list[str] = []
        enabled = True

        # Parse YAML frontmatter between --- delimiters
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            for line in fm_text.splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("version:"):
                    version = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("author:"):
                    author = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("tags:"):
                    tags_str = line.split(":", 1)[1].strip()
                    tags = [t.strip().strip('"').strip("'") for t in tags_str.split(",")]
                elif line.startswith("triggers:"):
                    trig_str = line.split(":", 1)[1].strip()
                    triggers = [t.strip().strip('"').strip("'") for t in trig_str.split(",")]
                elif line.startswith("enabled:"):
                    enabled = line.split(":", 1)[1].strip().lower() in ("true", "yes", "1")

        # Fallback: extract name from first heading
        if not name:
            heading = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if heading:
                name = heading.group(1).strip()

        # Fallback: extract description from first paragraph after heading
        if not description:
            para = re.search(r"^#\s+.+\n\n(.+?)(?:\n\n|\n#)", content, re.MULTILINE | re.DOTALL)
            if para:
                description = para.group(1).strip()[:200]

        return SkillMetadata(
            name=name,
            description=description,
            location=str(path),
            version=version,
            author=author,
            tags=tags,
            triggers=triggers,
            tools=tools,
            dependencies=dependencies,
            enabled=enabled,
        )

    def _extract_instructions(self, content: str) -> str:
        """Extract the instruction section from SKILL.md (everything after frontmatter)."""
        # Remove frontmatter
        without_fm = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL)
        return without_fm.strip()

    def _load_tools_from_script(self, skill: Skill, py_file: Path) -> None:
        """Load tool functions from a Python script in the skill directory."""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                f"skill_{skill.metadata.name}_{py_file.stem}",
                str(py_file),
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Register callable functions as tools
                for attr_name in dir(module):
                    if attr_name.startswith("_"):
                        continue
                    attr = getattr(module, attr_name)
                    if callable(attr) and not isinstance(attr, type):
                        tool_name = f"skill_{skill.metadata.name}_{attr_name}"
                        skill.tools[attr_name] = attr
                        if self.tool_registry:
                            self.tool_registry.register(tool_name, attr)
        except Exception as exc:
            logger.debug("Failed to load tools from %s: %s", py_file, exc)

    # ── Query ────────────────────────────────────────────────────────

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def find_by_trigger(self, text: str) -> Skill | None:
        """Find a skill whose trigger matches the given text."""
        text_lower = text.lower()
        for trigger, skill_name in self._trigger_map.items():
            if trigger in text_lower:
                return self._skills.get(skill_name)
        return None

    def list_skills(self) -> list[dict[str, Any]]:
        """List all loaded skills with metadata."""
        return [
            {
                "name": s.metadata.name,
                "description": s.metadata.description,
                "location": s.metadata.location,
                "tags": s.metadata.tags,
                "triggers": s.metadata.triggers,
                "tools": list(s.tools.keys()),
                "enabled": s.metadata.enabled,
            }
            for s in self._skills.values()
        ]

    def get_skill_instructions(self, name: str) -> str:
        """Get the instruction content for a skill."""
        skill = self._skills.get(name)
        return skill.instructions if skill else ""

    def reload(self) -> None:
        """Reload all skills from disk."""
        self._skills.clear()
        self._trigger_map.clear()
        self.load_all()


# ── Singleton ───────────────────────────────────────────────────────

_loader: SkillLoader | None = None


def get_skill_loader(
    skill_dirs: list[Path] | None = None,
    tool_registry: Any = None,
) -> SkillLoader:
    global _loader
    if _loader is None:
        dirs = skill_dirs or []
        # Default skill directories
        env_dirs = os.getenv("SKILL_DIRS", "")
        if env_dirs:
            dirs.extend(Path(d.strip()) for d in env_dirs.split(",") if d.strip())
        # Project-local skills
        project_skills = Path.home() / "projects" / "lengxiaobei" / "skills"
        if project_skills.exists():
            dirs.append(project_skills)

        _loader = SkillLoader(skill_dirs=dirs, tool_registry=tool_registry)
        _loader.load_all()
    return _loader
