"""Tool implementations for the Agent Loop.

Each tool is an async function (dict[str, Any]) -> Any.
Registered with AgentLoop.register_tool(name, fn).
"""

from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from backend.config import PROJECT_ROOT


# ── Filesystem ─────────────────────────────────────────────────────────

async def filesystem_write(args: dict[str, Any]) -> dict[str, Any]:
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return {"error": "path required"}
    safe_path = _safe_path(path)
    if safe_path is None:
        return {"error": "unsafe path"}
    safe_path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(safe_path)}


async def filesystem_read(args: dict[str, Any]) -> dict[str, Any]:
    path = args.get("path", "")
    if not path:
        return {"error": "path required"}
    safe_path = _safe_path(path)
    if safe_path is None:
        return {"error": "unsafe path"}
    if not safe_path.exists():
        return {"error": f"file not found: {path}"}
    text = safe_path.read_text(encoding="utf-8")
    return {"ok": True, "path": str(safe_path), "content": text[:5000]}


async def filesystem_delete(args: dict[str, Any]) -> dict[str, Any]:
    path = args.get("path", "")
    if not path:
        return {"error": "path required"}
    safe_path = _safe_path(path)
    if safe_path is None:
        return {"error": "unsafe path"}
    if safe_path.is_file():
        safe_path.unlink()
    elif safe_path.is_dir():
        return {"error": "refusing to delete directory"}
    return {"ok": True, "path": str(safe_path)}


def _safe_path(path: str) -> Path | None:
    """Resolve path within PROJECT_ROOT."""
    try:
        full = (Path(PROJECT_ROOT) / path).resolve()
        if not str(full).startswith(str(Path(PROJECT_ROOT).resolve())):
            return None
        return full
    except Exception:
        return None


# ── Shell exec ─────────────────────────────────────────────────────────

async def shell_exec(args: dict[str, Any]) -> dict[str, Any]:
    cmd = args.get("command", "")
    if not cmd:
        return {"error": "command required"}
    # Restrict to PROJECT_ROOT
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(PROJECT_ROOT)),
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── Web search ────────────────────────────────────────────────────────

