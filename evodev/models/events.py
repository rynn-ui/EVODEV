"""Normalized event models for coding agent interactions."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Supported lifecycle event types across coding agents."""

    TASK_STARTED = "task_started"
    TOOL_INVOKED = "tool_invoked"
    TOOL_RESULT = "tool_result"
    ERROR_OBSERVED = "error_observed"
    TEST_EXECUTED = "test_executed"
    VERIFICATION_RECORDED = "verification_recorded"
    TASK_FINISHED = "task_finished"
    USER_FEEDBACK = "user_feedback"


class NormalizedEvent(BaseModel):
    """Base event model with common metadata across all integrations."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(description="Unique session identifier for the agent conversation")
    task_id: str = Field(description="Task identifier within the session")
    project_id: str = Field(default="global", description="Project or repository identifier")
    event_type: EventType = Field(description="Type of normalized event")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary engine metadata")


class TaskStartedEvent(NormalizedEvent):
    """Fired when an agent begins a software development task."""

    event_type: EventType = EventType.TASK_STARTED
    task_description: str
    domain: Optional[str] = "general"
    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    git_branch: Optional[str] = None
    git_commit: Optional[str] = None


class ToolInvokedEvent(NormalizedEvent):
    """Fired before or when an agent calls an external tool."""

    event_type: EventType = EventType.TOOL_INVOKED
    tool_name: str
    call_id: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolResultEvent(NormalizedEvent):
    """Fired after an agent tool execution finishes."""

    event_type: EventType = EventType.TOOL_RESULT
    tool_name: str
    call_id: Optional[str] = None
    exit_code: int = 0
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class ErrorObservedEvent(NormalizedEvent):
    """Fired when a compiler, linter, runtime, or tool error occurs."""

    event_type: EventType = EventType.ERROR_OBSERVED
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None


class TestExecutedEvent(NormalizedEvent):
    """Fired when a test command runs."""

    __test__ = False
    event_type: EventType = EventType.TEST_EXECUTED
    test_command: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_seconds: Optional[float] = None
    failures_summary: Optional[str] = None


class VerificationRecordedEvent(NormalizedEvent):
    """Fired when explicit verification (build, test, lint, human) is performed."""

    event_type: EventType = EventType.VERIFICATION_RECORDED
    verification_type: str  # e.g., "test", "build", "lint", "human_review"
    passed: bool
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    details: Optional[str] = None


class TaskFinishedEvent(NormalizedEvent):
    """Fired when the task reaches a terminal state."""

    event_type: EventType = EventType.TASK_FINISHED
    outcome: str  # "success", "failure", "cancelled", "partial"
    duration_ms: Optional[int] = None
    changed_files: List[str] = Field(default_factory=list)
    summary: Optional[str] = None


class UserFeedbackEvent(NormalizedEvent):
    """Fired when user gives explicit feedback or correction."""

    event_type: EventType = EventType.USER_FEEDBACK
    rating: str  # "positive", "negative", "neutral"
    feedback_text: Optional[str] = None
    correction_applied: bool = False
