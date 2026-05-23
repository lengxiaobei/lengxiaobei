"""Ollama/OpenAI-compatible LLM adapter.

参考来源：YourAgent 文档中的本地优先 LLM 集成；OpenClaw/Hermes/OpenHuman 上层都只依赖
这个窄接口，具体供应商可替换为 Ollama、MLX 或 OpenAI-compatible API。
"""

from __future__ import annotations

import json
import urllib.request

from backend.config import get_settings


def chat(prompt: str, system: str | None = None) -> str:
    """Call local Ollama when available; otherwise return a deterministic local fallback."""
    settings = get_settings()
    if settings.llm_provider.lower() != "ollama":
        prefix = f"系统上下文：{system}\n" if system else ""
        return f"{prefix}当前 LLM provider={settings.llm_provider} 尚未配置适配器，已保留输入：{prompt}"

    try:
        payload = {
            "model": settings.llm_model,
            "messages": [
                *([{"role": "system", "content": system}] if system else []),
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        req = urllib.request.Request(
            f"{settings.llm_base_url.rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str((data.get("message") or {}).get("content") or data.get("response") or "")
    except Exception as exc:
        prefix = f"系统上下文：{system}\n" if system else ""
        return f"{prefix}当前本地 Ollama 不可用，已保留输入用于后续处理：{prompt}\n原因：{exc}"
