"""OpenCode connector: Configuration generator, session harvester, and adapter."""

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Union
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
from evodev.models.events import (
    NormalizedEvent,
    TaskFinishedEvent,
    TaskStartedEvent,
    ToolInvokedEvent,
    ToolResultEvent,
)
from evodev.models.experience import StrategyOutcome
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.repositories import (
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


class OpenCodeConnector(BaseAgentConnector):
    """Integrates OpenCode with EvoDev via MCP and session ingestion."""

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
        self._cached_version: Optional[str] = None
        self._version_checked: bool = False
        self._binary_path: Optional[str] = None

    def get_name(self) -> str:
        return "OpenCode"

    def get_identity(self) -> ConnectorIdentity:
        return ConnectorIdentity(
            adapter_id="opencode",
            agent_name="OpenCode",
            agent_version=self.get_version(),
            adapter_version="2.0.0",
            description="OpenCode integration via Model Context Protocol (MCP) stdio and session export harvesting",
        )

    def is_available(self, refresh: bool = False) -> bool:
        """Check if opencode executable is present in PATH with cached result."""
        if self._cached_available is None or refresh:
            self._binary_path = shutil.which("opencode")
            self._cached_available = self._binary_path is not None
        return self._cached_available

    def get_version(self, refresh: bool = False) -> Optional[str]:
        """Query installed OpenCode version once and cache the result."""
        if not self.is_available(refresh=refresh):
            self._cached_version = None
            self._version_checked = True
            return None
        if self._version_checked and not refresh:
            return self._cached_version
        self._version_checked = True
        try:
            cmd = self._binary_path or "opencode"
            res = subprocess.run(
                [cmd, "--version"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0:
                self._cached_version = res.stdout.strip()
                return self._cached_version
        except Exception:
            pass
        self._cached_version = None
        return None

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            can_retrieve_context=True,
            can_ingest_events=True,
            can_report_outcomes=True,
            can_verify=True,
            supported_event_types=[
                "task_started",
                "tool_invoked",
                "tool_result",
                "verification",
                "task_finished",
            ],
            supported_scopes=["global", "domain", "technology", "project", "preferences"],
            mcp_compliant=True,
            lifecycle_hooks_supported=False,
        )

    def health_check(self) -> ConnectorHealth:
        avail = self.is_available()
        ver = self.get_version() if avail else None
        status = HealthStatus.HEALTHY if avail else HealthStatus.DEGRADED
        details = (
            f"OpenCode CLI detected ({ver}). MCP stdio interface ready."
            if avail
            else "OpenCode binary not detected in PATH. MCP server remains operational for manual config."
        )
        return ConnectorHealth(
            status=status,
            is_available=avail,
            details=details,
            diagnostics={
                "version": ver or "Not installed",
                "mcp_server": "evodev.connectors.opencode_mcp",
                "binary_path": self._binary_path,
            },
        )

    def get_status(self) -> Dict[str, Any]:
        available = self.is_available()
        version = self.get_version() if available else None
        return {
            "name": self.get_name(),
            "available": available,
            "version": version or "Not installed",
            "mcp_server": "evodev.connectors.opencode_mcp",
            "supported_events": [
                "task_started",
                "tool_invoked",
                "tool_result",
                "verification",
                "task_finished",
            ],
        }

    def start(self) -> None:
        """Connector is active on demand via MCP stdio."""
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
            raise RuntimeError("CollectorService not provided to OpenCodeConnector")
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
            raise RuntimeError("Repositories not provided to OpenCodeConnector")

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
            message=f"Recorded OpenCode strategy outcome for '{record.name}'. Score: {record.bayesian_score:.2f}",
        )

    def generate_config(self, python_executable: str = "python") -> Dict[str, Any]:
        """Generate MCP configuration structure for OpenCode."""
        return {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "evodev": {
                    "type": "stdio",
                    "command": python_executable,
                    "args": ["-m", "evodev.connectors.opencode_mcp"],
                }
            },
        }

    def apply_to_project(
        self,
        project_dir: Path,
        python_executable: str = "python",
    ) -> Path:
        """Write opencode.json MCP registration to the project directory."""
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        config_path = project_dir / "opencode.json"

        cfg = self.generate_config(python_executable)

        # Merge if config already exists
        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if "mcp" not in existing:
                    existing["mcp"] = {}
                existing["mcp"]["evodev"] = cfg["mcp"]["evodev"]
                cfg = existing
            except Exception:
                pass

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

        return config_path

    def harvest_exported_session(
        self,
        session_data: Union[str, Dict[str, Any]],
        project_id: str,
        collector: CollectorService,
    ) -> List[NormalizedEvent]:
        """Parse an OpenCode session export JSON and feed events into CollectorService."""
        if isinstance(session_data, str):
            session_data = json.loads(session_data)

        events: List[NormalizedEvent] = []
        session_id = session_data.get("id", f"opencode-ses-{uuid.uuid4().hex[:8]}")
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        messages = session_data.get("messages", [])
        first_user_prompt = ""

        # Extract initial task description
        for msg in messages:
            if msg.get("role") == "user":
                parts = msg.get("parts", [])
                text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
                if text_parts:
                    first_user_prompt = " ".join(text_parts)
                    break

        # 1. Emit TaskStartedEvent
        start_ev = TaskStartedEvent(
            session_id=session_id,
            task_id=task_id,
            project_id=project_id,
            task_description=first_user_prompt or "OpenCode Interactive Task",
        )
        collector.ingest_event(start_ev)
        events.append(start_ev)

        # 2. Extract tool invocations and results
        for msg in messages:
            parts = msg.get("parts", [])
            for part in parts:
                p_type = part.get("type", "")
                if p_type == "tool_use" or "tool_call" in p_type:
                    tool_name = part.get("name") or part.get("tool_name", "unknown_tool")
                    args = part.get("input") or part.get("args", {})
                    call_id = part.get("id") or str(uuid.uuid4())

                    invoke_ev = ToolInvokedEvent(
                        session_id=session_id,
                        task_id=task_id,
                        project_id=project_id,
                        tool_name=tool_name,
                        call_id=call_id,
                        arguments=args,
                    )
                    collector.ingest_event(invoke_ev)
                    events.append(invoke_ev)

                elif p_type == "tool_result" or "tool_output" in p_type:
                    tool_name = part.get("name") or part.get("tool_name", "unknown_tool")
                    call_id = part.get("id") or str(uuid.uuid4())
                    content = part.get("content") or part.get("output", "")
                    exit_code = part.get("exit_code", 0)

                    result_ev = ToolResultEvent(
                        session_id=session_id,
                        task_id=task_id,
                        project_id=project_id,
                        tool_name=tool_name,
                        call_id=call_id,
                        exit_code=exit_code,
                        stdout=str(content),
                    )
                    collector.ingest_event(result_ev)
                    events.append(result_ev)

        # 3. Emit TaskFinishedEvent
        finish_ev = TaskFinishedEvent(
            session_id=session_id,
            task_id=task_id,
            project_id=project_id,
            outcome="success",
            summary="Imported OpenCode session completed",
        )
        collector.ingest_event(finish_ev)
        events.append(finish_ev)

        return events
