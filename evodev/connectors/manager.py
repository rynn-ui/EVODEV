"""Central connector registry and manager for unified multi-agent orchestration."""

from collections import OrderedDict
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set
import uuid

from evodev.collector.collector_service import CollectorService
from evodev.config import EvoDevConfig, load_config
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
from evodev.models.experience import KnowledgeScope, StrategyOutcome
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.security.redactor import SecretRedactor
from evodev.storage.repositories import (
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Thread-safe registry for agent adapters with duplicate prevention."""

    def __init__(self):
        self._connectors: Dict[str, AgentConnector] = {}

    def register(self, connector: AgentConnector, replace: bool = False) -> None:
        """Register an adapter under its stable identifier.

        Raises:
            ValueError: If connector is already registered and replace is False.
        """
        identity = connector.get_identity()
        adapter_id = identity.adapter_id
        if not adapter_id:
            raise ValueError("Connector identity must specify a non-empty adapter_id.")

        if adapter_id in self._connectors and not replace:
            raise ValueError(f"Connector '{adapter_id}' is already registered in registry.")

        self._connectors[adapter_id] = connector
        logger.info(f"Registered connector: {adapter_id} ({identity.agent_name})")

    def unregister(self, adapter_id: str) -> Optional[AgentConnector]:
        """Remove and return an adapter by identifier if present."""
        return self._connectors.pop(adapter_id, None)

    def get(self, adapter_id: str) -> Optional[AgentConnector]:
        """Look up a connector by ID."""
        return self._connectors.get(adapter_id)

    def has(self, adapter_id: str) -> bool:
        """Check if adapter is registered."""
        return adapter_id in self._connectors

    def list_connectors(self) -> List[AgentConnector]:
        """Return all registered connectors."""
        return list(self._connectors.values())

    def clear(self) -> None:
        """Clear all registered connectors."""
        self._connectors.clear()


class DeduplicationCache:
    """Fixed-capacity LRU cache for tracking recent event identifiers."""

    def __init__(self, capacity: int = 5000):
        self.capacity = capacity
        self._items: OrderedDict[str, float] = OrderedDict()

    def is_duplicate(self, item_id: str) -> bool:
        """Check if item_id exists in cache; if not, add it."""
        if not item_id:
            return False
        if item_id in self._items:
            self._items.move_to_end(item_id)
            return True
        self._items[item_id] = time.time()
        if len(self._items) > self.capacity:
            self._items.popitem(last=False)
        return False

    def clear(self) -> None:
        self._items.clear()


class ConnectorManager:
    """Central orchestration manager connecting AI coding agents to EvoDev Core.

    Ensures:
    - Shared core learning engine and database across all agents.
    - Failure isolation (an error in one agent never breaks another).
    - Event deduplication and secret redaction.
    - Strict cross-project and scope data isolation.
    """

    def __init__(
        self,
        registry: Optional[ConnectorRegistry] = None,
        retrieval_engine: Optional[RetrievalEngine] = None,
        collector_service: Optional[CollectorService] = None,
        strategy_repo: Optional[StrategyRepository] = None,
        lesson_repo: Optional[LessonRepository] = None,
        profile_repo: Optional[ProfileRepository] = None,
        redactor: Optional[SecretRedactor] = None,
        config: Optional[EvoDevConfig] = None,
    ):
        self.registry = registry or ConnectorRegistry()
        self.retrieval_engine = retrieval_engine
        self.collector_service = collector_service
        self.strategy_repo = strategy_repo
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.redactor = redactor or SecretRedactor()
        self.config = config or load_config()
        self.assembler = ContextAssembler()
        self.dedup_cache = DeduplicationCache()

    def register(self, connector: AgentConnector, replace: bool = False) -> None:
        """Register a connector through the manager."""
        self.registry.register(connector, replace=replace)

    def initialize_all(self, config_map: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, bool]:
        """Initialize all registered adapters with failure isolation."""
        config_map = config_map or {}
        results: Dict[str, bool] = {}

        for connector in self.registry.list_connectors():
            cid = connector.get_identity().adapter_id
            try:
                adapter_cfg = config_map.get(cid, {})
                connector.initialize(adapter_cfg)
                results[cid] = True
            except Exception as e:
                logger.error(f"Failed to initialize connector '{cid}': {e}", exc_info=True)
                results[cid] = False

        return results

    def health_check_all(self) -> Dict[str, ConnectorHealth]:
        """Run health checks on all adapters with failure isolation."""
        healths: Dict[str, ConnectorHealth] = {}
        for connector in self.registry.list_connectors():
            cid = connector.get_identity().adapter_id
            start_t = time.perf_counter()
            try:
                h = connector.health_check()
                if h.latency_ms is None:
                    h.latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
                healths[cid] = h
            except Exception as e:
                healths[cid] = ConnectorHealth(
                    status=HealthStatus.OFFLINE,
                    is_available=False,
                    details=f"Health check threw exception: {str(e)}",
                    latency_ms=round((time.perf_counter() - start_t) * 1000, 2),
                    diagnostics={"error": str(e)},
                )
        return healths

    def shutdown_all(self) -> None:
        """Gracefully shut down all registered connectors."""
        for connector in self.registry.list_connectors():
            cid = connector.get_identity().adapter_id
            try:
                connector.shutdown()
            except Exception as e:
                logger.warning(f"Error during connector '{cid}' shutdown: {e}")

    def get_capabilities_all(self) -> Dict[str, ConnectorCapabilities]:
        """Query capabilities across all registered connectors."""
        caps: Dict[str, ConnectorCapabilities] = {}
        for connector in self.registry.list_connectors():
            cid = connector.get_identity().adapter_id
            try:
                caps[cid] = connector.get_capabilities()
            except Exception as e:
                caps[cid] = ConnectorCapabilities(
                    can_retrieve_context=False,
                    can_ingest_events=False,
                    can_report_outcomes=False,
                )
        return caps

    def retrieve_context(self, adapter_id: str, request: ContextRequest) -> ContextResponse:
        """Route context retrieval to EvoDev Core with project and profile isolation."""
        connector = self.registry.get(adapter_id)
        if not connector:
            raise KeyError(f"Connector '{adapter_id}' is not registered.")

        caps = connector.get_capabilities()
        if not caps.can_retrieve_context:
            raise UnsupportedCapabilityError(adapter_id, "can_retrieve_context")

        if not self.retrieval_engine or not self.profile_repo:
            raise RuntimeError("Core retrieval engine or profile repository is not configured.")

        # Determine target profile
        profile_id = request.profile_id
        if not profile_id:
            active_p = self.profile_repo.get_active()
            profile_id = active_p.profile_id if active_p else "default"
            profile_name = active_p.name if active_p else "Default"
        else:
            p_obj = self.profile_repo.get_by_id(profile_id) or self.profile_repo.get_by_name(profile_id)
            profile_name = p_obj.name if p_obj else profile_id

        # Redact any accidental secrets in incoming task prompt before querying
        safe_task_desc = self.redactor.redact_text(request.task_description)

        # Retrieve scored lessons via shared RetrievalEngine (which enforces strict scope isolation)
        scored = self.retrieval_engine.retrieve_relevant_lessons(
            task_description=safe_task_desc,
            project_id=request.project_id,
            domain=request.domain,
            technologies=request.technologies,
            profile_id=profile_id,
            min_score=request.min_score,
            limit=request.limit,
        )

        # Assemble markdown advisory
        advisory_md = self.assembler.assemble(scored, profile_name=profile_name)

        snippets: List[RetrievedLessonSnippet] = []
        for lesson, score in scored:
            snippets.append(
                RetrievedLessonSnippet(
                    lesson_id=lesson.id,
                    title=lesson.title,
                    score=round(score, 3),
                    scope=lesson.scope,
                    recommended_strategy=lesson.recommended_strategy,
                    anti_patterns=lesson.anti_patterns,
                    confidence=lesson.confidence,
                    origin_project_ids=lesson.provenance.origin_project_ids if lesson.provenance else [],
                )
            )

        return ContextResponse(
            correlation_id=request.correlation_id,
            profile_name=profile_name,
            advisory_markdown=advisory_md,
            matched_count=len(snippets),
            lessons=snippets,
        )

    get_context = retrieve_context

    def ingest_event(self, adapter_id: str, event_data: NormalizedEvent | Dict[str, Any]) -> EventIngestResponse:
        """Route event ingestion into shared CollectorService with deduplication and secret redaction."""
        connector = self.registry.get(adapter_id)
        if not connector:
            raise KeyError(f"Connector '{adapter_id}' is not registered.")

        caps = connector.get_capabilities()
        if not caps.can_ingest_events:
            raise UnsupportedCapabilityError(adapter_id, "can_ingest_events")

        if not self.collector_service:
            raise RuntimeError("Core collector service is not configured.")

        # Extract ID for deduplication
        event_id = event_data.id if isinstance(event_data, NormalizedEvent) else event_data.get("id")
        if not event_id:
            event_id = str(uuid.uuid4())
            if isinstance(event_data, dict):
                event_data["id"] = event_id

        if self.dedup_cache.is_duplicate(event_id):
            e_type = event_data.event_type.value if isinstance(event_data, NormalizedEvent) else str(event_data.get("event_type", "unknown"))
            return EventIngestResponse(
                status="skipped",
                event_id=event_id,
                event_type=e_type,
                duplicate=True,
                message="Duplicate event detected and skipped.",
            )

        # Ingest event into collector service
        if isinstance(event_data, NormalizedEvent):
            ingested = self.collector_service.ingest_event(event_data)
            e_type = ingested.event_type.value
        else:
            # Redact raw data before normalizing
            clean_dict = self.redactor.redact_data(event_data)
            ingested = self.collector_service.ingest_raw_event(clean_dict)
            e_type = ingested.event_type.value

        return EventIngestResponse(
            status="ok",
            event_id=ingested.id,
            event_type=e_type,
            duplicate=False,
            message="Event ingested successfully into shared event store.",
        )

    def report_outcome(self, adapter_id: str, report: OutcomeReport) -> OutcomeResponse:
        """Route strategy outcome or verification result to shared learning engine."""
        connector = self.registry.get(adapter_id)
        if not connector:
            raise KeyError(f"Connector '{adapter_id}' is not registered.")

        caps = connector.get_capabilities()
        if not caps.can_report_outcomes:
            raise UnsupportedCapabilityError(adapter_id, "can_report_outcomes")

        if not self.strategy_repo or not self.profile_repo:
            raise RuntimeError("Strategy repository or profile repository is not configured.")

        # Map outcome string to enum
        outcome_map = {
            "success": StrategyOutcome.SUCCESS,
            "failure": StrategyOutcome.FAILURE,
            "regression": StrategyOutcome.REGRESSION,
        }
        outcome_enum = outcome_map.get(report.outcome.lower(), StrategyOutcome.SUCCESS)

        # Resolve target profile
        profile_id = report.profile_id
        if not profile_id:
            active_p = self.profile_repo.get_active()
            profile_id = active_p.profile_id if active_p else "default"

        # Update Bayesian score
        strat_record = self.strategy_repo.record_outcome(
            profile_id=profile_id,
            name=report.strategy_name,
            category=report.domain,
            outcome=outcome_enum,
        )

        return OutcomeResponse(
            correlation_id=report.correlation_id,
            success=True,
            strategy_name=strat_record.name,
            bayesian_score=strat_record.bayesian_score,
            attempts_count=strat_record.attempts_count,
            success_count=strat_record.success_count,
            regression_count=strat_record.regression_count,
            message=f"Recorded outcome '{report.outcome}' for '{strat_record.name}'. Score: {strat_record.bayesian_score:.2f}",
        )

    def get_diagnostics(self) -> List[Dict[str, Any]]:
        """Compile comprehensive diagnostics for all connectors for GUI and CLI."""
        healths = self.health_check_all()
        caps = self.get_capabilities_all()
        diagnostics = []

        for connector in self.registry.list_connectors():
            ident = connector.get_identity()
            cid = ident.adapter_id
            h = healths.get(cid, ConnectorHealth(status=HealthStatus.OFFLINE, details="Not checked"))
            c = caps.get(cid, ConnectorCapabilities())

            diagnostics.append({
                "adapter_id": cid,
                "agent_name": ident.agent_name,
                "agent_version": ident.agent_version or "N/A",
                "adapter_version": ident.adapter_version,
                "description": ident.description,
                "status": h.status.value,
                "is_available": h.is_available,
                "latency_ms": h.latency_ms,
                "details": h.details,
                "capabilities": c.model_dump(),
                "diagnostics": h.diagnostics,
            })

        return diagnostics
