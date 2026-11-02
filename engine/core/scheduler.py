"""
Schedule & Cron Manager (`schedule` tool).
Supports one-shot timers (`DurationSeconds`) and recurring cron schedules (`CronExpression`)
with Reactive Wakeup notifications back to the conversation.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ScheduledJob:
    job_id: str
    conversation_id: str
    prompt: str
    duration_seconds: Optional[int]
    cron_expression: Optional[str]
    max_iterations: Optional[int]
    is_daemon: bool
    created_at: str
    status: str = "active"  # "active" | "completed" | "cancelled"
    iterations_run: int = 0
    task: Optional[asyncio.Task] = None


class SchedulerManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, ScheduledJob] = {}
        self._wakeup_cb: Optional[Callable[[str, str, str], Any]] = None

    def set_wakeup_handler(self, cb: Callable[[str, str, str], Any]) -> None:
        self._wakeup_cb = cb

    async def schedule(
        self,
        conversation_id: str,
        prompt: str,
        duration_seconds: Optional[int] = None,
        cron_expression: Optional[str] = None,
        max_iterations: Optional[int] = None,
        is_daemon: bool = False,
    ) -> str:
        if not duration_seconds and not cron_expression:
            return "Error: Provide either DurationSeconds or CronExpression."

        job_id = f"sched_{uuid.uuid4().hex[:8]}"
        job = ScheduledJob(
            job_id=job_id,
            conversation_id=conversation_id,
            prompt=prompt,
            duration_seconds=duration_seconds,
            cron_expression=cron_expression,
            max_iterations=max_iterations,
            is_daemon=is_daemon,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._jobs[job_id] = job

        if duration_seconds:
            job.task = asyncio.create_task(self._run_timer(job))
            return f"Scheduled one-shot timer `{job_id}` for {duration_seconds}s. End your turn to wait for notification."
        else:
            job.task = asyncio.create_task(self._run_cron(job))
            return f"Scheduled recurring cron job `{job_id}` (`{cron_expression}`). End your turn to wait for triggers."

    async def _run_timer(self, job: ScheduledJob) -> None:
        try:
            await asyncio.sleep(max(1, job.duration_seconds or 1))
            if job.status != "active":
                return
            job.iterations_run += 1
            job.status = "completed"
            if self._wakeup_cb:
                res = self._wakeup_cb(job.conversation_id, job.job_id, job.prompt)
                if asyncio.iscoroutine(res):
                    await res
        except asyncio.CancelledError:
            job.status = "cancelled"

    async def _run_cron(self, job: ScheduledJob) -> None:
        from croniter import croniter

        try:
            while job.status == "active":
                now = datetime.now(timezone.utc)
                itr = croniter(job.cron_expression or "*/5 * * * *", now)
                next_dt = itr.get_next(datetime)
                delay = max(1.0, (next_dt - now).total_seconds())
                await asyncio.sleep(delay)
                if job.status != "active":
                    break
                job.iterations_run += 1
                if self._wakeup_cb:
                    res = self._wakeup_cb(job.conversation_id, job.job_id, job.prompt)
                    if asyncio.iscoroutine(res):
                        await res
                if job.max_iterations and job.iterations_run >= job.max_iterations:
                    job.status = "completed"
                    break
        except asyncio.CancelledError:
            job.status = "cancelled"
        except Exception:
            job.status = "cancelled"

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.status = "cancelled"
        if job.task:
            job.task.cancel()
        return True

    def list_jobs(self) -> List[Dict[str, Any]]:
        return [
            {
                "job_id": j.job_id,
                "conversation_id": j.conversation_id,
                "prompt": j.prompt,
                "duration_seconds": j.duration_seconds,
                "cron_expression": j.cron_expression,
                "status": j.status,
                "iterations_run": j.iterations_run,
                "created_at": j.created_at,
            }
            for j in self._jobs.values()
        ]


scheduler_manager = SchedulerManager()
