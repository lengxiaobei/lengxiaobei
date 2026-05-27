#!/usr/bin/env python3
"""Record this development session into LengXiaobei's memory tree.

Usage: python3 scripts/record_development.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.memory.sqlite_backend import SQLiteBackend
from backend.memory.tree import MemoryTree


def main() -> None:
    settings = get_settings()
    sqlite = SQLiteBackend(settings.data_dir / "sqlite" / "agent.db")
    memory = MemoryTree(sqlite)

    # Node 1: Design decision — why we added Claude Tool Use
    node1 = memory.add_node(
        content=(
            "## Design Decision: Claude Native Tool Use Integration\n\n"
            "**Date:** 2026-05-27\n"
            "**Author:** Claude Opus 4.7 (external collaborator)\n\n"
            "**Problem:**\n"
            "LengXiaobei's Commander used hardcoded rule-based intent matching. "
            "When users asked open-ended questions like 'analyze this project and fix the bug', "
            "the system had no way to autonomously decide which files to read, which commands to run, "
            "and how to synthesize the result into a coherent response.\n\n"
            "**Solution:**\n"
            "1. Created `backend/core/llm/claude_adapter.py` using official `anthropic` SDK\n"
            "2. Implemented native Tool Use with automatic tool_use / tool_result loops\n"
            "3. Added Prompt Caching (`cache_control: ephemeral`) to reduce repeated context costs by ~90%\n"
            "4. Added Extended Thinking support for complex reasoning tasks\n\n"
            "**Integration:**\n"
            "- Only activates when `LLM_PROVIDER=anthropic` and `LLM_CLAUDE_ENABLE_TOOLS=true`\n"
            "- Rule-based fast path preserved for greetings, status, agent queries\n"
            "- Falls back to ollama_chat on Claude errors\n\n"
            "**Files touched:**\n"
            "- `backend/core/llm/claude_adapter.py` (new, 354 lines)\n"
            "- `backend/core/commander.py` (Claude Tool Use routing)\n"
            "- `backend/config.py` (3 new config fields)"
        ),
        node_type="design_decision",
        metadata={"topic": "claude_tool_use", "status": "implemented", "priority": "high"},
        summary="Integrated Claude native Tool Use, Prompt Caching, and Extended Thinking",
    )
    print(f"Recorded design decision: {node1.get('id')}")

    # Node 2: Implementation — CodeEngineer self-modification
    node2 = memory.add_node(
        content=(
            "## Implementation: CodeEngineer Self-Modification Engine\n\n"
            "**Date:** 2026-05-27\n"
            "**Author:** Claude Opus 4.7 (external collaborator)\n\n"
            "**Motivation:**\n"
            "User explicitly asked: '让 lengxiaobei 有改代码的能力，借鉴你的工作方式' — "
            "not just calling Claude API, but having LengXiaobei itself capable of modifying its own source code.\n\n"
            "**Architecture:**\n"
            "```\n"
            "CodeTask(description, target_files) →\n"
            "  1. LLM analyzes task + gathers context (read relevant files)\n"
            "  2. LLM generates JSON plan: [{action: read|edit|write|run|verify, ...}]\n"
            "  3. CodeEngineer executes plan step by step\n"
            "  4. Verification: python3 -m compileall + pytest\n"
            "  5. If verification fails: build retry prompt → regenerate plan → retry (max 3)\n"
            "  6. Return full execution log\n"
            "```\n\n"
            "**Key features:**\n"
            "- `edit_text`: precise string replacement (old_string must match exactly once)\n"
            "- `search_files`: ripgrep/grep based code search with line numbers\n"
            "- `list_files`: directory tree with recursive support\n"
            "- Works with ANY LLM (Ollama, token-plan, etc.), no Claude dependency\n\n"
            "**Files touched:**\n"
            "- `backend/tools/builtin/code_engineer.py` (new, ~400 lines)\n"
            "- `backend/tools/builtin/filesystem.py` (edit_text, list_files)\n"
            "- `backend/tools/registry.py` (register 4 new tools)\n"
            "- `backend/core/commander.py` (code_modification intent routing)"
        ),
        node_type="implementation",
        metadata={"topic": "code_engineer", "status": "implemented", "priority": "high"},
        summary="Built CodeEngineer: self-modification workflow engine with LLM planning + verification loop",
    )
    print(f"Recorded implementation: {node2.get('id')}")

    # Node 3: Lessons learned
    node3 = memory.add_node(
        content=(
            "## Lessons: What We Learned\n\n"
            "**Date:** 2026-05-27\n\n"
            "1. **LLM quality matters for CodeEngineer:**\n"
            "   - Local models (llama3.1) struggle with generating precise JSON plans\n"
            "   - CodeEngineer has a `_fallback_plan()` for when LLM is unavailable\n"
            "   - Recommendation: use CodeEngineer with capable cloud models (Claude, GPT-4)\n\n"
            "2. **Sandbox limits are real:**\n"
            "   - Cannot bind network ports (PermissionError)\n"
            "   - Cannot push to GitHub (HTTP 403)\n"
            "   - Cannot kill existing processes\n"
            "   - Workaround: user runs `make backend` / `make frontend` manually\n\n"
            "3. **Intent detection precision:**\n"
            "   - 11/12 tests passed for code_modification detection\n"
            "   - Edge case: '添加新功能到 stores' missed because 'stores' isn't a code keyword\n"
            "   - Solution: keep expanding keyword lists or move to semantic classification\n\n"
            "4. **Future work:**\n"
            "   - Add CodeEngineer to autonomy loop for periodic self-improvement\n"
            "   - Implement skill extraction from successful CodeEngineer runs\n"
            "   - Add code quality metrics (cyclomatic complexity, test coverage)\n"
            "   - Allow CodeEngineer to create new files, not just edit existing ones"
        ),
        node_type="lessons_learned",
        metadata={"topic": "code_engineer", "status": "documented", "priority": "medium"},
        summary="Lessons from implementing Claude Tool Use + CodeEngineer",
    )
    print(f"Recorded lessons: {node3.get('id')}")

    print("\nAll development records written to memory tree.")
    print(f"Database: {settings.data_dir / 'sqlite' / 'agent.db'}")


if __name__ == "__main__":
    main()
