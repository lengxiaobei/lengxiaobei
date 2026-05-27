import asyncio
from pathlib import Path

from backend.core.dispatcher import Dispatcher
from backend.memory.sqlite_backend import SQLiteBackend
from backend.memory.tree import MemoryTree
from backend.tools.registry import ToolRegistry
from backend.utils.logger import get_logger


def test_project_write_and_shell_tools(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    memory = MemoryTree(sqlite)
    tools = ToolRegistry(tmp_path, memory=memory)
    dispatcher = Dispatcher(tools, get_logger("test-write-tools"), sqlite=sqlite)

    assert "filesystem_write" in tools.list()
    assert "shell_exec" in tools.list()

    write = asyncio.run(
        dispatcher.dispatch(
            "filesystem_write",
            {"path": "scratch/generated.txt", "content": "hello from cold north\n"},
        )
    )
    assert write["ok"] is True
    assert (tmp_path / "scratch" / "generated.txt").read_text() == "hello from cold north\n"

    command = asyncio.run(dispatcher.dispatch("shell_exec", {"command": ["python3", "-c", "print('ok')"]}))
    assert command["ok"] is True
    assert command["result"]["stdout"].strip() == "ok"


def test_secret_files_are_not_exposed(tmp_path: Path):
    (tmp_path / ".env").write_text("LLM_API_KEY=secret\n")
    tools = ToolRegistry(tmp_path)
    dispatcher = Dispatcher(tools, get_logger("test-secret-tools"))

    result = asyncio.run(dispatcher.dispatch("filesystem_read", {"path": ".env"}))

    assert result["ok"] is False
    assert "LLM_API_KEY=secret" not in str(result)
