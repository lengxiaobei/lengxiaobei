"""
AutoDream V2 — 照搬 Claude Code 设计
=====================================
核心特性：
- 三层门控：Time Gate + Session Gate + Lock Gate
- 文件锁：mtime = lastConsolidatedAt, 内容 = PID
- Forked Agent 架构（Python 版：异步子任务）
- 4 阶段 Consolidation：Orient → Gather → Consolidate → Prune & Index
"""

import os
import time
import json
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime

from .memory import Memory
from .llm import chat, route


# ============================================================================
# 配置（照搬 tengu_onyx_plover）
# ============================================================================

@dataclass
class DreamConfig:
    min_hours: float = 24.0           # Time Gate: 最少24小时
    min_sessions: int = 5             # Session Gate: 最少5个新会话
    scan_interval_ms: int = 600_000   # Scan Throttle: 10分钟
    lock_stale_ms: int = 3_600_000    # Lock 过期: 1小时
    max_entrypoint_lines: int = 200   # MEMORY.md 行数限制
    max_entrypoint_bytes: int = 25_000  # MEMORY.md 字节限制


# ============================================================================
# 分布式锁（使用新的分布式锁实现）
# ============================================================================
from .distributed_lock import get_lock


class ConsolidationLock:
    """
    分布式锁机制：
    - 使用新的分布式锁实现
    - 支持超时自动释放
    - 支持死锁检测
    - 支持锁的获取和释放
    """
    
    def __init__(self, memory_dir: Path, stale_ms: int = 3_600_000):
        self.memory_dir = memory_dir
        self.stale_ms = stale_ms
        self.lock = get_lock("auto_dream", timeout=int(stale_ms / 1000))
    
    async def read_last_consolidated_at(self) -> float:
        """获取上次整理时间"""
        lock_info = self.lock.get_lock_info()
        if lock_info:
            return lock_info.get('acquired_at') or 0
        return 0
    
    async def try_acquire(self) -> Optional[float]:
        """
        获取锁
        Returns the pre-acquire mtime (for rollback), or None if blocked.
        """
        prior_mtime = await self.read_last_consolidated_at()
        if self.lock.acquire(block=False):
            return prior_mtime
        else:
            return None
    
    async def rollback(self, prior_mtime: float):
        """回滚锁状态"""
        self.lock.release()
    
    def _is_process_running(self, pid: int) -> bool:
        """检查 PID 是否存在（使用标准库）"""
        try:
            # 发送信号 0 检查进程是否存在
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


# ============================================================================
# 门控检查器
# ============================================================================

class GateChecker:
    """
    门控检查器：负责三层门控逻辑
    """
    
    def __init__(self, config: DreamConfig, lock: ConsolidationLock, project_root: Path):
        self.config = config
        self.lock = lock
        self.project_root = project_root
        self.last_scan_at = 0
    
    async def should_run(self) -> bool:
        """
        三层门控检查（从便宜到昂贵）
        """
        # 1. Time Gate
        last_at = await self.lock.read_last_consolidated_at()
        hours_since = (time.time() - last_at) / 3600
        if hours_since < self.config.min_hours:
            return False
        
        # 2. Scan Throttle
        since_scan_ms = (time.time() - self.last_scan_at) * 1000
        if since_scan_ms < self.config.scan_interval_ms:
            print(f"[autoDream] scan throttle — last scan was {since_scan_ms/1000:.0f}s ago")
            return False
        self.last_scan_at = time.time()
        
        # 3. Session Gate
        session_ids = await self._list_sessions_touched_since(last_at)
        if len(session_ids) < self.config.min_sessions:
            print(f"[autoDream] skip — {len(session_ids)} sessions, need {self.config.min_sessions}")
            return False
        
        # 4. Lock Gate
        prior_mtime = await self.lock.try_acquire()
        if prior_mtime is None:
            return False
        
        return True
    
    async def _list_sessions_touched_since(self, since_ms: float) -> List[str]:
        """列出自上次整理以来有更新的会话"""
        sessions = []
        sessions_dir = self.project_root / "memory" / "sessions"
        
        if not sessions_dir.exists():
            return sessions
        
        for file_path in sessions_dir.glob("*.jsonl"):
            try:
                stat = file_path.stat()
                if stat.st_mtime > since_ms:
                    sessions.append(file_path.stem)
            except Exception:
                pass
        
        return sessions


# ============================================================================
# 4 阶段 Consolidation Prompt（照搬 consolidationPrompt.ts）
# ============================================================================

ENTRYPOINT_NAME = "MEMORY.md"
DIR_EXISTS_GUIDANCE = "This directory already exists — write to it directly (do not run mkdir or check for its existence)."


