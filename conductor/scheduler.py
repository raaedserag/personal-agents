"""
Scheduler — Cron-based job runner for the conductor.

Reads schedule config and triggers agent actions on a cron schedule.
Stores the last generated report for each schedule so the dashboard
can retrieve it without triggering a new generation.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from croniter import croniter

logger = logging.getLogger("conductor.scheduler")


class ScheduledJob:
    """A single scheduled job definition."""

    def __init__(self, name: str, cron_expr: str, action: str, deliver_to: list[str]):
        self.name = name
        self.cron_expr = cron_expr
        self.action = action
        self.deliver_to = deliver_to
        self.last_run: datetime | None = None
        self.last_result: Any = None
        self.cron = croniter(cron_expr, datetime.now(timezone.utc))

    def next_run(self) -> datetime:
        return self.cron.get_next(datetime)

    def should_run(self, now: datetime) -> bool:
        """Check if this job should run at the given time (minute-level precision)."""
        check_cron = croniter(self.cron_expr, now.replace(second=0, microsecond=0) - __import__("datetime").timedelta(seconds=1))
        next_time = check_cron.get_next(datetime)
        return next_time.replace(second=0, microsecond=0) == now.replace(second=0, microsecond=0)


class Scheduler:
    """Runs scheduled jobs in a background thread.

    The scheduler checks every 60 seconds whether any jobs need to run.
    When a job triggers, it calls the registered action callback.
    """

    def __init__(self):
        self.jobs: dict[str, ScheduledJob] = {}
        self.action_handlers: dict[str, Callable] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._reports: dict[str, Any] = {}  # latest report per schedule name

    def register_schedule(self, name: str, cron_expr: str, action: str, deliver_to: list[str]) -> None:
        """Register a scheduled job from config."""
        self.jobs[name] = ScheduledJob(name, cron_expr, action, deliver_to)
        logger.info(f"Registered schedule: {name} ({cron_expr}) -> {action}")

    def register_action(self, action_name: str, handler: Callable) -> None:
        """Register an action handler that a schedule can call."""
        self.action_handlers[action_name] = handler

    def start(self) -> None:
        """Start the scheduler background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped")

    def get_latest_report(self, schedule_name: str) -> Any | None:
        """Get the most recent report for a schedule."""
        return self._reports.get(schedule_name)

    def get_all_latest_reports(self) -> dict[str, Any]:
        """Get all latest reports."""
        return dict(self._reports)

    def get_status(self) -> dict:
        """Get scheduler status for health checks."""
        return {
            "running": self._running,
            "jobs": {
                name: {
                    "cron": job.cron_expr,
                    "action": job.action,
                    "last_run": job.last_run.isoformat() if job.last_run else None,
                    "has_report": name in self._reports,
                }
                for name, job in self.jobs.items()
            },
        }

    def trigger_now(self, schedule_name: str) -> Any:
        """Manually trigger a scheduled job immediately."""
        job = self.jobs.get(schedule_name)
        if not job:
            return {"error": f"Schedule '{schedule_name}' not found"}
        return self._execute_job(job)

    def _run_loop(self) -> None:
        """Main scheduler loop — checks every 60s."""
        import time

        while self._running:
            now = datetime.now(timezone.utc)
            for name, job in self.jobs.items():
                if job.should_run(now):
                    logger.info(f"Triggering scheduled job: {name}")
                    try:
                        self._execute_job(job)
                    except Exception as e:
                        logger.error(f"Scheduled job {name} failed: {e}")
            time.sleep(60)

    def _execute_job(self, job: ScheduledJob) -> Any:
        """Execute a scheduled job."""
        handler = self.action_handlers.get(job.action)
        if not handler:
            logger.warning(f"No handler for action: {job.action}")
            return {"error": f"No handler for action '{job.action}'"}

        result = handler()
        job.last_run = datetime.now(timezone.utc)
        job.last_result = result
        self._reports[job.name] = {
            "generated_at": job.last_run.isoformat(),
            "data": result,
        }
        logger.info(f"Job {job.name} completed successfully")
        return result
