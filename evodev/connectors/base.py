"""Abstract base connector interface for AI coding agent integrations."""

from abc import abstractmethod
from typing import Any, Dict, List, Optional

from evodev.connectors.contract import (
    AgentConnector,
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorIdentity,
    ContextRequest,
    ContextResponse,
    EventIngestResponse,
    HealthStatus,
    OutcomeReport,
    OutcomeResponse,
    RetrievedLessonSnippet,
    UnsupportedCapabilityError,
)
from evodev.models.events import NormalizedEvent


class BaseAgentConnector(AgentConnector):
    """Generic interface for bridging external coding agents into EvoDev.

    Maintains 100% backwards compatibility with legacy `BaseAgentConnector` methods
    while implementing the unified EvoDev 2.0 `AgentConnector` contract.
    """

    # --- Legacy interface methods ---

    @abstractmethod
    def get_name(self) -> str:
        """Return the connector display identifier."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the target host environment or agent binary is installed and reachable."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health and configuration state."""
        pass

    def start(self) -> None:
        """Initialize and activate the connector."""
        pass

    def stop(self) -> None:
        """Gracefully terminate connector background processes."""
        pass

    def assemble_context(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
    ) -> str:
        """Retrieve relevant experience and format into an agent-ready advisory snippet."""
        req = ContextRequest(
            task_description=task_description,
            project_id=project_id,
            domain=domain,
            technologies=technologies or [],
        )
        resp = self.get_context(req)
        return resp.advisory_markdown

    # --- Unified AgentConnector Contract Implementation ---

    def get_identity(self) -> ConnectorIdentity:
        name = self.get_name()
        adapter_id = name.lower().replace(" ", "_").replace("/", "_")
        return ConnectorIdentity(
            adapter_id=adapter_id,
            agent_name=name,
            agent_version=self.get_status().get("version"),
            adapter_version="2.0.0",
            description=f"Adapter for {name}",
        )

    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize adapter; calls legacy start() by default."""
        self.start()

    def health_check(self) -> ConnectorHealth:
        """Return standard health check based on is_available and get_status."""
        avail = self.is_available()
        status_info = self.get_status()
        return ConnectorHealth(
            status=HealthStatus.HEALTHY if avail else HealthStatus.OFFLINE,
            is_available=avail,
            details=f"{self.get_name()} is {'available' if avail else 'unavailable'}",
            diagnostics=status_info,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        """Return standard declared capabilities."""
        return ConnectorCapabilities(
            can_retrieve_context=True,
            can_ingest_events=True,
            can_report_outcomes=True,
            can_verify=False,
        )

    def get_context(self, request: ContextRequest) -> ContextResponse:
        """Retrieve context via assemble_context or override."""
        advisory = self.assemble_context(
            task_description=request.task_description,
            project_id=request.project_id,
            domain=request.domain,
            technologies=request.technologies,
        )
        return ContextResponse(
            correlation_id=request.correlation_id,
            profile_name="Default",
            advisory_markdown=advisory,
            matched_count=1 if advisory else 0,
            lessons=[],
        )

    def ingest_event(self, event: NormalizedEvent | Dict[str, Any]) -> EventIngestResponse:
        """Default event ingest stub; subclasses or manager override."""
        raise UnsupportedCapabilityError(self.get_name(), "ingest_event")

    def report_outcome(self, outcome: OutcomeReport) -> OutcomeResponse:
        """Default outcome reporting stub; subclasses or manager override."""
        raise UnsupportedCapabilityError(self.get_name(), "report_outcome")

    def shutdown(self) -> None:
        """Shutdown adapter; calls legacy stop() by default."""
        self.stop()
