"""Kilo Code connector: Config generator and adapter for Kilo Code AI agent."""

import json
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

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


class KiloCodeConnector(BaseAgentConnector):
    """Integrates Kilo Code agent with EvoDev via MCP protocol and config provisioning."""

    def __init__(
        self,
        lesson_repo: Optional[LessonRepository] = None,
        profile_repo: Optional[ProfileRepository] = None,
        strategy_repo: Optional[StrategyRepository] = None,
        collector_service: Optional[CollectorService] = None,
    ):
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.strategy_repo = strategy_repo
        self.collector = collector_service
        self.engine = (
            RetrievalEngine(lesson_repo, profile_repo)
            if (lesson_repo and profile_repo)
            else None
        )
        self.assembler = ContextAssembler()
        self._cached_available: Optional[bool] = None
        self._binary_path: Optional[str] = None

    def get_name(self) -> str:
        return "Kilo Code"

    def get_identity(self) -> ConnectorIdentity:
        return ConnectorIdentity(
            adapter_id="kilocode",
            agent_name="Kilo Code",
            agent_version="1.0" if self.is_available() else None,
            adapter_version="2.0.0",
            description="Kilo Code integration via .kilo/mcp.json and Model Context Protocol stdio",
        )

    def is_available(self, refresh: bool = False) -> bool:
        """Check if kilo command or .kilo workspace exists with cached result."""
        if self._cached_available is None or refresh:
            self._binary_path = shutil.which("kilo")
            self._cached_available = self._binary_path is not None or Path(".kilo").is_dir()
        return self._cached_available

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            can_retrieve_context=True,
            can_ingest_events=True,
            can_report_outcomes=True,
            can_verify=True,
            supported_event_types=["task_started", "tool_invoked", "tool_result", "verification", "task_finished"],
            supported_scopes=["global", "domain", "technology", "project", "preferences"],
            mcp_compliant=True,
            lifecycle_hooks_supported=False,
        )

    def health_check(self) -> ConnectorHealth:
        avail = self.is_available()
        status = HealthStatus.HEALTHY if avail else HealthStatus.DEGRADED
        details = (
            "Kilo Code binary or workspace detected. MCP stdio integration ready."
            if avail
            else "Kilo Code CLI not found. MCP configuration can still be provisioned to project."
        )
        return ConnectorHealth(
            status=status,
            is_available=avail,
            details=details,
            diagnostics={
                "binary_path": self._binary_path,
                "workspace_kilo_exists": Path(".kilo").is_dir(),
            },
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.get_name(),
            "available": self.is_available(),
            "mcp_server": "evodev.connectors.opencode_mcp",
            "supported_events": ["task_started", "tool_invoked", "tool_result", "verification", "task_finished"],
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
        if not self.engine:
            return ""
        scored = self.engine.retrieve_relevant_lessons(
            task_description=task_description,
            project_id=project_id,
            domain=domain,
            technologies=technologies,
        )
        active_p = self.profile_repo.get_active() if self.profile_repo else None
        p_name = active_p.name if active_p else "Default"
        return self.assembler.assemble(scored, profile_name=p_name)

    def get_context(self, request: ContextRequest) -> ContextResponse:
        if not self.engine:
            return ContextResponse(
                correlation_id=request.correlation_id,
                profile_name="Default",
                advisory_markdown="",
                matched_count=0,
                lessons=[],
            )

        profile_id = request.profile_id
        if not profile_id and self.profile_repo:
            active_p = self.profile_repo.get_active()
            profile_id = active_p.profile_id if active_p else "default"
            profile_name = active_p.name if active_p else "Default"
        else:
            profile_name = profile_id or "Default"

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
        if not self.collector:
            raise RuntimeError("CollectorService not provided to KiloCodeConnector")
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
        if not self.strategy_repo or not self.profile_repo:
            raise RuntimeError("Repositories not provided to KiloCodeConnector")

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
            message=f"Recorded Kilo Code strategy outcome for '{record.name}'. Score: {record.bayesian_score:.2f}",
        )

    def generate_config(self, python_executable: str = "python") -> Dict[str, Any]:
        """Generate MCP configuration structure for Kilo Code."""
        return {
            "mcpServers": {
                "evodev": {
                    "command": python_executable,
                    "args": ["-m", "evodev.connectors.opencode_mcp"],
                }
            }
        }

    def apply_to_project(
        self,
        project_dir: Path,
        python_executable: str = "python",
    ) -> Path:
        """Write .kilo/mcp.json MCP registration to project directory."""
        project_dir = Path(project_dir)
        kilo_dir = project_dir / ".kilo"
        kilo_dir.mkdir(parents=True, exist_ok=True)
        config_path = kilo_dir / "mcp.json"

        cfg = self.generate_config(python_executable)

        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if "mcpServers" not in existing:
                    existing["mcpServers"] = {}
                existing["mcpServers"]["evodev"] = cfg["mcpServers"]["evodev"]
                cfg = existing
            except Exception:
                pass

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

        return config_path
