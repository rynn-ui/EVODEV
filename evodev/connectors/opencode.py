"""OpenCode connector: Configuration generator, session harvester, and adapter."""

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Union
import uuid

from evodev.collector.collector_service import CollectorService
from evodev.connectors.base import BaseAgentConnector
from evodev.models.events import (
    NormalizedEvent,
    TaskFinishedEvent,
    TaskStartedEvent,
    ToolInvokedEvent,
    ToolResultEvent,
)
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.repositories import LessonRepository, ProfileRepository


class OpenCodeConnector(BaseAgentConnector):
    """Integrates OpenCode with EvoDev via MCP and session ingestion."""

    def __init__(
        self,
        lesson_repo: Optional[LessonRepository] = None,
        profile_repo: Optional[ProfileRepository] = None,
    ):
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.engine = (
            RetrievalEngine(lesson_repo, profile_repo)
            if (lesson_repo and profile_repo)
            else None
        )
        self.assembler = ContextAssembler()

    def get_name(self) -> str:
        return "OpenCode"

    def is_available(self) -> bool:
        """Check if opencode executable is present in PATH."""
        return shutil.which("opencode") is not None

    def get_version(self) -> Optional[str]:
        """Query installed OpenCode version."""
        if not self.is_available():
            return None
        try:
            res = subprocess.run(
                ["opencode", "--version"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

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
