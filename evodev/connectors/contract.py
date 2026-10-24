"""Common connector contract, protocol, and typed data models for multi-agent integrations."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from evodev.models.events import NormalizedEvent
from evodev.models.experience import KnowledgeScope, VerificationEvidence


class UnsupportedCapabilityError(Exception):
    """Raised when an operation is requested that an adapter does not support."""

    def __init__(self, adapter_id: str, capability: str, message: Optional[str] = None):
        msg = message or f"Adapter '{adapter_id}' does not support capability: '{capability}'"
        super().__init__(msg)
        self.adapter_id = adapter_id
        self.capability = capability


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class ConnectorIdentity(BaseModel):
    """Stable identity descriptor for an agent adapter."""

    adapter_id: str = Field(..., description="Unique stable ID, e.g. 'opencode', 'gemini', 'generic'")
    agent_name: str = Field(..., description="Display name of the target AI coding agent")
    agent_version: Optional[str] = Field(None, description="Detected version of target agent")
    adapter_version: str = Field(default="2.0.0", description="Version of the adapter implementation")
    description: str = Field(default="", description="Summary of the connector integration")


class ConnectorCapabilities(BaseModel):
    """Declared capabilities supported by this adapter."""

    can_retrieve_context: bool = Field(default=True, description="Can query verified lessons for prompts")
    can_ingest_events: bool = Field(default=True, description="Can capture observable coding events")
    can_report_outcomes: bool = Field(default=True, description="Can report task outcomes and Bayesian signals")
    can_verify: bool = Field(default=False, description="Can capture test/lint verification outcomes")
    supported_event_types: List[str] = Field(
        default_factory=lambda: ["task_started", "tool_invoked", "tool_result", "task_finished"]
    )
    supported_scopes: List[str] = Field(
        default_factory=lambda: ["global", "domain", "technology", "project", "preferences"]
    )
    mcp_compliant: bool = Field(default=False, description="Exposes or consumes Model Context Protocol")
    lifecycle_hooks_supported: bool = Field(default=False, description="Uses filesystem/process lifecycle hooks")
    custom_features: List[str] = Field(default_factory=list, description="Custom agent-specific capabilities")

    @property
    def supports_context_retrieval(self) -> bool:
        return self.can_retrieve_context

    @property
    def supports_outcome_reporting(self) -> bool:
        return self.can_report_outcomes

    @property
    def supports_event_ingestion(self) -> bool:
        return self.can_ingest_events


class ConnectorHealth(BaseModel):
    """Diagnostic health state for a connector."""

    status: HealthStatus = Field(default=HealthStatus.HEALTHY)
    is_available: bool = Field(default=True, description="Whether agent host environment is reachable")
    details: str = Field(default="", description="Human-readable status or error description")
    latency_ms: Optional[float] = Field(None, description="Roundtrip check latency in ms")
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    diagnostics: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY or self.is_available

    @property
    def message(self) -> str:
        return self.details


class ContextRequest(BaseModel):
    """Typed request for retrieving contextual lessons for an agent task."""

    task_description: str = Field(..., description="Description of the user problem or coding task")
    project_id: str = Field(default="default-project", description="Target project/repository identifier")
    domain: str = Field(default="general", description="Target technical domain (mobile, web, backend, ml, etc.)")
    technologies: List[str] = Field(default_factory=list, description="Target languages and frameworks")
    profile_id: Optional[str] = Field(None, description="Optional explicit profile ID; uses active profile if None")
    session_id: Optional[str] = Field(None, description="Agent session identifier")
    task_id: Optional[str] = Field(None, description="Agent subtask identifier")
    min_score: float = Field(default=0.35, description="Relevance cutoff threshold")
    limit: int = Field(default=5, description="Maximum lessons to retrieve")
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class RetrievedLessonSnippet(BaseModel):
    """Summary of a verified lesson retrieved for context."""

    lesson_id: str
    title: str
    score: float
    scope: KnowledgeScope
    recommended_strategy: str
    anti_patterns: List[str] = Field(default_factory=list)
    confidence: float
    origin_project_ids: List[str] = Field(default_factory=list)


class ContextResponse(BaseModel):
    """Typed response delivering formatted advisory and structured lessons."""

    correlation_id: str
    profile_name: str
    advisory_markdown: str
    matched_count: int
    lessons: List[RetrievedLessonSnippet] = Field(default_factory=list)


class OutcomeReport(BaseModel):
    """Report of a strategy outcome or task verification from an agent."""

    strategy_name: str = Field(default="", description="Identified strategy or tool technique applied")
    applied_strategies: List[str] = Field(default_factory=list, description="Multiple strategies applied if batch")
    outcome: Any = Field(..., description="success, failure, or regression")
    domain: str = Field(default="general")
    project_id: str = Field(default="default-project")
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    profile_id: Optional[str] = None
    verification: Optional[VerificationEvidence] = None
    notes: Optional[str] = None
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class OutcomeResponse(BaseModel):
    """Response returned after recording an outcome."""

    correlation_id: str
    success: bool = True
    strategy_name: str = ""
    bayesian_score: float = 0.5
    attempts_count: int = 1
    success_count: int = 1
    regression_count: int = 0
    message: str = ""
    acknowledged: bool = True


class EventIngestResponse(BaseModel):
    """Response returned after ingesting a normalized or raw agent event."""

    status: str = "ok"
    event_id: str
    event_type: str
    duplicate: bool = False
    message: Optional[str] = None


class AgentConnector(ABC):
    """Unified contract for all EvoDev AI coding agent adapters."""

    @abstractmethod
    def get_identity(self) -> ConnectorIdentity:
        """Return stable identity information for this connector."""
        pass

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize adapter with configuration settings."""
        pass

    @abstractmethod
    def health_check(self) -> ConnectorHealth:
        """Execute a diagnostic health check."""
        pass

    @abstractmethod
    def get_capabilities(self) -> ConnectorCapabilities:
        """Return the declared capabilities of this adapter."""
        pass

    @abstractmethod
    def get_context(self, request: ContextRequest) -> ContextResponse:
        """Retrieve relevant experience and return advisory snippet."""
        pass

    @abstractmethod
    def ingest_event(self, event: NormalizedEvent | Dict[str, Any]) -> EventIngestResponse:
        """Ingest an observable coding event into the shared event pipeline."""
        pass

    @abstractmethod
    def report_outcome(self, outcome: OutcomeReport) -> OutcomeResponse:
        """Report strategy outcome or verification result to the learning engine."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Gracefully release any adapter resources or background workers."""
        pass
