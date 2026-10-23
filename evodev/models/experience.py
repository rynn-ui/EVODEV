"""Experience and lesson data models representing accumulated software knowledge."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class KnowledgeScope(str, Enum):
    """Hierarchical scope defining the applicability of knowledge."""

    GLOBAL = "global"  # Universal software engineering rules
    DOMAIN = "domain"  # Domain-specific rules (e.g. mobile, ML, web security)
    TECHNOLOGY = "technology"  # Framework/language specific (e.g. Kotlin, React, PyTorch)
    PREFERENCES = "preferences"  # User explicit style guidelines
    PROJECT = "project"  # Strictly repository-internal knowledge
    SESSION = "session"  # Transient session-bound notes


class EpistemicType(str, Enum):
    """Distinction between facts, user preferences, observations, and inferred rules."""

    VERIFIED_FACT = "verified_fact"  # Deterministic fact (e.g., compiler flag deprecation)
    USER_PREFERENCE = "user_preference"  # Explicit user instruction
    OBSERVED_OUTCOME = "observed_outcome"  # Empirically measured event
    INFERRED_LESSON = "inferred_lesson"  # Inductive strategy recommendation


class StrategyOutcome(str, Enum):
    """Execution outcome status for a strategy."""

    SUCCESS = "success"
    FAILURE = "failure"
    REGRESSION = "regression"
    PARTIAL = "partial"


class VerificationEvidence(BaseModel):
    """Concrete, verifiable evidence establishing task success or failure."""

    verification_type: str = "test"  # "test", "build", "lint", "human"
    passed: bool = True
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    compiler_exit_code: Optional[int] = None
    linter_clean: Optional[bool] = None
    human_confirmed: bool = False
    evidence_snippet: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Provenance(BaseModel):
    """Historical lineage and verification audit trail for an accumulated lesson."""

    origin_task_ids: List[str] = Field(default_factory=list)
    origin_project_ids: List[str] = Field(default_factory=list)
    first_observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verification_count: int = 1
    failure_count: int = 0
    regression_count: int = 0


class Lesson(BaseModel):
    """A distilled, reusable software engineering recommendation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile_id: str = Field(default="default", description="Associated experience profile")
    title: str = Field(description="Short human-readable summary of the lesson")
    trigger_pattern: str = Field(
        description="Search pattern or semantic keywords for problem matching"
    )
    context_conditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Prerequisites: domain, languages, frameworks, version constraints",
    )
    recommended_strategy: str = Field(
        description="Prescribed actionable strategy for the coding agent"
    )
    anti_patterns: List[str] = Field(
        default_factory=list,
        description="Approaches that were proven to fail or cause regressions",
    )
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    epistemic_type: EpistemicType = Field(default=EpistemicType.INFERRED_LESSON)
    scope: KnowledgeScope = Field(default=KnowledgeScope.DOMAIN)
    provenance: Provenance = Field(default_factory=Provenance)
    evidence: List[VerificationEvidence] = Field(default_factory=list)
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StrategyRecord(BaseModel):
    """Statistical tracking of a named strategy's historical performance."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile_id: str = Field(default="default")
    name: str = Field(description="Unique identifier for the strategy")
    category: str = Field(default="general", description="Category: debug, refactor, config, build")
    attempts_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    regression_count: int = 0
    bayesian_score: float = Field(default=0.5, ge=0.0, le=1.0)
    avg_duration_seconds: float = 0.0
    last_attempted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def update_score(self) -> float:
        """Calculate Bayesian expected success using Laplace smoothing with regression penalty."""
        total = self.success_count + self.failure_count + self.regression_count
        if total == 0:
            self.bayesian_score = 0.5
            return self.bayesian_score

        # Laplace smoothing: (successes + 1) / (total + 2)
        base_rate = (self.success_count + 1.0) / (total + 2.0)
        # Regression penalty: heavy penalty if strategy causes downstream breaks
        penalty = (self.regression_count * 0.25) / (total + 1.0)
        self.bayesian_score = max(0.01, min(0.99, base_rate - penalty))
        return self.bayesian_score


class ExperienceRecord(BaseModel):
    """Comprehensive historical record of a single completed development task."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile_id: str = Field(default="default")
    session_id: str
    task_id: str
    project_id: str
    domain: str = "general"
    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    environment_info: Dict[str, str] = Field(default_factory=dict)
    initial_problem: str
    strategies_attempted: List[str] = Field(default_factory=list)
    tool_invocations_summary: List[Dict[str, Any]] = Field(default_factory=list)
    errors_observed: List[str] = Field(default_factory=list)
    file_changes: List[str] = Field(default_factory=list)
    verification: Optional[VerificationEvidence] = None
    outcome: str = "success"  # "success", "failure", "partial", "cancelled"
    user_feedback: Optional[str] = None
    extracted_lesson_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
