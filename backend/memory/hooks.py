"""Memory hooks for auto-recall and promotion.

参考来源：OpenClaw 的 memory-engine 插件 —— auto-recall（对话时自动检索相关记忆注入上下文）
和 short-term promotion（定期将短期记忆提升为长期记忆）。

植入目标：让 lengxiaobei 的记忆系统具备 OpenClaw 级别的自动记忆管理能力。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class RecallResult:
    """A single recalled memory node."""
    id: str
    content: str
    score: float = 0.0
    node_type: str = "knowledge"
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryHooks:
    """Auto-recall and promotion hooks for the memory system.

    Integrates with MemoryTree and VectorStore to provide:
    - Auto-recall: inject relevant memories into conversation context
    - Short-term promotion: promote weighted recalls to long-term MEMORY.md
    - Temporal decay: half-life based relevance scoring
    """

    def __init__(
        self,
        memory_tree: Any = None,
        vector_store: Any = None,
        max_results: int = 5,
        min_score: float = 0.3,
        promotion_threshold: float = 0.8,
        promotion_min_recalls: int = 3,
        promotion_min_queries: int = 3,
        decay_half_life_days: float = 30.0,
    ) -> None:
        self.memory = memory_tree
        self.vector_store = vector_store
        self.max_results = max_results
        self.min_score = min_score
        self.promotion_threshold = promotion_threshold
        self.promotion_min_recalls = promotion_min_recalls
        self.promotion_min_queries = promotion_min_queries
        self.decay_half_life_days = decay_half_life_days

        # Track recall counts for promotion decisions
        self._recall_counts: dict[str, int] = {}  # node_id -> count
        self._recall_queries: dict[str, set[str]] = {}  # node_id -> set of query strings
        self._recall_scores: dict[str, float] = {}  # node_id -> accumulated score

    # ── Auto-Recall ──────────────────────────────────────────────────

    async def auto_recall(self, message: str, limit: int | None = None) -> list[RecallResult]:
        """Search memory for context relevant to the incoming message.

        Called before each LLM turn. Returns top-K memories to inject into context.
        """
        if not self.memory:
            return []

        limit = limit or self.max_results
        query = self._extract_query(message)

        try:
            # Use vector search if available, fall back to keyword search
            if self.vector_store:
                raw_results = self.vector_store.search(query, limit=limit * 2)
            else:
                raw_results = self.memory.search(query, limit=limit * 2)

            results: list[RecallResult] = []
            for node in raw_results:
                score = float(node.get("score", 0.0))
                if score < self.min_score:
                    continue

                # Apply temporal decay
                created_at = node.get("created_at") or node.get("metadata", {}).get("created_at")
                if created_at:
                    try:
                        age_days = (time.time() - _parse_timestamp(created_at)) / 86400
                        decay = 0.5 ** (age_days / self.decay_half_life_days)
                        score *= decay
                    except Exception:
                        pass

                result = RecallResult(
                    id=str(node.get("id", "")),
                    content=str(node.get("content", "")),
                    score=score,
                    node_type=str(node.get("node_type", "knowledge")),
                    metadata=node.get("metadata", {}),
                )
                results.append(result)

                # Track for promotion
                nid = result.id
                self._recall_counts[nid] = self._recall_counts.get(nid, 0) + 1
                if nid not in self._recall_queries:
                    self._recall_queries[nid] = set()
                self._recall_queries[nid].add(query)
                self._recall_scores[nid] = max(self._recall_scores.get(nid, 0.0), score)

            # Sort by score, take top-K
            results.sort(key=lambda r: r.score, reverse=True)
            return results[:limit]

        except Exception as exc:
            logger.warning("Auto-recall failed: %s", exc)
            return []

    def format_recall_context(self, results: list[RecallResult]) -> str:
        """Format recall results as context string for LLM injection."""
        if not results:
            return ""
        lines = ["[相关记忆]"]
        for r in results:
            lines.append(f"- [{r.node_type}] {r.content}")
        return "\n".join(lines)

    # ── Short-Term Promotion ─────────────────────────────────────────

    def get_promotion_candidates(self) -> list[dict[str, Any]]:
        """Find memory nodes that qualify for promotion to long-term.

        Promotion criteria (mirrors OpenClaw memory-core):
        - recall_count >= promotion_min_recalls
        - unique_queries >= promotion_min_queries
        - max_score >= promotion_threshold
        """
        candidates = []
        for nid, count in self._recall_counts.items():
            if count < self.promotion_min_recalls:
                continue
            queries = self._recall_queries.get(nid, set())
            if len(queries) < self.promotion_min_queries:
                continue
            max_score = self._recall_scores.get(nid, 0.0)
            if max_score < self.promotion_threshold:
                continue
            candidates.append({
                "node_id": nid,
                "recall_count": count,
                "unique_queries": len(queries),
                "max_score": max_score,
            })
        return candidates

    async def promote_node(self, node_id: str, memory_md_path: str | None = None) -> bool:
        """Promote a short-term memory node to long-term MEMORY.md."""
        if not self.memory:
            return False

        node = self.memory.get(node_id)
        if not node:
            return False

        content = node.get("content", "")
        if not content:
            return False

        # Write to MEMORY.md if path provided
        if memory_md_path:
            try:
                from pathlib import Path
                path = Path(memory_md_path)
                existing = path.read_text(encoding="utf-8") if path.exists() else ""
                entry = f"\n\n## Auto-promoted ({time.strftime('%Y-%m-%d')})\n\n{content}\n"
                path.write_text(existing + entry, encoding="utf-8")
                logger.info("Promoted node %s to %s", node_id, memory_md_path)
            except Exception as exc:
                logger.error("Failed to promote node %s: %s", node_id, exc)
                return False

        # Update node type to indicate promotion
        try:
            self.memory.update_node(node_id, node_type="long_term", metadata={
                **node.get("metadata", {}),
                "promoted_at": time.time(),
                "promoted": True,
            })
        except Exception:
            pass

        # Clear tracking
        self._recall_counts.pop(node_id, None)
        self._recall_queries.pop(node_id, None)
        self._recall_scores.pop(node_id, None)

        return True

    async def run_promotion_cycle(self, memory_md_path: str | None = None) -> dict[str, Any]:
        """Run a full promotion cycle. Call periodically (e.g., every 30 min)."""
        candidates = self.get_promotion_candidates()
        promoted = []
        for c in candidates:
            ok = await self.promote_node(c["node_id"], memory_md_path)
            if ok:
                promoted.append(c["node_id"])
        return {
            "candidates": len(candidates),
            "promoted": len(promoted),
            "promoted_ids": promoted,
        }

    # ── Helpers ──────────────────────────────────────────────────────

    def _extract_query(self, message: str) -> str:
        """Extract a search query from the user message.

        Simple heuristic: use the full message, trimmed to reasonable length.
        For production, consider keyword extraction or embedding-based query.
        """
        # Trim to 500 chars for search efficiency
        query = message.strip()[:500]
        # Remove common prefixes
        for prefix in ["请", "帮我", "能不能", "可以", "你"]:
            if query.startswith(prefix):
                query = query[len(prefix):].lstrip("，,：: ")
        return query

    def get_stats(self) -> dict[str, Any]:
        """Return hook statistics for monitoring."""
        return {
            "tracked_nodes": len(self._recall_counts),
            "total_recalls": sum(self._recall_counts.values()),
            "promotion_candidates": len(self.get_promotion_candidates()),
            "max_score": max(self._recall_scores.values()) if self._recall_scores else 0.0,
        }


def _parse_timestamp(ts: str | float | int) -> float:
    """Parse a timestamp string to epoch seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        import datetime
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.datetime.strptime(str(ts)[:19], fmt).timestamp()
            except ValueError:
                continue
        return float(ts)
    except Exception:
        return time.time()


# ── Singleton ───────────────────────────────────────────────────────

_hooks: MemoryHooks | None = None


def get_memory_hooks(
    memory_tree: Any = None,
    vector_store: Any = None,
    **kwargs: Any,
) -> MemoryHooks:
    global _hooks
    if _hooks is None:
        _hooks = MemoryHooks(memory_tree=memory_tree, vector_store=vector_store, **kwargs)
    return _hooks
