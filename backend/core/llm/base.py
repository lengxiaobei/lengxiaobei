"""LLM adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    """Minimal chat adapter shared by local and remote model backends."""

    name: str

    @abstractmethod
    def chat(self, message: str, system: str | None = None) -> str:
        raise NotImplementedError