async def web_search(args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query", "")
    if not query:
        return {"error": "query required"}
    try:
        import urllib.request, json
        q = query.replace("\"", "").replace("'", "")
        url = f"https://search.gpto.ai/api/v1/search?query={urllib.parse.quote(q)}&count=5"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        results = data.get("results", data) if isinstance(data, dict) else data
        if isinstance(results, list):
            lines = [f"{i+1}. {r.get('title', r.get('snippet', ''))[:100]}" for i, r in enumerate(results[:5])]
            return {"ok": True, "results": "\n".join(lines)}
        return {"ok": True, "results": str(results)[:500]}
    except Exception as exc:
        return {"error": f"web search failed: {exc}"}


# ── Memory tools ──────────────────────────────────────────────────────

async def memory_search(args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query", "")
    if not query:
        return {"error": "query required"}
    try:
        from backend.memory.sqlite_backend import SQLiteMemoryBackend
        mem = SQLiteMemoryBackend()
        results = mem.search(query, limit=5)
        return {"ok": True, "results": results}
    except Exception as exc:
        return {"error": str(exc)}


async def memory_recall(args: dict[str, Any]) -> dict[str, Any]:
    limit = args.get("limit", 10)
    try:
        from backend.memory.sqlite_backend import SQLiteMemoryBackend
        mem = SQLiteMemoryBackend()
        recent = mem.list_recent(limit=limit)
        return {"ok": True, "recent": recent}
    except Exception as exc:
        return {"error": str(exc)}


# ── System tools ─────────────────────────────────────────────────────

async def system_status(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from backend.memory.sqlite_backend import SQLiteMemoryBackend
        mem = SQLiteMemoryBackend()
        return {
            "ok": True,
            "memory_nodes": mem.count(),
            "session_uptime": "N/A",
        }
    except Exception as exc:
        return {"error": str(exc)}


async def code_quality(args: dict[str, Any]) -> dict[str, Any]:
    """Run LengXiaobei's code quality suite: compile, tests, missing tests, large files, anti-patterns."""
    try:
        from backend.autonomy.code_quality import run_all_checks
        from backend.config import PROJECT_ROOT

        return run_all_checks(Path(PROJECT_ROOT))
    except Exception as exc:
        return {"error": str(exc)}


async def reflect(args: dict[str, Any]) -> dict[str, Any]:
    topic = args.get("topic", "")
    try:
        from backend.memory.sqlite_backend import SQLiteMemoryBackend
        mem = SQLiteMemoryBackend()
        recent = mem.list_recent(limit=20)
        summary_text = "\n".join(f"[{n.get('node_type')}] {n.get('content','')[:200]}" for n in recent)
        reflection = (
            f"关于「{topic}」的反思：\n"
            f"近期相关记忆 {len(recent)} 条：\n{summary_text[:1000]}\n"
            "基于以上事实，给出诚实、有主见的反思，不要泛泛而谈。"
        )
        return {"ok": True, "reflection": reflection, "recent_count": len(recent)}
    except Exception as exc:
        return {"error": str(exc)}


async def goals(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "message": "goal tracking not yet wired to persistence"}


# ── Skill tools ───────────────────────────────────────────────────────

async def skill_list(args: dict[str, Any]) -> dict[str, Any]:
    try:
        from backend.tools.skills_loader import SkillLoader
        loader = SkillLoader(PROJECT_ROOT)
        skills = loader.list_skills()
        return {"ok": True, "skills": skills}
    except Exception as exc:
        return {"error": str(exc)}


# ── Code engineering tools ─────────────────────────────────────────────

async def filesystem_edit(args: dict[str, Any]) -> dict[str, Any]:
    """Precisely replace a unique substring in a project file. Use instead of write for existing files."""
    path = args.get("path", "")
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")
    if not path or not old_string:
        return {"error": "path and old_string required"}
    try:
        from backend.tools.builtin import filesystem
        from backend.config import PROJECT_ROOT
        result = filesystem.edit_text(path=path, old_string=old_string, new_string=new_string, root=PROJECT_ROOT)
        return {"ok": True, **result}
    except ValueError as exc:
        return {"error": str(exc)}
    except PermissionError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


async def code_search(args: dict[str, Any]) -> dict[str, Any]:
    """Search for a text pattern in project source files. Returns matches with file paths and line numbers."""
    pattern = args.get("pattern", "")
    path = args.get("path", ".")
    if not pattern:
        return {"error": "pattern required"}
    try:
        from backend.tools.builtin.code_engineer import search_files
        from backend.config import PROJECT_ROOT
        return search_files(pattern=pattern, path=path, root=PROJECT_ROOT)
    except Exception as exc:
        return {"error": str(exc)}


async def list_files(args: dict[str, Any]) -> dict[str, Any]:
    """List files and directories inside the project. Use recursive=True for deep listing."""
    path = args.get("path", ".")
    recursive = args.get("recursive", False)
    try:
        from backend.tools.builtin import filesystem
        from backend.config import PROJECT_ROOT
        return filesystem.list_files(path=path, root=PROJECT_ROOT, recursive=recursive)
    except Exception as exc:
        return {"error": str(exc)}


# ── Tool registry ─────────────────────────────────────────────────────

def register_all(agent_loop: Any) -> None:
    """Register all tools with the agent loop."""
    tools = [
        ("filesystem_write", filesystem_write, "filesystem", {"path": "str", "content": "str"}),
        ("filesystem_read", filesystem_read, "filesystem", {"path": "str"}),
        ("filesystem_edit", filesystem_edit, "filesystem", {"path": "str", "old_string": "str", "new_string": "str"}),
        ("filesystem_delete", filesystem_delete, "filesystem", {"path": "str"}),
        ("shell_exec", shell_exec, "execution", {"command": "str"}),
        ("code_search", code_search, "code", {"pattern": "str", "path": "str optional"}),
        ("list_files", list_files, "code", {"path": "str optional", "recursive": "bool optional"}),
        ("web_search", web_search, "web", {"query": "str"}),
        ("memory_search", memory_search, "memory", {"query": "str"}),
        ("memory_recall", memory_recall, "memory", {"limit": "int optional"}),
        ("system_status", system_status, "runtime", {}),
        ("code_quality", code_quality, "code", {}),
        ("reflect", reflect, "reflection", {"topic": "str optional"}),
        ("goals", goals, "planning", {}),
        ("skill_list", skill_list, "skills", {}),
    ]
    for name, fn, category, schema in tools:
        agent_loop.register_tool(name, fn, category=category, input_schema=schema)


def register_dispatcher_tools(agent_loop: Any, dispatcher: Any, tool_registry: Any) -> None:
    """Expose ToolRegistry entries to AgentLoop through the Dispatcher.

    This follows OpenClaw's runtime tool-set idea: the loop should discover tools
    from the active runtime instead of depending only on a hand-maintained list.
    Builtin AgentLoop tools keep precedence so their argument shape stays stable.
    """
    if not dispatcher or not tool_registry:
        return

    async def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await dispatcher.dispatch(name, args or {})

    for item in tool_registry.describe():
        name = str(item.get("name") or "")
        if not name or name in agent_loop.tools:
            continue
        if name.startswith("controlled_agent_"):
            continue

        async def _tool(args: dict[str, Any], _name: str = name) -> dict[str, Any]:
            return await _dispatch(_name, args)

        agent_loop.register_tool(
            name,
            _tool,
            description=f"Runtime ToolRegistry tool: {item.get('callable') or name}",
            category="runtime",
        )
