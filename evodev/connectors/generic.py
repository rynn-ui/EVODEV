"""Generic adapter interface for third-party AI coding agents and IDEs."""

from typing import Any, Dict, List, Optional
import uuid

from evodev.collector.collector_service import CollectorService
from evodev.connectors.base import BaseAgentConnector
from evodev.connectors.contract import (
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
)
from evodev.models.events import NormalizedEvent
from evodev.models.experience import StrategyOutcome
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.repositories import (
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


class GenericAdapter(BaseAgentConnector):
    """Universal adapter supporting REST or IPC communication with any IDE or agent."""

    def __init__(
        self,
        collector: CollectorService,
        lesson_repo: LessonRepository,
        profile_repo: ProfileRepository,
        strategy_repo: Optional[StrategyRepository] = None,
    ):
        self.collector = collector
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.strategy_repo = strategy_repo
        self.engine = RetrievalEngine(lesson_repo, profile_repo)
        self.assembler = ContextAssembler()

    def get_name(self) -> str:
        return "Generic Adapter"

    def get_identity(self) -> ConnectorIdentity:
        return ConnectorIdentity(
            adapter_id="generic",
            agent_name="Generic Adapter",
            agent_version="2.0.0",
            adapter_version="2.0.0",
            description="Universal REST, IPC, or programmatic adapter for custom AI coding agents and IDEs",
        )

    def is_available(self) -> bool:
        return True

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            can_retrieve_context=True,
            can_ingest_events=True,
            can_report_outcomes=True,
            can_verify=True,
            supported_event_types=["task_started", "tool_invoked", "tool_result", "verification", "task_finished"],
            supported_scopes=["global", "domain", "technology", "project", "preferences"],
            mcp_compliant=False,
            lifecycle_hooks_supported=False,
        )

    def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(
            status=HealthStatus.HEALTHY,
            is_available=True,
            details="Generic adapter is ready for in-process or REST IPC communication.",
            diagnostics={"protocol": "in-process/REST"},
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.get_name(),
            "available": True,
            "interfaces": ["REST", "JSON-IPC", "CLI"],
        }

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def assemble_context(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
    ) -> str:
        scored = self.engine.retrieve_relevant_lessons(
            task_description=task_description,
            project_id=project_id,
            domain=domain,
            technologies=technologies,
        )
        active_p = self.profile_repo.get_active()
        p_name = active_p.name if active_p else "Default"
        return self.assembler.assemble(scored, profile_name=p_name)

    def get_context(self, request: ContextRequest) -> ContextResponse:
        profile_id = request.profile_id
        if not profile_id:
            active_p = self.profile_repo.get_active()
            profile_id = active_p.profile_id if active_p else "default"
            profile_name = active_p.name if active_p else "Default"
        else:
            profile_name = profile_id

        scored = self.engine.retrieve_relevant_lessons(
            task_description=request.task_description,
            project_id=request.project_id,
            domain=request.domain,
            technologies=request.technologies,
            profile_id=profile_id,
            min_score=request.min_score,
            limit=request.limit,
        )

        advisory_md = self.assembler.assemble(scored, profile_name=profile_name)
        snippets = [
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
            for lesson, score in scored
        ]

        return ContextResponse(
            correlation_id=request.correlation_id,
            profile_name=profile_name,
            advisory_markdown=advisory_md,
            matched_count=len(snippets),
            lessons=snippets,
        )

    def ingest_event(self, event: NormalizedEvent | Dict[str, Any]) -> EventIngestResponse:
        if isinstance(event, NormalizedEvent):
            ingested = self.collector.ingest_event(event)
        else:
            ingested = self.collector.ingest_raw_event(event)
        return EventIngestResponse(
            status="ok",
            event_id=ingested.id,
            event_type=ingested.event_type.value,
            duplicate=False,
        )

    def report_outcome(self, outcome: OutcomeReport) -> OutcomeResponse:
        if not self.strategy_repo:
            raise RuntimeError("StrategyRepository not provided to GenericAdapter")

        outcome_map = {
            "success": StrategyOutcome.SUCCESS,
            "failure": StrategyOutcome.FAILURE,
            "regression": StrategyOutcome.REGRESSION,
        }
        enum_val = outcome_map.get(outcome.outcome.lower(), StrategyOutcome.SUCCESS)

        profile_id = outcome.profile_id
        if not profile_id:
            active_p = self.profile_repo.get_active()
            profile_id = active_p.profile_id if active_p else "default"

        record = self.strategy_repo.record_outcome(
            profile_id=profile_id,
            name=outcome.strategy_name,
            category=outcome.domain,
            outcome=enum_val,
        )

        return OutcomeResponse(
            correlation_id=outcome.correlation_id,
            success=True,
            strategy_name=record.name,
            bayesian_score=record.bayesian_score,
            attempts_count=record.attempts_count,
            success_count=record.success_count,
            regression_count=record.regression_count,
            message=f"Recorded generic strategy outcome for '{record.name}'. Score: {record.bayesian_score:.2f}",
        )

    def query_context(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return structured lessons and raw score data (backward-compatible)."""
        scored = self.engine.retrieve_relevant_lessons(
            task_description=task_description,
            project_id=project_id,
            domain=domain,
            technologies=technologies,
        )
        active_p = self.profile_repo.get_active()
        p_name = active_p.name if active_p else "Default"

        return {
            "profile_name": p_name,
            "formatted_advisory": self.assembler.assemble(scored, profile_name=p_name),
            "lessons": [
                {
                    "title": l.title,
                    "score": round(score, 3),
                    "scope": l.scope.value,
                    "recommendation": l.recommended_strategy,
                    "anti_patterns": l.anti_patterns,
                    "confidence": l.confidence,
                }
                for l, score in scored
            ],
        }

    def send_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest raw event from an external agent or hook (backward-compatible)."""
        normalized = self.collector.ingest_raw_event(raw_event)
        return {"status": "ok", "event_id": normalized.id, "event_type": normalized.event_type.value}
