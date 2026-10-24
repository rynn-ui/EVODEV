"""Tests for specialist delegation, orchestration, approval gates, and concurrency limits."""

import pytest

from evodev.collector.collector_service import CollectorService
from evodev.config import EvoDevConfig
from evodev.connectors.contract import ConnectorCapabilities, ConnectorHealth, ConnectorIdentity
from evodev.connectors.manager import ConnectorManager, ConnectorRegistry
from evodev.connectors.opencode import OpenCodeConnector
from evodev.models.orchestration import SpecialistRole, TaskStatus
from evodev.models.profile import ProfileManifest
from evodev.orchestration.orchestrator import SpecialistOrchestrator
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


@pytest.fixture
def orchestrator_setup(tmp_path):
    config = EvoDevConfig(data_dir=tmp_path / "data")
    config.ensure_directories()
    db = get_db(config)
    MigrationManager(db).run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    s_repo = StrategyRepository(db)
    e_repo = ExperienceRepository(db)
    ev_repo = EventRepository(db)

    p_repo.create(ProfileManifest(profile_id="p1", name="TestProfile"), is_active=True)

    collector = CollectorService(ev_repo, e_repo, p_repo)
    engine = RetrievalEngine(l_repo, p_repo)

    registry = ConnectorRegistry()
    opencode = OpenCodeConnector(l_repo, p_repo, s_repo, collector)
    registry.register(opencode)

    manager = ConnectorManager(
        registry=registry,
        retrieval_engine=engine,
        collector_service=collector,
        strategy_repo=s_repo,
        lesson_repo=l_repo,
        profile_repo=p_repo,
        config=config,
    )

    orchestrator = SpecialistOrchestrator(manager, max_concurrent_tasks=2)
    return orchestrator, manager


def test_task_plan_creation_and_execution(orchestrator_setup):
    orchestrator, _ = orchestrator_setup

    steps = [
        {
            "role": SpecialistRole.IMPLEMENTER,
            "assigned_agent_id": "opencode",
            "task_description": "Implement authentication endpoints",
            "requires_approval": False,
        },
        {
            "role": SpecialistRole.TEST_ENGINEER,
            "assigned_agent_id": "opencode",
            "task_description": "Generate integration tests",
            "requires_approval": False,
        },
    ]

    task = orchestrator.create_task_plan(
        title="Auth feature slice",
        project_id="proj_auth",
        step_definitions=steps,
    )

    assert task.id is not None
    assert len(task.steps) == 2
    assert task.status == TaskStatus.PENDING

    # Execute first step
    step1 = orchestrator.execute_step(task.id, task.steps[0].step_id)
    assert step1.status == TaskStatus.COMPLETED
    assert "retrieved_lesson_count" in step1.outputs


def test_human_approval_gate_enforcement(orchestrator_setup):
    orchestrator, _ = orchestrator_setup

    steps = [
        {
            "role": SpecialistRole.SECURITY_REVIEWER,
            "assigned_agent_id": "opencode",
            "task_description": "Deploy to staging and run vulnerability scan",
            "requires_approval": True,  # High impact: requires human approval
        }
    ]

    task = orchestrator.create_task_plan("Deploy to staging", "proj_1", steps)
    step = task.steps[0]

    # Attempting to execute unapproved step should transition to WAITING_APPROVAL
    res = orchestrator.execute_step(task.id, step.step_id)
    assert res.status == TaskStatus.WAITING_APPROVAL

    # Grant explicit human approval
    orchestrator.approve_step(task.id, step.step_id)

    # Now executing executes the step to completion
    res2 = orchestrator.execute_step(task.id, step.step_id)
    assert res2.status == TaskStatus.COMPLETED


def test_unsupported_specialist_agent(orchestrator_setup):
    orchestrator, _ = orchestrator_setup

    # Ask for a role with an agent that is not registered
    steps = [
        {
            "role": SpecialistRole.SECURITY_REVIEWER,
            "assigned_agent_id": "non_existent_security_bot",
            "task_description": "Audit penetration vectors",
            "requires_approval": False,
        }
    ]

    task = orchestrator.create_task_plan("Security audit", "proj_sec", steps)
    res = orchestrator.execute_step(task.id, task.steps[0].step_id)
    assert res.status == TaskStatus.UNSUPPORTED


def test_cancel_orchestration_task(orchestrator_setup):
    orchestrator, _ = orchestrator_setup

    steps = [
        {"role": SpecialistRole.IMPLEMENTER, "task_description": "Task 1", "requires_approval": False},
        {"role": SpecialistRole.TEST_ENGINEER, "task_description": "Task 2", "requires_approval": False},
    ]

    task = orchestrator.create_task_plan("Long running plan", "proj_cancel", steps)
    orchestrator.cancel_task(task.id)

    cancelled_task = orchestrator.get_task(task.id)
    assert cancelled_task.status == TaskStatus.CANCELLED
    assert all(s.status == TaskStatus.CANCELLED for s in cancelled_task.steps)
