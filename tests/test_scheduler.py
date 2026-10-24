"""Tests for persistent background scheduler, schedule expressions, and failure isolation."""

from datetime import datetime, timedelta, timezone
import pytest

from evodev.config import EvoDevConfig
from evodev.models.scheduler import JobType
from evodev.scheduler.engine import SchedulerEngine
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import ScheduleRepository


@pytest.fixture
def scheduler_setup(tmp_path):
    config = EvoDevConfig(data_dir=tmp_path / "data")
    config.ensure_directories()
    db = get_db(config)
    MigrationManager(db).run_migrations()

    sched_repo = ScheduleRepository(db)
    engine = SchedulerEngine(sched_repo)
    return engine, sched_repo


def test_schedule_expression_parsing(scheduler_setup):
    engine, _ = scheduler_setup
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Hourly
    next_hourly = engine.calculate_next_run("hourly", now)
    assert next_hourly == now + timedelta(hours=1)

    # Daily
    next_daily = engine.calculate_next_run("daily", now)
    assert next_daily == now + timedelta(days=1)

    # every:30m
    next_30m = engine.calculate_next_run("every:30m", now)
    assert next_30m == now + timedelta(minutes=30)

    # interval:3600
    next_interval = engine.calculate_next_run("interval:3600", now)
    assert next_interval == now + timedelta(seconds=3600)


def test_job_registration_and_run_pending(scheduler_setup):
    engine, sched_repo = scheduler_setup

    executed_params = []

    def sample_handler(params):
        executed_params.append(params)
        return {"result": "success", "cleaned_items": 42}

    engine.handlers[JobType.STALE_CLEANUP] = sample_handler

    # Register job due in the past
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    job = engine.register_job(
        name="Cleanup Stale Memories",
        job_type=JobType.STALE_CLEANUP,
        schedule_expr="hourly",
        params={"retention_days": 30},
        first_run_at=past_time,
    )

    assert job.id is not None
    assert job.enabled is True

    # Run pending jobs
    results = engine.run_pending()
    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["details"]["cleaned_items"] == 42
    assert executed_params[0]["retention_days"] == 30

    # Job next_run_at should now be in the future
    updated = sched_repo.get_by_id(job.id)
    assert updated.last_run_at is not None
    assert updated.next_run_at > datetime.now(timezone.utc)


def test_job_failure_isolation(scheduler_setup):
    engine, sched_repo = scheduler_setup

    def failing_handler(params):
        raise RuntimeError("Disk full simulation")

    engine.handlers[JobType.BENCHMARK_RUN] = failing_handler

    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    job = engine.register_job(
        name="Benchmark Job",
        job_type=JobType.BENCHMARK_RUN,
        schedule_expr="daily",
        first_run_at=past_time,
    )

    # Execution should not raise an unhandled exception, but record failure
    results = engine.run_pending()
    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert "Disk full simulation" in str(results[0]["details"])

    updated = sched_repo.get_by_id(job.id)
    assert updated.last_status == "failed"
    assert updated.next_run_at > datetime.now(timezone.utc)  # Continues schedule without halting
