"""Hermes Agent connector adapter supporting tool execution, memory retrieval, and outcome ingestion."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from evodev.connectors.base import BaseAgentConnector
from evodev.connectors.contract import (
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorIdentity,
    ContextRequest,
    ContextResponse,
    EventIngestResponse,
    OutcomeReport,
    OutcomeResponse,
)
from evodev.models.events import NormalizedEvent
from evodev.models.experience import KnowledgeScope, Lesson, StrategyOutcome
from evodev.retrieval.engine import RetrievalEngine
from evodev.security.redactor import SecretRedactor
from evodev.storage.repositories import EventRepository, LessonRepository, ProfileRepository, StrategyRepository

logger = logging.getLogger(__name__)


class HermesConnector(BaseAgentConnector):
    """Adapter connecting Nous Research Hermes Agent runtime to EvoDev shared intelligence."""

    def __init__(
        self,
        retrieval_engine: Optional[RetrievalEngine] = None,
        event_repo: Optional[EventRepository] = None,
        strategy_repo: Optional[StrategyRepository] = None,
        lesson_repo: Optional[LessonRepository] = None,
        profile_repo: Optional[ProfileRepository] = None,
        redactor: Optional[SecretRedactor] = None,
    ):
        self.retrieval_engine = retrieval_engine
        self.event_repo = event_repo
        self.strategy_repo = strategy_repo
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.redactor = redactor or SecretRedactor()

    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize Hermes adapter."""
        pass

    def shutdown(self) -> None:
        """Shutdown Hermes adapter resources."""
        pass

    def get_name(self) -> str:
        return "Hermes Agent"

    def is_available(self) -> bool:
        return self.health_check().is_available

    def get_status(self) -> Dict[str, Any]:
        h = self.health_check()
        return {
            "name": self.get_name(),
            "available": h.is_available,
            "status": "healthy" if h.is_healthy else "unhealthy",
            "message": h.message,
            "diagnostics": h.diagnostics,
        }

    def get_identity(self) -> ConnectorIdentity:
        return ConnectorIdentity(
            adapter_id="hermes",
            agent_name="Hermes Agent",
            adapter_version="2.0.0",
            description="Hermes Agent runtime connector with tool schemas and persistent memory integration",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            can_retrieve_context=True,
            can_ingest_events=True,
            can_report_outcomes=True,
            can_verify=False,
            supported_event_types=[
                "task_started",
                "tool_invoked",
                "tool_result",
                "error_observed",
                "task_finished",
                "user_feedback",
            ],
            custom_features=["hermes_tool_calling", "persistent_memory", "skill_prompts"],
        )

    def health_check(self) -> ConnectorHealth:
        from evodev.connectors.contract import HealthStatus

        hermes_paths = [
            Path.cwd() / "hermes_config.json",
            Path.cwd() / ".hermes" / "config.json",
            Path.home() / ".hermes" / "config.json",
        ]
        is_installed = any(p.is_file() for p in hermes_paths)
        return ConnectorHealth(
            status=HealthStatus.HEALTHY,
            is_available=is_installed,
            details="Hermes config detected in workspace" if is_installed else "Hermes configuration standby",
            diagnostics={
                "checked_paths": [str(p) for p in hermes_paths],
                "workspace": str(Path.cwd()),
            },
        )

    def get_context(self, request: ContextRequest) -> ContextResponse:
        from evodev.connectors.contract import RetrievedLessonSnippet

        snippets: List[RetrievedLessonSnippet] = []
        p_name = "Default"
        if self.profile_repo:
            p_obj = self.profile_repo.get(request.profile_id) if request.profile_id else self.profile_repo.get_active()
            if p_obj:
                p_name = p_obj.name

        if self.retrieval_engine:
            ranked = self.retrieval_engine.retrieve_relevant_lessons(
                task_description=request.task_description,
                project_id=request.project_id,
                domain=request.domain,
                technologies=request.technologies,
                profile_id=request.profile_id,
                limit=request.limit,
            )
            for item in ranked:
                if isinstance(item, tuple):
                    lesson, score = item
                else:
                    lesson = item
                    score = getattr(lesson, "confidence", 1.0)
                snippets.append(
                    RetrievedLessonSnippet(
                        lesson_id=lesson.id,
                        title=lesson.title,
                        score=round(float(score), 3),
                        scope=lesson.scope,
                        recommended_strategy=lesson.recommended_strategy,
                        anti_patterns=lesson.anti_patterns,
                        confidence=lesson.confidence,
                        origin_project_ids=lesson.provenance.origin_project_ids if getattr(lesson, "provenance", None) else [],
                    )
                )

        advisory_md = "\n\n".join(
            f"### Verified Pattern: {s.title}\n"
            f"- Recommended Strategy: {s.recommended_strategy}\n"
            f"- Confidence: {s.confidence:.2f}"
            for s in snippets
        )

        return ContextResponse(
            correlation_id=request.correlation_id,
            profile_name=p_name,
            advisory_markdown=advisory_md,
            matched_count=len(snippets),
            lessons=snippets,
        )

    def ingest_event(self, event: NormalizedEvent | Dict[str, Any]) -> EventIngestResponse:
        from evodev.models.events import NormalizedEvent

        if isinstance(event, dict):
            event_obj = NormalizedEvent(**event)
        else:
            event_obj = event

        if self.event_repo:
            if hasattr(event_obj, "payload") and isinstance(event_obj.payload, dict):
                event_obj.payload = self.redactor.redact_dict(event_obj.payload)
            self.event_repo.save(event_obj)

        return EventIngestResponse(
            event_id=getattr(event_obj, "id", getattr(event_obj, "event_id", str(uuid.uuid4()))),
            event_type=getattr(event_obj, "event_type", "task_event"),
            duplicate=False,
            message=f"Event ingested for Hermes task {getattr(event_obj, 'task_id', '')}",
        )

    def report_outcome(self, outcome: OutcomeReport) -> OutcomeResponse:
        strat_names = list(outcome.applied_strategies)
        if outcome.strategy_name and outcome.strategy_name not in strat_names:
            strat_names.append(outcome.strategy_name)

        p_id = outcome.profile_id
        if not p_id and self.profile_repo:
            active_p = self.profile_repo.get_active()
            p_id = active_p.profile_id if active_p else "default"
        p_id = p_id or "default"

        raw_outcome = outcome.outcome
        if isinstance(raw_outcome, StrategyOutcome):
            mapped_outcome = raw_outcome
        elif isinstance(raw_outcome, str):
            mapping = {
                "success": StrategyOutcome.SUCCESS,
                "failure": StrategyOutcome.FAILURE,
                "regression": StrategyOutcome.REGRESSION,
            }
            mapped_outcome = mapping.get(raw_outcome.lower(), StrategyOutcome.SUCCESS)
        else:
            mapped_outcome = StrategyOutcome.SUCCESS

        latest_record = None
        if self.strategy_repo and strat_names:
            for strat_name in strat_names:
                latest_record = self.strategy_repo.record_outcome(
                    profile_id=p_id,
                    name=strat_name,
                    category=outcome.domain,
                    outcome=mapped_outcome,
                )

        return OutcomeResponse(
            correlation_id=outcome.correlation_id,
            success=True,
            strategy_name=latest_record.name if latest_record else (strat_names[0] if strat_names else ""),
            bayesian_score=latest_record.bayesian_score if latest_record else 0.5,
            attempts_count=latest_record.attempts_count if latest_record else 1,
            success_count=latest_record.success_count if latest_record else 1,
            regression_count=latest_record.regression_count if latest_record else 0,
            message="Hermes outcome recorded into Bayesian strategy ledger.",
            acknowledged=True,
        )

    def generate_hermes_config(self, output_dir: Optional[Path] = None) -> Path:
        """Generate a hermes_config.json exposing EvoDev tools to Hermes Agent."""
        target_dir = output_dir or Path.cwd()
        target_dir.mkdir(parents=True, exist_ok=True)
        config_file = target_dir / "hermes_config.json"

        config = {
            "agent": "hermes",
            "evodev_integration": {
                "version": "2.0.0",
                "connector_id": "hermes",
                "tools": [
                    {
                        "name": "evodev_retrieve_memory",
                        "description": "Query EvoDev persistent memory and verified lessons for this task",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "category": {"type": "string"},
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "evodev_report_outcome",
                        "description": "Report final verification outcome and applied strategies to EvoDev",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task_id": {"type": "string"},
                                "outcome": {"type": "string", "enum": ["success", "failure", "regression"]},
                                "strategies": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["task_id", "outcome"],
                        },
                    },
                ],
            },
        }

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        return config_file
