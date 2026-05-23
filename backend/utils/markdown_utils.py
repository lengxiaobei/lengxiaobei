"""Markdown helpers."""

from __future__ import annotations


def frontmatter(title: str) -> str:
    return f"---\ntitle: {title}\n---\n"
