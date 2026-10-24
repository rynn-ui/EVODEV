"""Scheduled job models for background automation and recurring maintenance."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class JobType(str, Enum):
    """Supported background maintenance and automation task types."""

    BENCHMARK_RUN = "benchmark_run"
    STALE_CLEANUP = "stale_cleanup"
    HEALTH_CHECK = "health_check"
    DEPENDENCY_AUDIT = "dependency_audit"
    REPORT = "report"
    MAINTENANCE = "maintenance"


class JobStatus(str, Enum):
    """Current state of a scheduled job execution."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledJob(BaseModel):
    """Persistent configuration and state of a background scheduled job."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(description="Unique job name")
    job_type: JobType
    schedule_expr: str = Field(description="Interval expression e.g. 'every:1h', 'every:24h', 'daily'")
    next_run_at: datetime = Field(description="Scheduled time for next execution")
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict, description="Job parameters")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
