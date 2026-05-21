"""
KAIROS 每日日志管理器 (DailyLogManager)

Append-only 日志，按日期组织：logs/YYYY/MM/YYYY-MM-DD.md
"""

import os
import time
import json
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta


class DailyLogManager:
    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.logs_dir = memory_dir / "logs"
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.current_log_file: Optional[Path] = None

    def _get_log_path(self, date: Optional[str] = None) -> Path:
        dt = datetime.now() if date is None else datetime.strptime(date, "%Y-%m-%d")
        return self.logs_dir / str(dt.year) / f"{dt.month:02d}" / f"{dt.strftime('%Y-%m-%d')}.md"

    def _ensure_log_file(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.current_date or self.current_log_file is None:
            self.current_date = today
            self.current_log_file = self._get_log_path()
            self.current_log_file.parent.mkdir(parents=True, exist_ok=True)
        return self.current_log_file

    def append_entry_sync(self, entry_type: str, content: str, metadata: Optional[Dict] = None) -> Path:
        """同步写入日志条目（供同步上下文调用，避免 asyncio.run 嵌套）"""
        log_file = self._ensure_log_file()
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"- [{timestamp}] **{entry_type}**: {content}"
        if metadata:
            meta_str = json.dumps(metadata, ensure_ascii=False)
            entry += f" <!-- {meta_str} -->"
        entry += "\n"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        return log_file

    async def append_entry(self, entry_type: str, content: str, metadata: Optional[Dict] = None):
        """异步写入日志条目（供 async 上下文调用）"""
        return self.append_entry_sync(entry_type, content, metadata)

    async def get_recent_entries(self, hours: int = 24) -> List[Dict]:
        entries = []
        for days_back in [0, 1]:
            date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            log_file = self._get_log_path(date)
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('- ['):
                            entries.append({'date': date, 'raw': line})
        return entries

    def get_daily_log_prompt(self) -> str:
        memory_dir = str(self.memory_dir)
        log_pattern = str(self.logs_dir / "YYYY" / "MM" / "YYYY-MM-DD.md")
        return f"""# auto memory

You have a persistent, file-based memory system found at: `{memory_dir}`

This session is long-lived. As you work, record anything worth remembering by **appending** to today's daily log file:

`{log_pattern}`

Substitute today's date (from `currentDate` in your context) for `YYYY-MM-DD`. When the date rolls over mid-session, start appending to the new day's file.

Write each entry as a short timestamped bullet. Create the file (and parent directories) on first write if it does not exist. Do not rewrite or reorganize the log — it is append-only. A separate nightly process distills these logs into `MEMORY.md` and topic files.

## What to log
- User corrections and preferences ("use bun, not npm"; "stop summarizing diffs")
- Facts about the user, their role, or their goals
- Project context that is not derivable from the code (deadlines, incidents, decisions and their rationale)
- Pointers to external systems (dashboards, Linear projects, Slack channels)
- Anything the user explicitly asks you to remember

## What NOT to save
- Code snippets (the codebase is the source of truth)
- File contents (use read_file when needed)
- Transient errors (unless they reveal a persistent issue)
- Anything the user asks you to forget

## MEMORY.md
`MEMORY.md` is the distilled index (maintained nightly from your logs) and is loaded into your context automatically. Read it for orientation, but do not edit it directly — record new information in today's log instead."""