def build_consolidation_prompt(memory_root: str, transcript_dir: str, extra: str = "") -> str:
    """照搬 Claude Code 的 4 阶段提示词"""
    return f"""# Dream: Memory Consolidation

You are performing a dream — a reflective pass over your memory files. Synthesize what you've learned recently into durable, well-organized memories so that future sessions can orient quickly.

Memory directory: `{memory_root}`
{DIR_EXISTS_GUIDANCE}

Session transcripts: `{transcript_dir}` (large JSONL files — grep narrowly, don't read whole files)

---

## Phase 1 — Orient

- `ls` the memory directory to see what already exists
- Read `{ENTRYPOINT_NAME}` to understand the current index
- Skim existing topic files so you improve them rather than creating duplicates
- If `logs/` or `sessions/` subdirectories exist (assistant-mode layout), review recent entries there

## Phase 2 — Gather recent signal

Look for new information worth persisting. Sources in rough priority order:

1. **Daily logs** (`logs/YYYY/MM/YYYY-MM-DD.md`) if present — these are the append-only stream
2. **Existing memories that drifted** — facts that contradict something you see in the codebase now
3. **Transcript search** — if you need specific context (e.g., "what was the error message from yesterday's build failure?"), grep the JSONL transcripts for narrow terms:
   `grep -rn "<narrow term>" {transcript_dir}/ --include="*.jsonl" | tail -50`

Don't exhaustively read transcripts. Look only for things you already suspect matter.

## Phase 3 — Consolidate

For each thing worth remembering, write or update a memory file at the top level of the memory directory. Use the memory file format and type conventions from your system prompt's auto-memory section — it's the source of truth for what to save, how to structure it, and what NOT to save.

Focus on:
- Merging new signal into existing topic files rather than creating near-duplicates
- Converting relative dates ("yesterday", "last week") to absolute dates so they remain interpretable after time passes
- Deleting contradicted facts — if today's investigation disproves an old memory, fix it at the source

## Phase 4 — Prune and index

Update `{ENTRYPOINT_NAME}` so it stays under 200 lines AND under ~25KB. It's an **index**, not a dump — each entry should be one line under ~150 characters: `- [Title](file.md) — one-line hook`. Never write memory content directly into it.

- Remove pointers to memories that are now stale, wrong, or superseded
- Demote verbose entries: if an index line is over ~200 chars, it's carrying content that belongs in the topic file — shorten the line, move the detail
- Add pointers to newly important memories
- Resolve contradictions — if two files disagree, fix the wrong one

---

Return a brief summary of what you consolidated, updated, or pruned. If nothing changed (memories are already tight), say so.{extra if extra else ''}"""


# ============================================================================
# 进度跟踪器
# ============================================================================

@dataclass
class DreamProgress:
    phase: str
    status: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DreamResult:
    success: bool
    sessions_reviewed: int
    files_touched: List[str]
    summary: str
    cache_read_tokens: int = 0
    cache_created_tokens: int = 0
    output_tokens: int = 0


class ProgressTracker:
    """
    进度跟踪器：负责生成进度信息
    """
    
    def __init__(self):
        pass
    
    def start_progress(self, hours_since: float, sessions: int) -> DreamProgress:
        return DreamProgress(
            phase="start",
            status="firing",
            details={"hours_since": hours_since, "sessions": sessions}
        )
    
    def orient_progress(self) -> DreamProgress:
        return DreamProgress(phase="orient", status="scanning_memory")
    
    def gather_progress(self) -> DreamProgress:
        return DreamProgress(phase="gather", status="collecting_signal")
    
    def consolidate_progress(self) -> DreamProgress:
        return DreamProgress(phase="consolidate", status="synthesizing")
    
    def index_progress(self, files_touched: List[str]) -> DreamProgress:
        return DreamProgress(
            phase="index",
            status="updating_index",
            details={"files_touched": files_touched}
        )
    
    def complete_progress(self, summary: str, files_touched: List[str]) -> DreamProgress:
        return DreamProgress(
            phase="complete",
            status="done",
            details={
                "summary": summary,
                "files_touched": files_touched
            }
        )
    
    def error_progress(self, error: str) -> DreamProgress:
        return DreamProgress(phase="error", status="failed", details={"error": error})
    
    def skip_progress(self, reason: str) -> DreamProgress:
        return DreamProgress(phase="skip", status=reason)


# ============================================================================
# AutoDream V2 主类（照搬 autoDream.ts）
# ============================================================================

