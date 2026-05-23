from pathlib import Path

from backend.memory.sqlite_backend import SQLiteBackend
from backend.memory.tree import MemoryTree
from backend.memory.vector_store import VectorStore


def test_memory_tree_crud_and_vector_search(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    tree = MemoryTree(sqlite)
    vector = VectorStore(tree, sqlite=sqlite, persist_dir=str(tmp_path / "chroma"))

    node = tree.add_node("OpenHuman memory tree banana", "knowledge")
    vector.index_node(node)

    assert tree.get(node["id"])["content"].startswith("OpenHuman")
    assert vector.search("banana", limit=1)[0]["id"] == node["id"]

    updated = tree.update_node(node["id"], summary="fruit memory")
    assert updated["summary"] == "fruit memory"
    assert tree.delete_node(node["id"]) is True
