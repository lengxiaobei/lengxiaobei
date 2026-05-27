"""Ollama/OpenAI-compatible/Anthropic/Xiaomi LLM adapter.

参考来源：YourAgent 文档中的本地优先 LLM 集成；OpenClaw/Hermes/OpenHuman 上层都只依赖
这个窄接口，具体供应商可替换为 Ollama、MLX、OpenAI-compatible API、Anthropic 或 Xiaomi MiMo。
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.config import get_settings


def local_fallback(prompt: str, reason: str | None = None) -> str:
    """Human-facing fallback used when the configured model is unavailable."""
    compact = "".join(prompt.split())
    if compact in {"你好", "您好", "hello", "hi"}:
        return "你好，我是冷小北。模型服务暂时没有连上，但我还在，可以先处理系统状态、记忆、技能和工具类请求。"
    if reason:
        return f"模型服务这次没有返回成功，我先用本地规则把请求接住：{prompt}"
    return f"我收到：{prompt}"


# ── Provider registry ───────────────────────────────────────────────

_PROVIDER_ALIASES: dict[str, str] = {
    "openai": "openai",
    "openai-compatible": "openai",
    "token-plan": "openai",
    "ollama": "ollama",
    "xiaomi": "openai",          # Xiaomi MiMo uses OpenAI-compatible protocol
    "mimo": "openai",
    "minimax": "openai",
    "minimax-cn": "openai",
    "anthropic": "anthropic",
    "mimo-v2.5-pro": "openai",   # Model name as provider shortcut
}


def _resolve_protocol(provider: str) -> str:
    """Map provider name to protocol handler."""
    normalized = provider.lower().replace("_", "-")
    return _PROVIDER_ALIASES.get(normalized, "unknown")


async def chat(prompt: str, system: str | None = None) -> str:
    """Call the configured chat backend; otherwise return a deterministic local fallback.

    Now uses the multi-provider router for automatic fallback.
    """
    try:
        from backend.core.llm.router import chat as router_chat
        return await router_chat(prompt, system=system)
    except Exception:
        # Fallback to direct single-provider call
        settings = get_settings()
        protocol = _resolve_protocol(settings.llm_provider)
        if protocol == "openai":
            return await _openai_compatible_chat(prompt, system=system)
        if protocol == "anthropic":
            return await _anthropic_chat(prompt, system=system)
        if protocol == "ollama":
            return await _ollama_chat(prompt, system=system)
        return local_fallback(prompt, reason=f"provider {settings.llm_provider} is not configured")


# ── Ollama ──────────────────────────────────────────────────────────

async def _ollama_chat(prompt: str, system: str | None = None) -> str:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20)) as client:
            payload = {
                "model": settings.llm_model,
                "messages": [
                    *([{"role": "system", "content": system}] if system else []),
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            }
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/api/chat",
                json=payload,
            )
            data = response.json()
        return str((data.get("message") or {}).get("content") or data.get("response") or "")
    except Exception:
        return local_fallback(prompt, reason="ollama unavailable")


# ── OpenAI-compatible (also covers Xiaomi MiMo, MiniMax, etc.) ──────

async def _openai_compatible_chat(prompt: str, system: str | None = None) -> str:
    settings = get_settings()
    if not settings.llm_api_key:
        return local_fallback(prompt, reason="missing api key")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60)) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                json={
                    "model": settings.llm_model,
                    "messages": _messages(prompt, system),
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            )
            data = response.json()
        choices = data.get("choices") or []
        if not choices:
            error_msg = data.get("error", {}).get("message", "") if isinstance(data.get("error"), dict) else ""
            return local_fallback(prompt, reason=f"empty model response: {error_msg}")
        message = choices[0].get("message") or {}
        return str(message.get("content") or choices[0].get("text") or "").strip() or local_fallback(
            prompt, reason="empty model content"
        )
    except Exception as exc:
        return local_fallback(prompt, reason=f"openai-compatible backend unavailable: {exc}")


# ── Anthropic protocol ──────────────────────────────────────────────

async def _anthropic_chat(prompt: str, system: str | None = None) -> str:
    """Call Anthropic Messages API (/v1/messages)."""
    settings = get_settings()
    if not settings.llm_api_key:
        return local_fallback(prompt, reason="missing anthropic api key")

    base_url = settings.llm_base_url.rstrip("/")
    # Support both direct Anthropic and proxy endpoints
    if "/v1/messages" not in base_url:
        url = f"{base_url}/v1/messages"
    else:
        url = base_url

    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body: dict[str, Any] = {
        "model": settings.llm_model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60)) as client:
            response = await client.post(url, json=body, headers=headers)
            data = response.json()

        # Anthropic response format
        content_blocks = data.get("content") or []
        text_parts = [block.get("text", "") for block in content_blocks if block.get("type") == "text"]
        result = "\n".join(text_parts).strip()
        return result or local_fallback(prompt, reason="empty anthropic response")
    except Exception as exc:
        return local_fallback(prompt, reason=f"anthropic backend unavailable: {exc}")


# ── Helpers ─────────────────────────────────────────────────────────

def _messages(prompt: str, system: str | None = None) -> list[dict[str, str]]:
    return [
        *([{"role": "system", "content": system}] if system else []),
        {"role": "user", "content": prompt},
    ]
