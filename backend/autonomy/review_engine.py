"""Review engine — periodic trace review and learning reports.

参考来源：Hermes 的 Nudge 系统 — 定期回顾执行轨迹，
生成学习报告，发现改进机会，清理低质量记忆和技能。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class ReviewEngine:
    """定期复盘引擎：分析轨迹、生成报告、发现改进机会。"""

    def __init__(
        self,
        sqlite: Any,
        memory: Any,
        skill_store: Any,
        llm_completer: Callable[[str, str], Awaitable[str]] | None = None,
    ):
        self.sqlite = sqlite
        self.memory = memory
        self.skill_store = skill_store
        self.llm_completer = llm_completer
        self._last_review_at: float = 0
        self._review_count: int = 0

    async def daily_review(self) -> dict[str, Any]:
        """每日复盘：分析最近 24 小时的轨迹。"""
        cutoff = time.time() - 86400  # 24 hours
        return await self._review_since(cutoff, "daily")

    async def weekly_review(self) -> dict[str, Any]:
        """每周复盘：分析最近 7 天的轨迹。"""
        cutoff = time.time() - 7 * 86400
        return await self._review_since(cutoff, "weekly")

    async def _review_since(self, cutoff: float, period: str) -> dict[str, Any]:
        """分析指定时间段的轨迹，生成复盘报告。"""
        # Gather stats
        runs = self.sqlite.trace_list_runs(limit=100) if self.sqlite else []
        recent_runs = [r for r in runs if (r.get("created_at") or 0) > cutoff]

        total = len(recent_runs)
        success = sum(1 for r in recent_runs if r.get("status") == "completed")
        failed = sum(1 for r in recent_runs if r.get("status") == "completed_with_errors")

        # Get failure patterns
        failure_patterns = self.sqlite.get_failure_patterns(min_occurrences=1) if self.sqlite else []

        # Get skill stats
        skills = self.skill_store.list_with_stats() if self.skill_store else []
        low_quality = [s for s in skills if (s.get("total_uses") or 0) >= 3 and (s.get("success_rate") or 100) < 40]

        # Build report
        report = {
            "period": period,
            "cutoff": cutoff,
            "generated_at": time.time(),
            "run_stats": {
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": round(success / total * 100, 1) if total > 0 else 0,
            },
            "failure_patterns": [
                {
                    "tool": p.get("tool"),
                    "pattern": p.get("pattern", "")[:100],
                    "occurrences": p.get("occurrence_count", 0),
                }
                for p in failure_patterns[:5]
            ],
            "low_quality_skills": [
                {
                    "name": s.get("name"),
                    "success_rate": s.get("success_rate", 0),
                    "uses": s.get("total_uses", 0),
                }
                for s in low_quality[:5]
            ],
            "recommendations": [],
        }

        # Generate recommendations
        if failed > total * 0.3 and total > 0:
            report["recommendations"].append("失败率较高，建议检查常见失败模式并生成对应技能")
        if failure_patterns:
            report["recommendations"].append(f"有 {len(failure_patterns)} 个未解决的失败模式需要关注")
        if low_quality:
            report["recommendations"].append(f"有 {len(low_quality)} 个低质量技能建议降权或删除")

        # LLM analysis if available
        if self.llm_completer and total > 0:
            try:
                analysis = await self._llm_analyze(report)
                report["llm_analysis"] = analysis
            except Exception as e:
                logger.warning("LLM analysis failed: %s", e)

        # Store review as memory node
        try:
            self.memory.add_node(
                content=f"{period}复盘: {total}次运行, 成功率{report['run_stats']['success_rate']}%",
                node_type="review",
                metadata=report,
                summary=f"{period}复盘报告",
            )
        except Exception:
            pass

        self._last_review_at = time.time()
        self._review_count += 1

        logger.info(
            "%s review: %d runs, %.1f%% success, %d failure patterns, %d low-quality skills",
            period, total, report["run_stats"]["success_rate"],
            len(failure_patterns), len(low_quality),
        )

        return report

    async def _llm_analyze(self, report: dict[str, Any]) -> str:
        """用 LLM 分析复盘数据，生成改进建议。"""
        import json
        prompt = (
            "分析以下智能体运行复盘数据，给出具体改进建议：\n\n"
            f"{json.dumps(report, ensure_ascii=False, indent=2)}\n\n"
            "从以下角度分析：\n"
            "1. 失败模式的根本原因\n"
            "2. 技能系统的改进方向\n"
            "3. 提高成功率的具体措施\n"
            "输出简洁的分析文本，不超过200字。"
        )
        return await self.llm_completer(prompt, "你是智能体运维分析师。")

    def cleanup_stale(self, max_age_days: int = 30) -> dict[str, Any]:
        """清理过期的记忆和技能。"""
        cutoff = time.time() - max_age_days * 86400
        result = {"cleaned_memories": 0, "cleaned_skills": 0}

        # Clean old memory nodes (keep facts and reviews longer)
        if self.sqlite:
            try:
                with self.sqlite.connect() as conn:
                    # Delete old conversation memories older than max_age_days
                    cursor = conn.execute(
                        "DELETE FROM memory_nodes WHERE node_type='conversation' AND created_at < ?",
                        (cutoff,)
                    )
                    result["cleaned_memories"] = cursor.rowcount

                    # Clean resolved failure patterns older than 2x max_age
                    old_cutoff = time.time() - max_age_days * 2 * 86400
                    cursor = conn.execute(
                        "DELETE FROM failure_patterns WHERE resolved=1 AND last_seen_at < ?",
                        (old_cutoff,)
                    )
            except Exception as e:
                logger.warning("Cleanup failed: %s", e)

        logger.info("Cleanup: %s", result)
        return result

    def stats(self) -> dict[str, Any]:
        return {
            "review_count": self._review_count,
            "last_review_at": self._last_review_at,
        }
