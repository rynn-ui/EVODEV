"""Self-improving skill models distinct from individual lessons."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from evodev.models.experience import KnowledgeScope


class SkillStatus(str, Enum):
    """Lifecycle status of a self-improving skill."""

    DRAFT = "draft"  # Freshly generated or proposed, unverified
    EVALUATING = "evaluating"  # Under benchmark evaluation
    PROMOTED = "promoted"  # Validated and approved for cross-agent production use
    DEPRECATED = "deprecated"  # Replaced by higher-performing or updated version
    ACTIVE = "active"


class SkillPrerequisite(BaseModel):
    """Required tools, environment setups, or context flags for executing a skill."""

    name: str = Field(description="Prerequisite name or tool capability")
    description: str = Field(default="", description="Requirement details")
    required: bool = Field(default=True)


class ProcedureStep(BaseModel):
    """Individual actionable procedure step within a skill."""

    step_number: int = Field(ge=1)
    instruction: str = Field(description="Actionable directive for the coding agent")
    validation: Optional[str] = Field(default=None, description="Observable verification criterion for this step")


class SkillEvaluation(BaseModel):
    """Controlled benchmark trial evaluation for a specific skill version."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_version_id: str
    task_id: str
    benchmark_id: Optional[str] = None
    passed: bool = Field(description="True if all verification gates succeeded")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Test outputs, error logs, execution metrics")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SkillVersion(BaseModel):
    """An immutable, versioned implementation of a skill packaging instructions and procedure steps."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str
    version: str = Field(default="1.0.0", description="SemVer version tag")
    instructions: str = Field(description="Comprehensive system/agent instructions")
    prerequisites: List[SkillPrerequisite] = Field(default_factory=list)
    procedures: List[ProcedureStep] = Field(default_factory=list)
    validation_steps: List[str] = Field(default_factory=list)
    expected_outcomes: List[str] = Field(default_factory=list)
    evaluation_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Benchmark statistics (pass rate, regression rate, trials)",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Skill(BaseModel):
    """A self-improving, reusable procedure packaging validated developer workflows."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile_id: str = Field(default="default", description="Associated experience profile")
    name: str = Field(description="Canonical skill identifier (e.g. android-compose-migration)")
    description: str = Field(description="High-level description of when and why to activate this skill")
    category: str = Field(default="general", description="Category: refactor, build, debug, test, architecture")
    current_version: str = Field(default="1.0.0", description="Currently active promoted version tag")
    status: SkillStatus = Field(default=SkillStatus.DRAFT)
    scope: KnowledgeScope = Field(default=KnowledgeScope.DOMAIN)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    versions: List[SkillVersion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_current_version_obj(self) -> Optional[SkillVersion]:
        for v in self.versions:
            if v.version == self.current_version:
                return v
        return self.versions[-1] if self.versions else None

    @property
    def total_evaluations(self) -> int:
        cur_v = self.get_current_version_obj()
        if cur_v and cur_v.evaluation_summary:
            return cur_v.evaluation_summary.get("trials", 0)
        return self.metadata.get("total_evaluations", 0)

    @property
    def success_rate(self) -> float:
        cur_v = self.get_current_version_obj()
        if cur_v and cur_v.evaluation_summary:
            return cur_v.evaluation_summary.get("pass_rate", 0.0)
        return self.metadata.get("success_rate", 0.0)
