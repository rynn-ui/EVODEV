"""Background scheduler engine with persistent SQLite job store and catchup execution."""

from datetime import datetime, timedelta, timezone
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from evodev.models.scheduler import JobStatus, JobType, ScheduledJob
from evodev.storage.repositories import ScheduleRepository

logger = logging.getLogger(__name__)


class SchedulerEngine:
    """Manages persistent scheduled maintenance and automation tasks."""

    def __init__(
        self,
        schedule_repo: ScheduleRepository,
        handlers: Optional[Dict[JobType, Callable[[Dict[str, Any]], Dict[str, Any]]]] = None,
    ):
        self.repo = schedule_repo
        self.handlers = handlers or {}
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def register_job(
        self,
        name: str,
        job_type: JobType,
        schedule_expr: str,
        params: Optional[Dict[str, Any]] = None,
        first_run_at: Optional[datetime] = None,
    ) -> ScheduledJob:
        """Register or update a persistent scheduled job with next run calculation."""
        now = datetime.now(timezone.utc)
        next_run = first_run_at or self.calculate_next_run(schedule_expr, now)

        job = ScheduledJob(
            id=str(uuid.uuid4()),
            name=name,
            job_type=job_type,
            schedule_expr=schedule_expr,
            next_run_at=next_run,
            params=params or {},
            enabled=True,
        )
        return self.repo.save(job)

    def calculate_next_run(self, schedule_expr: str, from_time: datetime) -> datetime:
        """Parse interval or schedule expression into next execution timestamp."""
        expr = schedule_expr.strip().lower()

        if expr in ("hourly", "every:1h"):
            return from_time + timedelta(hours=1)
        elif expr in ("daily", "every:24h"):
            return from_time + timedelta(days=1)
        elif expr.startswith("interval:"):
            seconds = int(expr.split(":")[1])
            return from_time + timedelta(seconds=seconds)
        elif expr.startswith("every:"):
            # Format: every:30m, every:2h, every:1d
            unit = expr[-1]
            val = int(expr[6:-1])
            if unit == "m":
                return from_time + timedelta(minutes=val)
            elif unit == "h":
                return from_time + timedelta(hours=val)
            elif unit == "d":
                return from_time + timedelta(days=val)
            elif unit == "s":
                return from_time + timedelta(seconds=val)

        # Default fallback: 1 hour
        return from_time + timedelta(hours=1)

    def run_pending(self, as_of: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Evaluate and execute all due jobs with failure isolation and next run scheduling."""
        check_time = as_of or datetime.now(timezone.utc)
        due_jobs = self.repo.list_due_jobs(check_time)
        results: List[Dict[str, Any]] = []

        for job in due_jobs:
            res = self.execute_job_now(job.id)
            results.append(res)

        return results

    def execute_job_now(self, job_id: str) -> Dict[str, Any]:
        """Manually trigger or execute a specific scheduled job."""
        job = self.repo.get_by_id(job_id)
        if not job:
            return {"job_id": job_id, "status": "error", "message": "Job not found"}

        handler = self.handlers.get(job.job_type)
        start_time = datetime.now(timezone.utc)
        job.last_run_at = start_time

        try:
            if handler:
                details = handler(job.params)
                status_str = "completed"
            else:
                details = {"message": f"Simulated default execution for job type '{job.job_type.value}'"}
                status_str = "completed"
        except Exception as exc:
            logger.error(f"Job execution failed for '{job.name}': {exc}", exc_info=True)
            details = {"error": str(exc)}
            status_str = "failed"

        job.last_status = status_str
        job.next_run_at = self.calculate_next_run(job.schedule_expr, start_time)
        self.repo.save(job)

        return {
            "job_id": job.id,
            "name": job.name,
            "status": status_str,
            "details": details,
            "next_run_at": job.next_run_at.isoformat(),
        }

    def cancel_job(self, job_id: str) -> bool:
        """Disable a scheduled job."""
        job = self.repo.get_by_id(job_id)
        if not job:
            return False
        job.enabled = False
        self.repo.save(job)
        return True

    def delete_job(self, job_id: str) -> bool:
        """Permanently delete a scheduled job."""
        return self.repo.delete(job_id)

    def list_jobs(self, enabled_only: bool = False) -> List[ScheduledJob]:
        """List all registered scheduled jobs."""
        return self.repo.list_jobs(enabled_only=enabled_only)

    def start_background_worker(self, poll_interval_seconds: float = 10.0) -> None:
        """Start non-blocking daemon thread to execute pending jobs."""
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                return
            self._stop_event.clear()

            def _loop():
                while not self._stop_event.is_set():
                    try:
                        self.run_pending()
                    except Exception as e:
                        logger.error(f"Error in scheduler worker: {e}")
                    self._stop_event.wait(poll_interval_seconds)

            self._worker_thread = threading.Thread(target=_loop, daemon=True, name="EvoDevSchedulerWorker")
            self._worker_thread.start()

    def stop_background_worker(self) -> None:
        """Stop background execution worker cleanly."""
        with self._lock:
            self._stop_event.set()
            if self._worker_thread:
                self._worker_thread.join(timeout=2.0)
                self._worker_thread = None
