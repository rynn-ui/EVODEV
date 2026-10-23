"""CLI handler for Gemini CLI / Antigravity lifecycle hooks (hooks.json)."""

import json
from pathlib import Path
import sys
from typing import Any, Dict

from evodev.collector.collector_service import CollectorService
from evodev.config import load_config
from evodev.models.events import (
    ErrorObservedEvent,
    TaskFinishedEvent,
    ToolResultEvent,
)
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


def handle_hook(hook_type: str) -> None:
    """Read stdin payload, execute hook action, and write stdout according to hook contract."""
    raw_input = sys.stdin.read().strip()
    payload: Dict[str, Any] = json.loads(raw_input) if raw_input else {}

    config = load_config()
    db = get_db(config)
    MigrationManager(db).run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    s_repo = StrategyRepository(db)
    e_repo = ExperienceRepository(db)
    ev_repo = EventRepository(db)

    collector = CollectorService(ev_repo, e_repo, p_repo)
    engine = RetrievalEngine(l_repo, p_repo)
    assembler = ContextAssembler()

    conv_id = payload.get("conversationId", "gemini-session")
    workspaces = payload.get("workspacePaths", [])
    project_id = Path(workspaces[0]).name if workspaces else "default-project"

    if hook_type == "pre-invocation":
        # Retrieve verified lessons for the active profile
        active_p = p_repo.get_active()
        p_name = active_p.name if active_p else "Default"

        scored = engine.retrieve_relevant_lessons(
            task_description=f"Active development task in {project_id}",
            project_id=project_id,
            domain="general",
            min_score=0.30,
            limit=3,
        )

        inject_steps = []
        if scored:
            advisory = assembler.assemble(scored, profile_name=p_name)
            inject_steps.append({"ephemeralMessage": advisory})

        out = {"injectSteps": inject_steps}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()

    elif hook_type == "post-tool-use":
        tool_call = payload.get("toolCall", {})
        tool_name = tool_call.get("name", "unknown_tool")
        err = payload.get("error")

        if err:
            collector.ingest_event(
                ErrorObservedEvent(
                    session_id=conv_id,
                    task_id=f"step-{payload.get('stepIdx', 0)}",
                    project_id=project_id,
                    error_type="ToolExecutionError",
                    error_message=str(err),
                )
            )

        collector.ingest_event(
            ToolResultEvent(
                session_id=conv_id,
                task_id=f"step-{payload.get('stepIdx', 0)}",
                project_id=project_id,
                tool_name=tool_name,
                exit_code=1 if err else 0,
                error=str(err) if err else None,
            )
        )

        sys.stdout.write("{}\n")
        sys.stdout.flush()

    elif hook_type == "stop":
        term_reason = payload.get("terminationReason", "model_stop")
        err = payload.get("error", "")

        collector.ingest_event(
            TaskFinishedEvent(
                session_id=conv_id,
                task_id="gemini-task-final",
                project_id=project_id,
                outcome="failure" if err else "success",
                summary=f"Terminated: {term_reason}",
            )
        )

        sys.stdout.write("{}\n")
        sys.stdout.flush()

    else:
        sys.stdout.write("{}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    hook = sys.argv[1] if len(sys.argv) > 1 else "pre-invocation"
    handle_hook(hook)
