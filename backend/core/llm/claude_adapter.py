"""Claude API adapter with native Tool Use, Prompt Caching, and Extended Thinking.

参考来源：Anthropic Messages API，支持 tools、tool_choice、cache_control、thinking。
植入目标：让 lengxiaobei 的 LLM 调用获得 Anthropic SDK 级别的原生能力。
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from backend.config import get_settings

logger = logging.getLogger(__name__)


# ── Tool schemas for Anthropic Tool Use ─────────────────────────────

_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "filesystem_read",
        "description": "Read a text file inside the project root. Returns file content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside the project root, e.g. 'frontend/src/App.tsx'"},
                "limit": {"type": "integer", "description": "Max characters to read (default 12000)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "filesystem_write",
        "description": "Write a text file inside the project root. Overwrites existing content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside the project root"},
                "content": {"type": "string", "description": "Full file content to write"},
                "create_parents": {"type": "boolean", "description": "Auto-create parent directories (default true)"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "filesystem_append",
        "description": "Append text to a file inside the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside the project root"},
                "content": {"type": "string", "description": "Text to append"},
                "create_parents": {"type": "boolean", "description": "Auto-create parent directories (default true)"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "filesystem_delete",
        "description": "Delete a file inside the project root. Cannot delete directories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside the project root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "shell_readonly",
        "description": "Run a safe read-only shell command inside the project root (e.g. ls, grep, find, git log, cat). Returns stdout and stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}, "description": "Command as list of args, e.g. ['ls', '-la']"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "shell_exec",
        "description": "Run a shell command inside the project root. Can run build, test, install commands. Returns stdout and stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "array", "items": {"type": "string"}, "description": "Command as list of args, e.g. ['npm', 'run', 'build']"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "web_fetch",
        "description": "Fetch a URL and return the page content as plain text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "memory_search",
        "description": "Search the agent's long-term memory for relevant entries. Returns matching memory nodes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "reflect",
        "description": "Trigger a reflection on the agent's recent activity or a specific topic. Returns reflection summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to reflect on (default 'system')"},
            },
            "required": [],
        },
    },
    {
        "name": "skill_list",
        "description": "List available/approved skills in the skill store.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "skill_execute",
        "description": "Execute an approved skill by name with optional inputs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name"},
                "inputs": {"type": "object", "description": "Optional input parameters for the skill"},
            },
            "required": ["name"],
        },
    },
]


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return Anthropic tool schemas for the built-in tool set."""
    return list(_TOOL_SCHEMAS)


# ── Client singleton ────────────────────────────────────────────────

_client: Any | None = None


def _get_client() -> Any:
    global _client
    if _client is None:
        try:
            import anthropic as _anthropic

            settings = get_settings()
            _client = _anthropic.AsyncAnthropic(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url if settings.llm_base_url else None,
            )
        except Exception as exc:
            logger.error("Failed to initialize Anthropic client: %s", exc)
            raise
    return _client


# ── Caching helpers ─────────────────────────────────────────────────

CACHING_MODELS = frozenset({
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
    "claude-3-5-haiku-20241022",
})


def _supports_caching(model: str) -> bool:
    return any(model.startswith(m) for m in CACHING_MODELS) or "claude" in model.lower()


def _wrap_system_with_cache(text: str) -> list[dict[str, Any]]:
    """Wrap system text in a content block with cache_control for prompt caching."""
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


# ── Core chat functions ─────────────────────────────────────────────

@dataclass
class ChatResult:
    """Result of a Claude chat, including tool calls and token usage."""

    content: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, Any]
    model: str
    stop_reason: str | None = None


async def chat(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    enable_caching: bool = False,
    thinking_budget: int | None = None,
) -> ChatResult:
    """Simple chat without tools. Drop-in replacement for ollama.chat."""
    client = _get_client()
    settings = get_settings()
    target_model = model or settings.llm_model

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    kwargs: dict[str, Any] = {
        "model": target_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }

    if system:
        if enable_caching and _supports_caching(target_model):
            kwargs["system"] = _wrap_system_with_cache(system)
        else:
            kwargs["system"] = system

    if thinking_budget and thinking_budget > 0:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        kwargs.pop("temperature", None)  # thinking mode disables temperature

    try:
        response = await client.messages.create(**kwargs)
    except Exception as exc:
        logger.error("Claude chat error: %s", exc)
        raise

    text_parts = [b.text for b in response.content if b.type == "text"]
    content = "\n".join(text_parts).strip()

    return ChatResult(
        content=content,
        tool_calls=[],
        usage=_extract_usage(response),
        model=response.model,
        stop_reason=response.stop_reason,
    )


