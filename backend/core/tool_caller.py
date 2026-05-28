"""Tool Calling Protocol — LLM → JSON tool_call → dispatch → loop → response.

Hermes-style multi-turn tool loop:
  1. Send system + messages to LLM
  2. LLM outputs tool_call JSON (or plain text) in its response
  3. Parse tool_calls from response, dispatch each to registered tools
  4. Collect results, prepend as tool results messages
  5. Loop back to step 1 until no more tool_calls
  6. Return final text response

Supports two formats:
  - OpenAI style: { "tool_calls": [ { "id": "...", "type": "function", "function": { "name": "...", "arguments": "..." } } ] }
  - Hermes style: { "tool_calls": [ { "name": "...", "args": {...}, "id": "..." } ] }
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Max loops to prevent infinite tool calling
MAX_TOOL_LOOPS = 10


def _extract_json(text: str) -> list[dict[str, Any]] | None:
    """Extract tool_calls JSON from LLM response text."""
    # Try: ```json ... ``` blocks first
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "tool_calls" in obj:
                return obj["tool_calls"]
            if isinstance(obj, list):
                return obj
        except json.JSONDecodeError:
            pass

    # Try: raw { "tool_calls": [...] } at start
    try:
        obj = json.loads(text.strip())
        if isinstance(obj, dict) and "tool_calls" in obj:
            return obj["tool_calls"]
        if isinstance(obj, list):
            return obj
    except json.JSONDecodeError:
        pass

    # Try: find tool_calls JSON anywhere in text
    m = re.search(r'"tool_calls"\s*:\s*\[', text)
    if m:
        start = m.start()
        # Try to find the matching ]
        brace_start = text.rfind("{", 0, start)
        if brace_start >= 0:
            for end_offset in range(start, len(text)):
                if text[end_offset] == "]":
                    try:
                        obj = json.loads(text[brace_start : end_offset + 1])
                        return obj.get("tool_calls", [])
                    except json.JSONDecodeError:
                        break
    return None


def _parse_tool_call(raw: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Parse a single tool call into (name, call_id, arguments_dict)."""
    # Hermes style: { "name": "...", "args": {...}, "id": "..." }
    if "name" in raw:
        name = raw["name"]
        args = raw.get("args") or raw.get("arguments") or {}
        cid = raw.get("id") or raw.get("call_id") or f"call_{name}"
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        return name, cid, args

    # OpenAI style: { "function": { "name": "...", "arguments": "..." }, "id": "..." }
    if "function" in raw:
        fn = raw["function"]
        name = fn.get("name") or ""
        args_str = fn.get("arguments") or "{}"
        cid = raw.get("id") or ""
        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            args = {}
        return name, cid, args

    raise ValueError(f"Unknown tool_call format: {list(raw.keys())}")


class ToolCaller:
    """Hermes-style tool calling loop with LLM and a tool registry."""

    def __init__(self, llm_complete_fn, tool_registry, logger: Any = None):
        self.llm_complete = llm_complete_fn  # async (messages) -> str
        self.tools = tool_registry  # ToolRegistry instance
        self.logger = logger or logging.getLogger(__name__)
        self.max_loops = MAX_TOOL_LOOPS

    async def run(self, messages: list[dict[str, Any]], system: str = "") -> dict[str, Any]:
        """Run the tool-calling loop. Returns final response dict."""
        loop_count = 0
        history = list(messages)

        while loop_count < self.max_loops:
            loop_count += 1
            self.logger.debug("Tool loop iteration %d, %d messages", loop_count, len(history))

            # Step 1: call LLM
            response_text = await self.llm_complete(history, system=system)
            if not response_text:
                return {"content": "", "tool_calls": [], "loops": loop_count, "error": "empty LLM response"}

            # Step 2: append assistant message
            history.append({"role": "assistant", "content": response_text})

            # Step 3: extract tool_calls
            tool_calls = _extract_json(response_text)
            if not tool_calls:
                # Plain text response — we're done
                return {"content": response_text, "tool_calls": [], "loops": loop_count}

            self.logger.info("LLM requested %d tool(s): %s", len(tool_calls), [t.get("name") or t.get("function", {}).get("name") for t in tool_calls])

            # Step 4: dispatch each tool call
            results_content: list[str] = []
            for raw in tool_calls:
                try:
                    name, call_id, args = _parse_tool_call(raw)
                except Exception as exc:
                    results_content.append(f'{{"error": "parse error: {exc}"}}')
                    continue

                if name not in self.tools._tools:
                    results_content.append(f'{{"error": "unknown tool: {name}"}}')
                    continue

                try:
                    result = await self._call_tool(name, args)
                    # Serialize result — prefer dict/json, else wrap as string
                    if isinstance(result, (dict, list)):
                        result_str = json.dumps(result, ensure_ascii=False, indent=2)
                    else:
                        result_str = str(result)
                    results_content.append(result_str)
                except Exception as exc:
                    results_content.append(f'{{"error": "tool execution failed: {exc}"}}')

            # Step 5: prepend tool results as system-injected tool role messages
            if results_content:
                combined = "\n\n".join(results_content)
                history.append({
                    "role": "system",
                    "content": (
                        "You have called the following tools. Here are the results:\n\n"
                        + combined
                        + "\n\nContinue your response based on these results, or if the task is complete, give your final answer."
                    ),
                })

        # Max loops reached
        history.append({"role": "system", "content": "Max tool-call loops reached. Please respond with what you have."})
        final = await self.llm_complete(history, system=system)
        return {"content": final or "Max tool-call loops reached.", "tool_calls": [], "loops": loop_count, "truncated": True}

    async def _call_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Call a single registered tool, with concurrency limit."""
        tool_fn = self.tools._tools[name]
        # Dispatch via dispatcher-style call
        if asyncio.iscoroutinefunction(tool_fn):
            return await tool_fn(**args)
        else:
            return tool_fn(**args)