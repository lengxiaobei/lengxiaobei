"""Apple MLX model adapter placeholder.

The adapter keeps the architecture slot explicit while avoiding an eager MLX dependency.
"""

from __future__ import annotations

from backend.core.llm.base import LLMAdapter


class MLXAdapter(LLMAdapter):
    name = "mlx"

    def chat(self, message: str, system: str | None = None) -> str:
        raise RuntimeError("MLX adapter is not configured")
