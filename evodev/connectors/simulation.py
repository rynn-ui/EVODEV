"""High-fidelity simulation agent adapter for integration testing and benchmarks."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from evodev.collector.collector_service import CollectorService
from evodev.connectors.base import BaseAgentConnector
from evodev.models.events import (
    ErrorObservedEvent,
    TaskFinishedEvent,
    TaskStartedEvent,
    TestExecutedEvent,
    ToolInvokedEvent,
    ToolResultEvent,
    VerificationRecordedEvent,
)


class SimulationAgent(BaseAgentConnector):
    """Deterministic coding agent simulator for running reproducible workflows."""

    def __init__(self, collector_service: CollectorService):
        self.collector = collector_service
        self.is_running = False

    def get_name(self) -> str:
        return "SimulationAgent"

    def is_available(self) -> bool:
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.get_name(),
            "available": True,
            "running": self.is_running,
            "mode": "in-process-deterministic",
        }

    def start(self) -> None:
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False

    def assemble_context(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
    ) -> str:
        return f"[EvoDev Context Advisory: {task_description}]"

    def run_simulated_workflow(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        languages: Optional[List[str]] = None,
        frameworks: Optional[List[str]] = None,
        initial_error: Optional[str] = None,
        resolution_strategy: str = "apply_fix",
        changed_files: Optional[List[str]] = None,
        simulate_tests_passing: bool = True,
        outcome: str = "success",
    ) -> str:
        """Simulate a complete developer task from start to verification and finish.
        
        Returns the session_id used.
        """
        session_id = f"sim-session-{uuid.uuid4().hex[:8]}"
        task_id = f"sim-task-{uuid.uuid4().hex[:8]}"
        languages = languages or ["python"]
        frameworks = frameworks or []
        changed_files = changed_files or ["src/main.py"]

        # 1. Task Started
        self.collector.ingest_event(
            TaskStartedEvent(
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                task_description=task_description,
                domain=domain,
                languages=languages,
                frameworks=frameworks,
            )
        )

        # 2. Initial tool execution or initial failure
        if initial_error:
            self.collector.ingest_event(
                ToolInvokedEvent(
                    session_id=session_id,
                    task_id=task_id,
                    project_id=project_id,
                    tool_name="run_command",
                    arguments={"command": "build"},
                )
            )
            self.collector.ingest_event(
                ToolResultEvent(
                    session_id=session_id,
                    task_id=task_id,
                    project_id=project_id,
                    tool_name="run_command",
                    exit_code=1,
                    stderr=initial_error,
                    error=initial_error,
                )
            )
            self.collector.ingest_event(
                ErrorObservedEvent(
                    session_id=session_id,
                    task_id=task_id,
                    project_id=project_id,
                    error_type="BuildError",
                    error_message=initial_error,
                )
            )

        # 3. Strategy / File edit tool execution
        self.collector.ingest_event(
            ToolInvokedEvent(
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                tool_name=resolution_strategy,
                arguments={"files": changed_files},
            )
        )
        self.collector.ingest_event(
            ToolResultEvent(
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                tool_name=resolution_strategy,
                exit_code=0,
                stdout="Modifications successfully applied",
            )
        )

        # 4. Test execution
        total_tests = 10 if simulate_tests_passing else 5
        passed_tests = 10 if simulate_tests_passing else 2
        failed_tests = 0 if simulate_tests_passing else 3

        self.collector.ingest_event(
            TestExecutedEvent(
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                test_command="pytest",
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                failures_summary="Test failure" if failed_tests > 0 else None,
            )
        )

        # 5. Verification recorded
        self.collector.ingest_event(
            VerificationRecordedEvent(
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                verification_type="test",
                passed=simulate_tests_passing,
                score=1.0 if simulate_tests_passing else 0.0,
                details="Automated pytest suite execution",
            )
        )

        # 6. Task finished
        self.collector.ingest_event(
            TaskFinishedEvent(
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                outcome=outcome,
                changed_files=changed_files,
                summary=f"Completed task with strategy {resolution_strategy}",
            )
        )

        return session_id
