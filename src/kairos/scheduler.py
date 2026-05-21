"""
KAIROS Cron 定时任务调度器
"""

import time
import json
import asyncio
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Callable
from datetime import datetime, timedelta


@dataclass
class CronTask:
    id: str
    prompt: str
    cron: str
    created_at: float
    recurring: bool = True
    permanent: bool = False
    max_age_ms: int = 0


class CronScheduler:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.tasks_file = project_root / ".claude" / "scheduled_tasks.json"
        self.tasks: List[CronTask] = []
        self.running = False
        self.check_interval = 1
        self.on_fire: Optional[Callable[[str], None]] = None

    def _load_tasks(self) -> List[CronTask]:
        if not self.tasks_file.exists():
            return []
        try:
            with open(self.tasks_file, 'r') as f:
                data = json.load(f)
                return [CronTask(**task) for task in data.get('tasks', [])]
        except Exception:
            return []

    def _save_tasks(self):
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tasks_file, 'w') as f:
            json.dump({'tasks': [asdict(t) for t in self.tasks]}, f, indent=2)

    def add_task(self, prompt: str, cron: str, recurring: bool = True) -> str:
        task_id = f"cron_{int(time.time())}"
        task = CronTask(id=task_id, prompt=prompt, cron=cron, created_at=time.time(), recurring=recurring)
        self.tasks.append(task)
        self._save_tasks()
        return task_id

    def remove_task(self, task_id: str):
        self.tasks = [t for t in self.tasks if t.id != task_id]
        self._save_tasks()

    def _parse_cron(self, cron: str) -> Optional[datetime]:
        try:
            parts = cron.split()
            if len(parts) != 5:
                return None
            minute, hour, day, month, weekday = parts
            if day == "*" and month == "*" and weekday == "*":
                next_run = datetime.now().replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
                if next_run <= datetime.now():
                    next_run += timedelta(days=1)
                return next_run
            return None
        except Exception:
            return None

    async def start(self, on_fire: Callable[[str], None]):
        self.on_fire = on_fire
        self.running = True
        self.tasks = self._load_tasks()
        print(f"[KAIROS] Cron scheduler started with {len(self.tasks)} tasks")
        while self.running:
            now = datetime.now()
            for task in self.tasks:
                next_run = self._parse_cron(task.cron)
                if next_run and now >= next_run:
                    print(f"[KAIROS] Cron task fired: {task.prompt[:50]}...")
                    if self.on_fire:
                        self.on_fire(task.prompt)
                    if not task.recurring:
                        self.remove_task(task.id)
            await asyncio.sleep(self.check_interval)

    def stop(self):
        self.running = False