async def chat_with_tools(
    prompt: str,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_executor: Callable[[str, dict[str, Any]], Any] | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    max_tool_rounds: int = 10,
    enable_caching: bool = False,
    thinking_budget: int | None = None,
) -> ChatResult:
    """Chat with native Tool Use. Automatically handles tool_use / tool_result loops.

    tool_executor: callable(name: str, args: dict) -> result (any serializable)
    """
    client = _get_client()
    settings = get_settings()
    target_model = model or settings.llm_model
    tools = tools or []

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    all_tool_calls: list[dict[str, Any]] = []

    for _ in range(max_tool_rounds):
        kwargs: dict[str, Any] = {
            "model": target_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        if system:
            if enable_caching and _supports_caching(target_model):
                kwargs["system"] = _wrap_system_with_cache(system)
            else:
                kwargs["system"] = system

        if thinking_budget and thinking_budget > 0:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            kwargs.pop("temperature", None)

        try:
            response = await client.messages.create(**kwargs)
        except Exception as exc:
            logger.error("Claude chat_with_tools error: %s", exc)
            raise

        # Check for tool_use blocks
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_parts = [b.text for b in response.content if b.type == "text"]
        text_content = "\n".join(text_parts).strip()

        if not tool_uses:
            return ChatResult(
                content=text_content,
                tool_calls=all_tool_calls,
                usage=_extract_usage(response),
                model=response.model,
                stop_reason=response.stop_reason,
            )

        # Record assistant message with tool_use blocks
        assistant_content: list[dict[str, Any]] = []
        if text_content:
            assistant_content.append({"type": "text", "text": text_content})
        for tu in tool_uses:
            assistant_content.append({
                "type": "tool_use",
                "id": tu.id,
                "name": tu.name,
                "input": tu.input,
            })
            all_tool_calls.append({"id": tu.id, "name": tu.name, "input": tu.input})

        messages.append({"role": "assistant", "content": assistant_content})

        # Execute tools and build tool_result blocks
        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            if tool_executor is None:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": "Error: no tool executor configured",
                    "is_error": True,
                })
                continue

            try:
                result = tool_executor(tu.name, dict(tu.input))
                if inspect.isawaitable(result):
                    result = await result
                result_text = json.dumps(result, ensure_ascii=False, default=str)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_text,
                })
            except Exception as exc:
                logger.warning("Tool %s failed: %s", tu.name, exc)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": f"Error: {exc}",
                    "is_error": True,
                })

        messages.append({"role": "user", "content": tool_results})

    # Max rounds exceeded — return whatever we have
    return ChatResult(
        content=text_content or "达到最大工具调用轮次限制，请简化请求。",
        tool_calls=all_tool_calls,
        usage={},
        model=target_model,
        stop_reason="max_tool_rounds",
    )


async def stream_chat(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """Stream a chat response token by token."""
    client = _get_client()
    settings = get_settings()
    target_model = model or settings.llm_model

    kwargs: dict[str, Any] = {
        "model": target_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    if system:
        kwargs["system"] = system

    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as exc:
        logger.error("Claude stream error: %s", exc)
        raise


# ── Helpers ─────────────────────────────────────────────────────────

def _extract_usage(response: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    if hasattr(response, "usage") and response.usage:
        u = response.usage
        usage["input_tokens"] = getattr(u, "input_tokens", 0)
        usage["output_tokens"] = getattr(u, "output_tokens", 0)
        # Prompt caching fields
        usage["cache_creation_input_tokens"] = getattr(u, "cache_creation_input_tokens", 0)
        usage["cache_read_input_tokens"] = getattr(u, "cache_read_input_tokens", 0)
    return usage


# ── Drop-in compatibility wrapper ───────────────────────────────────

async def compat_chat(prompt: str, system: str | None = None) -> str:
    """Drop-in replacement for backend.core.llm.ollama.chat.

    Returns plain text string. Does not use tools.
    """
    try:
        settings = get_settings()
        enable_caching = getattr(settings, "llm_claude_enable_caching", False)
        thinking_budget = getattr(settings, "llm_claude_thinking_budget", None)
        result = await chat(
            prompt,
            system=system,
            enable_caching=enable_caching,
            thinking_budget=thinking_budget,
        )
        return result.content
    except Exception as exc:
        logger.warning("Claude compat_chat failed: %s", exc)
        return _fallback(prompt, str(exc))


def _fallback(prompt: str, reason: str) -> str:
    compact = "".join(prompt.split())
    if compact in {"你好", "您好", "hello", "hi"}:
        return "你好，我是冷小北。Claude API 暂时不可用，但我还在。"
    return f"Claude 服务暂时不可用：{reason}"
