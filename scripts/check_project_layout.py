#!/usr/bin/env python3
"""Validate the repository layout.

This guard keeps agents from creating random top-level directories or committing
generated caches/build outputs. It is intentionally conservative: add a directory
here only when it has a clear owner and lifecycle in docs/DIRECTORY_RULES.md.
"""

from __future__ import annotations

import argparse
from pathlib import Path


ALLOWED_TOP_LEVEL_DIRS = {
    ".claude",
    ".github",
    ".trae",
    "assessment",
    "bridges",
    "buddy",
    "config",
    "deploy",
    "docs",
    "goals",
    "integrity",
    "learning",
    "logs",
    "lx_web",
    "memory",
    "memory_layer",
    "motivation",
    "permissions",
    "prompts",
    "scripts",
    "skills",
    "src",
    "state",
    "tests",
    "trae-plugin-lengxiaobei",
    "venv",
}

LEGACY_RUNTIME_DIRS = {
    "assessment",
    "buddy",
    "goals",
    "integrity",
    "learning",
    "motivation",
    "permissions",
}

FORBIDDEN_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "node_modules",
    "target",
}

FORBIDDEN_SUFFIXES = (".egg-info",)

REQUIRED_FILES = {
    "docs/ARCHITECTURE.md",
    "docs/DIRECTORY_RULES.md",
    "lx_web/app.py",
    "lx_web.py",
    "src/core.py",
    "src/self_evolution.py",
}


def _is_forbidden_dir(path: Path) -> bool:
    return path.name in FORBIDDEN_DIR_NAMES or path.name.endswith(FORBIDDEN_SUFFIXES)


def check_layout(root: Path, strict_legacy: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for rel in sorted(REQUIRED_FILES):
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")

    def report_generated(path: Path) -> None:
        rel = path.relative_to(root) if path != root else path
        message = f"generated directory should stay untracked/disposable: {rel}/"
        warnings.append(message)

    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        name = child.name
        if name == ".git":
            continue
        if _is_forbidden_dir(child):
            report_generated(child)
            continue
        if name not in ALLOWED_TOP_LEVEL_DIRS:
            errors.append(f"unknown top-level directory: {name}/")
        elif name in LEGACY_RUNTIME_DIRS:
            message = (
                f"legacy runtime directory still present: {name}/ "
                "(do not add new files; migrate future state to memory/ or state/)"
            )
            if strict_legacy:
                errors.append(message)
            else:
                warnings.append(message)

    ignored_parts = {".git", "venv", "node_modules", "target", "__pycache__"}
    for path in sorted(root.rglob("*"), key=lambda p: str(p)):
        if any(part in ignored_parts for part in path.parts):
            continue
        if path.is_dir() and _is_forbidden_dir(path):
            report_generated(path)

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check LengXiaobei repository layout")
    parser.add_argument("--root", default=".", help="project root")
    parser.add_argument(
        "--strict-legacy",
        action="store_true",
        help="treat legacy runtime directories as errors",
    )
    parser.add_argument(
        "--strict-generated",
        action="store_true",
        help="treat generated cache/build directories as errors",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors, warnings = check_layout(root, strict_legacy=args.strict_legacy)
    if args.strict_generated:
        generated = [w for w in warnings if w.startswith("generated directory")]
        errors.extend(generated)
        warnings = [w for w in warnings if w not in generated]

    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print(f"layout check failed: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"layout check passed: {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
