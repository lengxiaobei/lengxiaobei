#!/usr/bin/env python3
"""Validate the new YourAgent repository layout."""
from __future__ import annotations

from pathlib import Path

ALLOWED_TOP_LEVEL = {
    ".github", "backend", "frontend", "data", "scripts",
    ".env.example", ".gitignore", ".dockerignore", "README.md", "Dockerfile",
    "docker-compose.yml", "pyproject.toml", "package.json", "Makefile", "requirements.txt",
}
REQUIRED = {
    "backend/main.py",
    "backend/config.py",
    "backend/api/routes/conversations.py",
    "backend/memory/tree.py",
    "backend/evolution/skill_gen.py",
    "backend/tools/registry.py",
    "frontend/src/api/client.ts",
    "frontend/src/components/Chat/ChatWindow.tsx",
    "data/sqlite/.gitkeep",
}


def main() -> int:
    root = Path.cwd()
    errors: list[str] = []
    for child in root.iterdir():
        if child.name == ".git":
            continue
        if child.name not in ALLOWED_TOP_LEVEL:
            errors.append(f"unexpected top-level entry: {child.name}")
    for rel in REQUIRED:
        if not (root / rel).exists():
            errors.append(f"missing required entry: {rel}")
    if errors:
        print("Layout check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Layout check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
