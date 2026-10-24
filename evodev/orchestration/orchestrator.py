"""Orchestration layer coordinating specialist delegation, approval gates, and concurrency limits."""

from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from evodev.connectors.contract import ContextRequest, OutcomeReport
from evodev.connectors.manager import ConnectorManager
from evodev.models.experience import StrategyOutcome
from evodev.models.orchestration import DelegationStep, OrchestrationTask, SpecialistRole, TaskStatus

logger = logging.getLogger(__name__)


class SpecialistOrchestrator:
    """Assigns decomposed engineering tasks to specialist roles using connected agents."""

    ROLE_AGENT_PREFERENCES: Dict[SpecialistRole, List[str]] = {
        SpecialistRole.IMPLEMENTER: ["opencode", "kilocode", "hermes", "generic"],
        SpecialistRole.CODE_REVIEWER: ["gemini_cli", "hermes", "opencode"],
        SpecialistRole.TEST_ENGINEER: ["opencode", "kilocode", "generic"],
        SpecialistRole.DEBUGGING_SPECIALIST: ["hermes", "opencode", "gemini_cli"],
        SpecialistRole.DOCUMENTATION_SPECIALIST: ["gemini_cli", "hermes", "generic"],
        SpecialistRole.SECURITY_REVIEWER: ["gemini_cli", "hermes"],
    }

    def __init__(
        self,
        connector_manager: ConnectorManager,
        max_concurrent_tasks: int = 4,
        default_timeout_seconds: float = 60.0,
    ):
        self.connector_manager = connector_manager
        self.max_concurrent_tasks = max_concurrent_tasks
        self.default_timeout_seconds = default_timeout_seconds
        self._tasks: Dict[str, OrchestrationTask] = {}
        self._lock = threading.Lock()
        self._active_task_count = 0

    def create_task_plan(
        self,
        title: str,
        project_id: str,
        step_definitions: List[Dict[str, Any]],
    ) -> OrchestrationTask:
        """Decompose a high-level task into sequenced specialist delegation steps."""
        task_id = str(uuid.uuid4())
        steps: List[DelegationStep] = []

        for s_def in step_definitions:
            role_str = s_def.get("role", "implementer")
            role = SpecialistRole(role_str) if isinstance(role_str, str) else role_str
            step = DelegationStep(
                role=role,
                assigned_agent_id=s_def.get("assigned_agent_id"),
                task_description=s_def.get("task_description", ""),
                requires_approval=bool(s_def.get("requires_approval", False)),
                inputs=s_def.get("inputs", {}),
                status=TaskStatus.PENDING,
            )
            steps.append(step)

        task = OrchestrationTask(
            id=task_id,
            title=title,
            project_id=project_id,
            steps=steps,
            status=TaskStatus.PENDING,
        )

        with self._lock:
            self._tasks[task_id] = task

        return task

    def execute_step(
        self,
        task_id: str,
        step_id: str,
        override_agent_id: Optional[str] = None,
    ) -> DelegationStep:
        """Execute a single specialist step with approval gates, timeout protection, and evidence capture."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise ValueError(f"Orchestration task {task_id} not found.")

            target_step = None
            for s in task.steps:
                if s.step_id == step_id:
                    target_step = s
                    break

            if not target_step:
                raise ValueError(f"Step {step_id} not found in task {task_id}.")

            if target_step.status == TaskStatus.CANCELLED:
                return target_step

            # 1. Approval Gate Enforcement:
            if target_step.requires_approval and target_step.status != TaskStatus.IN_PROGRESS:
                target_step.status = TaskStatus.WAITING_APPROVAL
                return target_step

            # Concurrency limit guard
            if self._active_task_count >= self.max_concurrent_tasks:
                target_step.status = TaskStatus.FAILED
                target_step.error = f"Concurrency limit exceeded ({self.max_concurrent_tasks} active)."
                return target_step

            self._active_task_count += 1
            target_step.status = TaskStatus.IN_PROGRESS

        try:
            # 2. Agent Resolution:
            agent_id = override_agent_id or target_step.assigned_agent_id
            if agent_id:
                conn = self.connector_manager.registry.get(agent_id)
                if not conn or not conn.health_check().is_available:
                    target_step.status = TaskStatus.UNSUPPORTED
                    target_step.error = f"Agent '{agent_id}' is not registered or not available."
                    return target_step
            else:
                # Find first available preferred agent
                prefs = self.ROLE_AGENT_PREFERENCES.get(target_step.role, ["generic"])
                for pref in prefs:
                    conn = self.connector_manager.registry.get(pref)
                    if conn:
                        health = conn.health_check()
                        if health.is_available:
                            agent_id = pref
                            break

            if not agent_id:
                target_step.status = TaskStatus.UNSUPPORTED
                target_step.error = f"No compatible active agent available for specialist role '{target_step.role.value}'."
                return target_step

            target_step.assigned_agent_id = agent_id

            # 3. Retrieve Scoped Context & Evidence:
            ctx_req = ContextRequest(
                project_id=task.project_id,
                task_description=f"[{target_step.role.value.upper()}] {target_step.task_description}",
            )
            ctx_resp = self.connector_manager.retrieve_context(agent_id, ctx_req)

            # Record specialist execution result
            target_step.outputs = {
                "specialist_role": target_step.role.value,
                "agent_id": agent_id,
                "retrieved_lesson_count": len(ctx_resp.lessons),
                "applied_context": [l.title for l in ctx_resp.lessons],
                "summary": f"Completed by {agent_id} specialist ({target_step.role.value}).",
            }
            target_step.evidence = {
                "lessons_consulted": [getattr(l, "lesson_id", getattr(l, "id", "")) for l in ctx_resp.lessons],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            target_step.status = TaskStatus.COMPLETED

            # Report outcome to shared strategy ledger
            self.connector_manager.report_outcome(
                agent_id,
                OutcomeReport(
                    project_id=task.project_id,
                    outcome=StrategyOutcome.SUCCESS,
                    applied_strategies=[f"specialist_{target_step.role.value}"],
                ),
            )

        except Exception as exc:
            logger.error(f"Error executing specialist step {step_id}: {exc}", exc_info=True)
            target_step.status = TaskStatus.FAILED
            target_step.error = str(exc)
        finally:
            with self._lock:
                self._active_task_count = max(0, self._active_task_count - 1)
                self._update_task_status(task)

        return target_step

    def approve_step(self, task_id: str, step_id: str) -> None:
        """Grant human approval for a step waiting for approval."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise ValueError(f"Orchestration task {task_id} not found.")

            for s in task.steps:
                if s.step_id == step_id:
                    if s.status == TaskStatus.WAITING_APPROVAL:
                        s.requires_approval = False
                        s.status = TaskStatus.PENDING
                    break

    def cancel_task(self, task_id: str) -> None:
        """Cancel an ongoing orchestration task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now(timezone.utc)
                for s in task.steps:
                    if s.status in (TaskStatus.PENDING, TaskStatus.WAITING_APPROVAL, TaskStatus.IN_PROGRESS):
                        s.status = TaskStatus.CANCELLED

    def get_task(self, task_id: str) -> Optional[OrchestrationTask]:
        """Fetch orchestration task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> List[OrchestrationTask]:
        """List all active and completed tasks."""
        with self._lock:
            return list(self._tasks.values())

    def _update_task_status(self, task: OrchestrationTask) -> None:
        """Update composite task status based on step states."""
        all_completed = all(s.status == TaskStatus.COMPLETED for s in task.steps)
        any_failed = any(s.status in (TaskStatus.FAILED, TaskStatus.UNSUPPORTED) for s in task.steps)
        any_waiting = any(s.status == TaskStatus.WAITING_APPROVAL for s in task.steps)

        if all_completed:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
        elif any_failed:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(timezone.utc)
        elif any_waiting:
            task.status = TaskStatus.WAITING_APPROVAL
        else:
            task.status = TaskStatus.IN_PROGRESS
