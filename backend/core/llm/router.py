"""Multi-provider LLM router with fallback chains.

参考来源：OpenClaw 的 models.providers 架构——多 provider 注册、优先级排序、
自动 fallback、健康检查、流式支持。

植入目标：让 lengxiaobei 的 LLM 调用获得 OpenClaw 级别的 provider 路由能力。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)


# ── Provider & Model config ─────────────────────────────────────────

@dataclass
class ModelSpec:
    """A single model within a provider."""
    id: str
    name: str = ""
    context_window: int = 128000
    max_tokens: int = 4096
    supports_vision: bool = False
    supports_reasoning: bool = False
    cost_input: float = 0.0
    cost_output: float = 0.0


@dataclass
class ProviderConfig:
    """A registered LLM provider with its models and connection info."""
    name: str
    base_url: str
    api_key: str = ""
    protocol: str = "openai"  # openai | anthropic | ollama
    models: list[ModelSpec] = field(default_factory=list)
    priority: int = 0  # higher = tried first
    timeout: float = 60.0
    max_retries: int = 2
    enabled: bool = True
    _healthy: bool = True
    _last_check: float = 0.0
    _fail_count: int = 0

    @property
    def default_model(self) -> ModelSpec | None:
        return self.models[0] if self.models else None

    def get_model(self, model_id: str) -> ModelSpec | None:
        for m in self.models:
            if m.id == model_id:
                return m
        return None


# ── Provider Router ─────────────────────────────────────────────────

class ProviderRouter:
    """Routes LLM requests across multiple providers with automatic fallback.

    Mirrors OpenClaw's models.providers + agents.defaults.model.primary/fallbacks pattern.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProviderConfig] = {}
        self._primary: str | None = None
        self._fallbacks: list[str] = []
        self._client: httpx.AsyncClient | None = None

    # -- Registration -------------------------------------------------------

    def register(self, provider: ProviderConfig) -> None:
        """Register a provider. Called at startup from config."""
        self._providers[provider.name] = provider
        logger.info("Registered LLM provider: %s (%s)", provider.name, provider.base_url)

    def set_primary(self, provider_name: str) -> None:
        self._primary = provider_name

    def set_fallbacks(self, provider_names: list[str]) -> None:
        self._fallbacks = provider_names

    def load_from_config(self) -> None:
        """Load provider chain from settings / env.

        Reads:
          LLM_PROVIDER          -> primary provider
          LLM_FALLBACKS         -> comma-separated fallback list
          LLM_<NAME>_BASE_URL   -> provider base url
          LLM_<NAME>_API_KEY    -> provider api key
          LLM_<NAME>_MODELS     -> comma-separated model ids
          LLM_<NAME>_PROTOCOL   -> protocol (default: openai)
          LLM_<NAME>_PRIORITY   -> priority int (default: 0)
        """
        import os

        settings = get_settings()

        # Primary provider from settings
        primary = settings.llm_provider
        self._primary = primary

        # Fallbacks from env
        fallbacks_str = os.getenv("LLM_FALLBACKS", "")
        self._fallbacks = [f.strip() for f in fallbacks_str.split(",") if f.strip()]

        # Auto-register the main provider from settings
        main_provider = ProviderConfig(
            name=primary,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "",
            protocol=_resolve_protocol(primary),
            models=[ModelSpec(id=settings.llm_model)],
            priority=100,
        )
        self.register(main_provider)

        # Scan env for additional providers: LLM_<NAME>_BASE_URL
        prefix = "LLM_"
        seen_names: set[str] = {primary}
        for key, value in os.environ.items():
            if not key.startswith(prefix) or not key.endswith("_BASE_URL"):
                continue
            # Extract provider name: LLM_BAILIAN_BASE_URL -> bailian
            name_part = key[len(prefix):-len("_BASE_URL")]
            provider_name = name_part.lower().replace("_", "-")
            if provider_name in seen_names:
                continue
            seen_names.add(provider_name)

            base_url = value
            api_key = os.getenv(f"{prefix}{name_part}_API_KEY", "")
            models_str = os.getenv(f"{prefix}{name_part}_MODELS", "")
            protocol = os.getenv(f"{prefix}{name_part}_PROTOCOL", "openai").lower()
            priority = int(os.getenv(f"{prefix}{name_part}_PRIORITY", "0"))

            models = [ModelSpec(id=m.strip()) for m in models_str.split(",") if m.strip()]
            if not models:
                models = [ModelSpec(id="default")]

            provider = ProviderConfig(
                name=provider_name,
                base_url=base_url,
                api_key=api_key,
                protocol=protocol,
                models=models,
                priority=priority,
            )
            self.register(provider)
            if provider_name not in self._fallbacks:
                self._fallbacks.append(provider_name)

        # Sort fallbacks by priority (descending)
        self._fallbacks.sort(
            key=lambda name: self._providers[name].priority if name in self._providers else 0,
            reverse=True,
        )

    # -- Routing ------------------------------------------------------------

    def _ordered_providers(self, model_id: str | None = None) -> list[ProviderConfig]:
        """Return providers in try-order: primary first, then fallbacks by priority."""
        ordered: list[ProviderConfig] = []
        seen: set[str] = set()

        # Primary first
        if self._primary and self._primary in self._providers:
            p = self._providers[self._primary]
            if p.enabled and p._healthy:
                ordered.append(p)
                seen.add(self._primary)

        # Then fallbacks
        for name in self._fallbacks:
            if name in seen or name not in self._providers:
                continue
            p = self._providers[name]
            if p.enabled and p._healthy:
                ordered.append(p)
                seen.add(name)

        # Any remaining providers not in fallbacks
        for name, p in self._providers.items():
            if name not in seen and p.enabled and p._healthy:
                ordered.append(p)

        return ordered

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Route a chat request through the provider chain with fallback.

        Returns: {"content": str, "model": str, "provider": str, "usage": dict, "error": str|None}
        """
        providers = self._ordered_providers(model)
        if not providers:
            return {"content": "", "model": "", "provider": "", "usage": {}, "error": "no available providers"}

        last_error: str | None = None
        for provider in providers:
            target_model = model or (provider.default_model.id if provider.default_model else "default")
            try:
                result = await self._call_provider(
                    provider=provider,
                    model=target_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                    **kwargs,
                )
                provider._fail_count = 0
                provider._healthy = True
                return result
            except Exception as exc:
                provider._fail_count += 1
                last_error = f"[{provider.name}] {exc}"
                logger.warning("Provider %s failed (attempt %d): %s", provider.name, provider._fail_count, exc)
                if provider._fail_count >= 3:
                    provider._healthy = False
                    logger.error("Provider %s marked unhealthy after %d failures", provider.name, provider._fail_count)
                continue

        return {"content": "", "model": "", "provider": "", "usage": {}, "error": f"all providers failed: {last_error}"}

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a chat response through the provider chain."""
        providers = self._ordered_providers(model)
        for provider in providers:
            target_model = model or (provider.default_model.id if provider.default_model else "default")
            try:
                async for chunk in self._stream_provider(
                    provider=provider,
                    model=target_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ):
                    yield chunk
                provider._fail_count = 0
                return
            except Exception as exc:
                provider._fail_count += 1
                logger.warning("Provider %s stream failed: %s", provider.name, exc)
                continue

    # -- Protocol handlers ---------------------------------------------------

    async def _call_provider(
        self,
        provider: ProviderConfig,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = await self._get_client()
        if provider.protocol == "anthropic":
            return await self._call_anthropic(client, provider, model, messages, temperature, max_tokens, **kwargs)
        else:
            return await self._call_openai(client, provider, model, messages, temperature, max_tokens, **kwargs)

    async def _call_openai(
        self,
        client: httpx.AsyncClient,
        provider: ProviderConfig,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{provider.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        # Pass through extra params (e.g., reasoning, tools)
        body.update(kwargs)

        resp = await client.post(url, json=body, headers=headers, timeout=provider.timeout)
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices") or []
        content = ""
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content") or ""

        return {
            "content": content,
            "model": data.get("model", model),
            "provider": provider.name,
            "usage": data.get("usage", {}),
            "error": None,
        }

    async def _call_anthropic(
        self,
        client: httpx.AsyncClient,
        provider: ProviderConfig,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{provider.base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": provider.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Extract system message if present
        system_msg = None
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_messages.append(m)

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": user_messages,
        }
        if system_msg:
            body["system"] = system_msg

        resp = await client.post(url, json=body, headers=headers, timeout=provider.timeout)
        resp.raise_for_status()
        data = resp.json()

        content_blocks = data.get("content") or []
        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        content = "\n".join(text_parts).strip()

        return {
            "content": content,
            "model": data.get("model", model),
            "provider": provider.name,
            "usage": data.get("usage", {}),
            "error": None,
        }

    async def _stream_provider(
        self,
        provider: ProviderConfig,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = await self._get_client()
        url = f"{provider.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        body.update(kwargs)

        async with client.stream("POST", url, json=body, headers=headers, timeout=provider.timeout) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    return
                try:
                    import json
                    chunk = json.loads(payload)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except Exception:
                    continue

    # -- Health management ---------------------------------------------------

    async def health_check(self, provider_name: str | None = None) -> dict[str, Any]:
        """Check health of a specific or all providers."""
        targets = [self._providers[provider_name]] if provider_name else list(self._providers.values())
        results = {}
        for p in targets:
            try:
                client = await self._get_client()
                url = f"{p.base_url.rstrip('/')}/models"
                headers = {}
                if p.api_key:
                    headers["Authorization"] = f"Bearer {p.api_key}"
                resp = await client.get(url, headers=headers, timeout=10)
                p._healthy = resp.status_code == 200
                p._last_check = time.time()
                results[p.name] = {"healthy": p._healthy, "status": resp.status_code}
            except Exception as exc:
                p._healthy = False
                p._last_check = time.time()
                results[p.name] = {"healthy": False, "error": str(exc)}
        return results

    def get_status(self) -> dict[str, Any]:
        """Return current router status for API introspection."""
        return {
            "primary": self._primary,
            "fallbacks": self._fallbacks,
            "providers": {
                name: {
                    "base_url": p.base_url,
                    "protocol": p.protocol,
                    "healthy": p._healthy,
                    "fail_count": p._fail_count,
                    "models": [m.id for m in p.models],
                    "priority": p.priority,
                }
                for name, p in self._providers.items()
            },
        }

    # -- Lifecycle ----------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ── Singleton & helpers ─────────────────────────────────────────────

_router: ProviderRouter | None = None


def get_router() -> ProviderRouter:
    global _router
    if _router is None:
        _router = ProviderRouter()
        _router.load_from_config()
    return _router


async def chat(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> str:
    """Drop-in replacement for backend.core.llm.ollama.chat with multi-provider routing."""
    router = get_router()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    result = await router.chat(messages, model=model, **kwargs)
    if result["error"]:
        logger.warning("Router chat error: %s", result["error"])
        return _local_fallback(prompt, result["error"])
    return result["content"]


def _local_fallback(prompt: str, reason: str) -> str:
    compact = "".join(prompt.split())
    if compact in {"你好", "您好", "hello", "hi"}:
        return "你好，我是冷小北。模型服务暂时没有连上，但我还在。"
    return f"模型服务暂时不可用：{reason}"


def _resolve_protocol(provider: str) -> str:
    mapping = {
        "openai": "openai", "openai-compatible": "openai",
        "token-plan": "openai", "tokenplan": "openai",
        "ollama": "ollama", "xiaomi": "openai", "mimo": "openai",
        "minimax": "openai", "minimax-cn": "openai",
        "anthropic": "anthropic",
    }
    return mapping.get(provider.lower().replace("_", "-"), "openai")
