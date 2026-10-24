"""Gemini CLI / Antigravity connector: Hooks generator, MCP configuration, and adapter."""

import json
from pathlib import Path
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


class GeminiCLIConnector(BaseAgentConnector):
    """Integrates Gemini CLI and Antigravity via lifecycle hooks and MCP."""

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

    def get_name(self) -> str:
        return "GeminiCLI"

    def get_identity(self) -> ConnectorIdentity:
        return ConnectorIdentity(
            adapter_id="gemini",
            agent_name="Gemini CLI / Antigravity",
            agent_version="Antigravity 2.0" if self.is_available() else None,
            adapter_version="2.0.0",
            description="Integration via .agents/hooks.json lifecycle hooks and MCP tools",
        )

    def is_available(self) -> bool:
        """Check if Antigravity or Gemini config directory exists in user home or current project."""
        home = Path.home()
        gemini_dir = home / ".gemini"
        local_agents = Path(".agents")
        return gemini_dir.is_dir() or local_agents.is_dir()

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            can_retrieve_context=True,
            can_ingest_events=True,
            can_report_outcomes=True,
            can_verify=True,
            supported_event_types=["PreInvocation", "PostToolUse", "Stop", "error_observed"],
            supported_scopes=["global", "domain", "technology", "project", "preferences"],
            mcp_compliant=True,
            lifecycle_hooks_supported=True,
        )

    def health_check(self) -> ConnectorHealth:
        avail = self.is_available()
        status = HealthStatus.HEALTHY if avail else HealthStatus.DEGRADED
        details = (
            "Gemini/Antigravity environment detected. Hooks and MCP ready."
            if avail
            else "Gemini configuration directory not found. Adapter can still provision hooks to workspace."
        )
        return ConnectorHealth(
            status=status,
            is_available=avail,
            details=details,
            diagnostics={
                "home_gemini_exists": (Path.home() / ".gemini").is_dir(),
                "workspace_agents_exists": Path(".agents").is_dir(),
                "hook_mechanism": ".agents/hooks.json",
            },
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.get_name(),
            "available": self.is_available(),
            "hook_mechanism": ".agents/hooks.json",
            "supported_events": ["PreInvocation", "PostToolUse", "Stop"],
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
            raise RuntimeError("CollectorService not provided to GeminiCLIConnector")
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
            raise RuntimeError("Repositories not provided to GeminiCLIConnector")

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
            message=f"Recorded Gemini/Antigravity strategy outcome for '{record.name}'. Score: {record.bayesian_score:.2f}",
        )

    def generate_hooks_config(self, python_executable: str = "python") -> Dict[str, Any]:
        """Generate hooks.json configuration matching Antigravity specifications."""
        return {
            "evodev-experience-layer": {
                "enabled": True,
                "PreInvocation": [
                    {
                        "type": "command",
                        "command": f"{python_executable} -m evodev.connectors.gemini_hook pre-invocation",
                        "timeout": 15,
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{python_executable} -m evodev.connectors.gemini_hook post-tool-use",
                                "timeout": 15,
                            }
                        ],
                    }
                ],
                "Stop": [
                    {
                        "type": "command",
                        "command": f"{python_executable} -m evodev.connectors.gemini_hook stop",
                        "timeout": 15,
                    }
                ],
            }
        }

    def generate_mcp_config(self, python_executable: str = "python") -> Dict[str, Any]:
        """Generate mcp_config.json configuration."""
        return {
            "mcpServers": {
                "evodev": {
                    "command": python_executable,
                    "args": ["-m", "evodev.connectors.opencode_mcp"],
                }
            }
        }

    def apply_to_workspace(
        self,
        workspace_dir: Path,
        python_executable: str = "python",
    ) -> Dict[str, Path]:
        """Install .agents/hooks.json and .agents/mcp_config.json into target workspace."""
        workspace_dir = Path(workspace_dir)
        agents_dir = workspace_dir / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        hooks_file = agents_dir / "hooks.json"
        mcp_file = agents_dir / "mcp_config.json"

        hooks_cfg = self.generate_hooks_config(python_executable)
        mcp_cfg = self.generate_mcp_config(python_executable)

        # Merge hooks if existing
        if hooks_file.is_file():
            try:
                with open(hooks_file, "r", encoding="utf-8") as f:
                    existing_hooks = json.load(f)
                existing_hooks["evodev-experience-layer"] = hooks_cfg["evodev-experience-layer"]
                hooks_cfg = existing_hooks
            except Exception:
                pass

        # Merge mcp if existing
        if mcp_file.is_file():
            try:
                with open(mcp_file, "r", encoding="utf-8") as f:
                    existing_mcp = json.load(f)
                if "mcpServers" not in existing_mcp:
                    existing_mcp["mcpServers"] = {}
                existing_mcp["mcpServers"]["evodev"] = mcp_cfg["mcpServers"]["evodev"]
                mcp_cfg = existing_mcp
            except Exception:
                pass

        with open(hooks_file, "w", encoding="utf-8") as f:
            json.dump(hooks_cfg, f, indent=2)

        with open(mcp_file, "w", encoding="utf-8") as f:
            json.dump(mcp_cfg, f, indent=2)

        return {"hooks": hooks_file, "mcp": mcp_file}
