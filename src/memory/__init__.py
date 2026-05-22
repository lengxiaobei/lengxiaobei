"""Compatibility memory facade.

Older modules import `src.memory.Memory`. The old flat `src/memory.py` module was
removed during the directory cleanup, so this package exposes a small wrapper
around the current HybridMemory implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from ..hybrid_memory import HybridMemory


class _MemoryConfig:
    def __init__(self, memory_dir: str):
        self.memory_dir = memory_dir
        self.vector_backend = "faiss"


class Memory(HybridMemory):
    """Backward-compatible memory class used by legacy query/forked-agent code."""

    def __init__(self, project_root: str | None = None, memory_dir: str | None = None):
        root = Path(project_root or Path(__file__).resolve().parents[2])
        target = memory_dir or str(root / "memory")
        super().__init__(_MemoryConfig(target))

    def recall(self, query: str, limit: int = 5, mem_type: Optional[str] = None) -> List[Dict]:
        return self.search(query, limit=limit, mem_type=mem_type)

    def remember(self, content: str, **kwargs) -> None:
        self.store(content, **kwargs)