class AutoDreamV2:
    """
    照搬 Claude Code 的 autoDream.ts
    
    核心流程：
    1. 三层门控检查（Time + Session + Lock）
    2. Forked Agent 执行（Python: 异步子任务）
    3. 进度监听（onMessage 回调）
    4. 完成/失败处理
    """
    
    def __init__(self, memory: Memory, project_root: str):
        self.memory = memory
        self.project_root = Path(project_root)
        self.memory_dir = self.project_root / "memory"
        self.config = DreamConfig()
        self.lock = ConsolidationLock(self.memory_dir, self.config.lock_stale_ms)
        self.gate_checker = GateChecker(self.config, self.lock, self.project_root)
        self.progress_tracker = ProgressTracker()
        
        # 状态
        self.is_running = False
    
    def is_gate_open(self) -> bool:
        """检查是否满足运行条件"""
        # TODO: 添加 KAIROS 检查、Remote Mode 检查
        return True
    
    async def should_run(self) -> bool:
        """
        使用门控检查器进行检查
        """
        return await self.gate_checker.should_run()
    
    async def run_dream(self) -> AsyncGenerator[DreamProgress, None]:
        """
        执行记忆整理（异步生成器，实时报告进度）
        照搬 runAutoDream 函数
        """
        if self.is_running:
            yield self.progress_tracker.skip_progress("already_running")
            return
        
        self.is_running = True
        
        try:
            # 获取锁（在 should_run 中已经获取，这里取 prior_mtime）
            last_at = await self.lock.read_last_consolidated_at()
            prior_mtime = await self.lock.try_acquire()
            
            if prior_mtime is None:
                yield self.progress_tracker.skip_progress("lock_failed")
                return
            
            # 获取会话列表
            session_ids = await self.gate_checker._list_sessions_touched_since(last_at)
            hours_since = (time.time() - last_at) / 3600
            
            print(f"[autoDream] firing — {hours_since:.1f}h since last, {len(session_ids)} sessions to review")
            
            yield self.progress_tracker.start_progress(hours_since, len(session_ids))
            
            # 构建提示词
            memory_root = str(self.memory_dir)
            transcript_dir = str(self.project_root / "memory" / "sessions")
            session_list = "".join(f"- {sid}\n" for sid in session_ids)
            extra = f"""

Sessions since last consolidation ({len(session_ids)}):
{session_list}"""
            
            prompt = build_consolidation_prompt(memory_root, transcript_dir, extra)
            
            # Phase 1: Orient
            yield self.progress_tracker.orient_progress()
            
            # Phase 2: Gather
            yield self.progress_tracker.gather_progress()
            
            # Phase 3: Consolidate (LLM)
            yield self.progress_tracker.consolidate_progress()
            
            # 调用 LLM（简化版，实际应该用 forked agent）
            try:
                response = chat(
                    prompt=prompt,
                    system="You are a memory consolidation agent. Follow the 4-phase process carefully.",
                    model=route(prompt),
                    temperature=0.3,
                )
                
                # 解析 LLM 输出，提取文件操作
                files_touched = self._extract_files_from_response(response)
                
                yield self.progress_tracker.index_progress(files_touched)
                
                # 完成
                yield self.progress_tracker.complete_progress(response[:200], files_touched)
                
            except Exception as e:
                # 失败，回滚锁
                await self.lock.rollback(prior_mtime)
                yield self.progress_tracker.error_progress(str(e))
                
        finally:
            self.is_running = False
    
    def _extract_files_from_response(self, response: str) -> List[str]:
        """从 LLM 响应中提取操作的文件列表"""
        files = []
        # 简单提取：查找 .md 文件引用
        import re
        md_files = re.findall(r'[\w\-]+\.md', response)
        files.extend(md_files)
        return list(set(files))
    
    async def execute(self) -> Optional[DreamResult]:
        """
        同步执行接口（返回结果）
        用于后台任务调用
        """
        if not await self.should_run():
            return None
        
        files_touched = []
        summary = ""
        
        async for progress in self.run_dream():
            if progress.phase == "complete":
                files_touched = progress.details.get("files_touched", [])
                summary = progress.details.get("summary", "")
            elif progress.phase == "error":
                return DreamResult(
                    success=False,
                    sessions_reviewed=0,
                    files_touched=[],
                    summary=f"Failed: {progress.details.get('error', 'Unknown error')}"
                )
        
        # 获取会话数量
        last_at = await self.lock.read_last_consolidated_at()
        session_ids = await self.gate_checker._list_sessions_touched_since(last_at)
        
        return DreamResult(
            success=True,
            sessions_reviewed=len(session_ids),
            files_touched=files_touched,
            summary=summary
        )


# ============================================================================
# 便捷函数
# ============================================================================

async def execute_auto_dream(memory: Memory, project_root: str) -> Optional[DreamResult]:
    """便捷函数：执行一次 autoDream"""
    dream = AutoDreamV2(memory, project_root)
    return await dream.execute()