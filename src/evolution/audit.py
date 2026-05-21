"""
进化审计日志
============
结构化 JSONL 审计记录，每次进化运行一行，包含完整溯源链：

Discover → Triage → Propose → Review → Execute → Verify → Record

每步记录：发生了什么、什么时间、谁/什么触发的、结果如何。
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AuditEntry:
    """单次进化运行的完整审计记录"""
    # 元信息
    run_id: str
    started_at: float = field(default_factory=time.time)
    trigger: str = "manual"          # manual | kairos | curator | autonomous

    # Discover — 发现了什么
    discover: Dict[str, Any] = field(default_factory=dict)
    # 例: {"files_scanned": 12, "improvements_found": 3, "source": "curator"}

    # Triage — 风险分级
    triage: Dict[str, Any] = field(default_factory=dict)
    # 例: {"risk_score": 0.3, "risk_level": "low", "rationale": "仅修改变量命名"}

    # Propose — 补丁方案
    propose: Dict[str, Any] = field(default_factory=dict)
    # 例: {"strategy": "rename", "approach": "...", "confidence": 0.85, "patch_preview": "..."}

    # Review — 治理检查
    review: Dict[str, Any] = field(default_factory=dict)
    # 例: {"constitution": "allowed", "permission": "granted", "impact_scope": "1 file"}

    # Execute — 执行结果
    execute: Dict[str, Any] = field(default_factory=dict)
    # 例: {"file": "src/foo.py", "backup": "backups/foo.20260521.py", "lines_changed": 5}

    # Verify — 验证结果
    verify: Dict[str, Any] = field(default_factory=dict)
    # 例: {"tests_passed": 12, "tests_failed": 0, "linter": "clean"}

    # Record — 技能沉淀 / 回滚
    record: Dict[str, Any] = field(default_factory=dict)
    # 例: {"skill_card": "rename-variables", "rollback_ref": "backup-xxx"}

    # 结束状态
    status: str = "running"           # running | success | failed | rejected
    ended_at: Optional[float] = None
    error: Optional[str] = None

    def finish(self, status: str, error: str = None):
        self.status = status
        self.error = error
        self.ended_at = time.time()

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class AuditTrail:
    """进化审计日志 — JSONL 追加写入"""

    def __init__(self, project_root: str):
        self.log_path = Path(project_root) / "evolution_runs.jsonl"
        self._ensure_dir()

    def _ensure_dir(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def start_run(self, run_id: str, trigger: str = "manual") -> AuditEntry:
        return AuditEntry(run_id=run_id, trigger=trigger)

    def log_phase(self, entry: AuditEntry, phase: str, data: Dict[str, Any]):
        """记录某个阶段的数据"""
        if hasattr(entry, phase):
            setattr(entry, phase, data)

    def finish_and_write(self, entry: AuditEntry, status: str, error: str = None):
        """完成审计记录并写入 JSONL"""
        entry.finish(status, error)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def read_recent(self, limit: int = 20) -> List[Dict]:
        """读取最近 N 条审计记录"""
        if not self.log_path.exists():
            return []
        records = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        return records[-limit:]

    def search(self, status: str = None, trigger: str = None) -> List[Dict]:
        """按状态或触发方式搜索"""
        results = []
        if not self.log_path.exists():
            return results
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if status and r.get("status") != status:
                    continue
                if trigger and r.get("trigger") != trigger:
                    continue
                results.append(r)
        return results

    def stats(self) -> Dict[str, Any]:
        """统计摘要"""
        records = self.read_recent(1000)
        total = len(records)
        if total == 0:
            return {"total_runs": 0}

        success = sum(1 for r in records if r.get("status") == "success")
        failed = sum(1 for r in records if r.get("status") == "failed")
        rejected = sum(1 for r in records if r.get("status") == "rejected")

        triggers = {}
        risk_levels = {}
        for r in records:
            t = r.get("trigger", "unknown")
            triggers[t] = triggers.get(t, 0) + 1
            rl = r.get("triage", {}).get("risk_level", "unknown")
            risk_levels[rl] = risk_levels.get(rl, 0) + 1

        return {
            "total_runs": total,
            "success": success,
            "failed": failed,
            "rejected": rejected,
            "success_rate": round(success / total * 100, 1) if total else 0,
            "by_trigger": triggers,
            "by_risk_level": risk_levels,
        }