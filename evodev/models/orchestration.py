"""Specialist delegation and multi-agent orchestration data models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class SpecialistRole(str, Enum):
    """Specialized roles for multi-agent delegation."""

    IMPLEMENTER = "implementer"
    CODE_REVIEWER = "code_reviewer"
    TEST_ENGINEER = "test_engineer"
    DEBUGGING_SPECIALIST = "debugging_specialist"
    DOCUMENTATION_SPECIALIST = "documentation_specialist"
    SECURITY_REVIEWER = "security_reviewer"


class TaskStatus(str, Enum):
    """Execution status for decomposed orchestration tasks."""

    PENDING = "pending"
    WAITING_APPROVAL = "waiting_approval"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"


class DelegationStep(BaseModel):
    """A distinct task step assigned to a specific specialist role."""

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: SpecialistRole
    assigned_agent_id: Optional[str] = Field(default=None, description="Connector ID of agent executing this step")
    task_description: str = Field(description="Explicit goal and constraints for the specialist")
    requires_approval: bool = Field(default=False, description="Whether human confirmation is required before run")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Explicit structured input context")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="Structured outputs produced by agent")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    error: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Captured test/compiler/review evidence")


class OrchestrationTask(BaseModel):
    """A composite task decomposed across multiple specialist agent roles."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(description="High-level engineering mission")
    project_id: str
    steps: List[DelegationStep] = Field(default_factory=list)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
