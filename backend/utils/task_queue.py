"""Background task queue and runtime scheduler.

参考来源：
- OpenHuman：周期同步外部数据源。
- Hermes：周期性反思最近轨迹并提炼技能。
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


def schedule(coro: Awaitable) -> asyncio.Task:
    return asyncio.create_task(coro)


@dataclass
class ScheduledJob:
    id: str
    interval_seconds: int
    func: Callable[[], Any]
    last_run_at: float | None = None
    next_run_at: float | None = None
    status: str = "idle"
    result: Any = None
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


class RuntimeScheduler:
    """Small interval scheduler used by sync and reflection loops."""

    def __init__(self, logger: Any):
        self.logger = logger
        self.jobs: dict[str, ScheduledJob] = {}
        self.running = False

    def add_interval_job(self, job_id: str, interval_seconds: int, func: Callable[[], Any]) -> ScheduledJob:
        job = ScheduledJob(job_id, interval_seconds, func, next_run_at=time.time() + interval_seconds)
        self.jobs[job_id] = job
        if self.running:
            self._start_job(job)
        return job

    def start(self) -> None:
        self.running = True
        for job in self.jobs.values():
            self._start_job(job)

    async def run_now(self, job_id: str) -> dict[str, Any]:
        job = self.jobs[job_id]
        await self._run_job(job)
        return self.describe_job(job)

    def stop(self) -> None:
        self.running = False
        for job in self.jobs.values():
            if job.task and not job.task.done():
                job.task.cancel()

    def describe(self) -> dict[str, Any]:
        return {job_id: self.describe_job(job) for job_id, job in self.jobs.items()}

    def describe_job(self, job: ScheduledJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "interval_seconds": job.interval_seconds,
            "last_run_at": job.last_run_at,
            "next_run_at": job.next_run_at,
            "status": job.status,
            "result": job.result,
            "error": job.error,
        }

    def _start_job(self, job: ScheduledJob) -> None:
        if job.task and not job.task.done():
            return
        try:
            loop = asyncio.get_running_loop()
            job.task = loop.create_task(self._loop(job))
        except RuntimeError:
            thread = threading.Thread(target=lambda: asyncio.run(self._loop(job)), daemon=True)
            thread.start()

    async def _loop(self, job: ScheduledJob) -> None:
        while self.running:
            now = time.time()
            wait = max(0.0, (job.next_run_at or now) - now)
            await asyncio.sleep(wait)
            if self.running:
                await self._run_job(job)

    async def _run_job(self, job: ScheduledJob) -> None:
        job.status = "running"
        job.error = None
        try:
            result = job.func()
            if inspect.isawaitable(result):
                result = await result
            job.result = result
            job.status = "ok"
        except Exception as exc:
            self.logger.exception("scheduled job failed: %s", job.id)
            job.error = str(exc)
            job.status = "failed"
        finally:
            job.last_run_at = time.time()
            job.next_run_at = job.last_run_at + job.interval_seconds
