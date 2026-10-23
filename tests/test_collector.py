"""Unit tests for collector service, normalizer, and simulation agent."""

from pathlib import Path
import pytest

from evodev.collector.collector_service import CollectorService
from evodev.collector.normalizer import EventNormalizer
from evodev.connectors.simulation import SimulationAgent
from evodev.models.events import EventType, TaskStartedEvent
from evodev.models.profile import ProfileManifest
from evodev.storage.db import DatabaseManager
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    EventRepository,
    ExperienceRepository,
    ProfileRepository,
)


@pytest.fixture
def collector_stack():
    db = DatabaseManager(":memory:")
    migrator = MigrationManager(db)
    migrator.run_migrations()

    p_repo = ProfileRepository(db)
    e_repo = ExperienceRepository(db)
    ev_repo = EventRepository(db)

    # Create active default profile
    manifest = ProfileManifest(name="DefaultProfile", version="1.0.0")
    p_repo.create(manifest, is_active=True)

    normalizer = EventNormalizer()
    service = CollectorService(ev_repo, e_repo, p_repo, normalizer)
    return service, e_repo, ev_repo


def test_normalizer_redacts_and_parses(collector_stack):
    service, _, _ = collector_stack
    raw_event = {
        "event_type": "task_started",
        "session_id": "ses-1",
        "task_id": "t-1",
        "project_id": "proj-auth",
        "task_description": "Configure OAuth using secret sk-proj-1234567890abcdef1234567890abcdef",
        "domain": "security",
        "languages": ["python"],
    }
    normalized = service.ingest_raw_event(raw_event)
    assert isinstance(normalized, TaskStartedEvent)
    assert "[REDACTED_OPENAI_KEY]" in normalized.task_description
    assert "sk-proj" not in normalized.task_description


def test_simulation_workflow_generates_experience(collector_stack):
    service, e_repo, ev_repo = collector_stack
    sim_agent = SimulationAgent(service)

    # Run complete workflow
    session_id = sim_agent.run_simulated_workflow(
        task_description="Resolve Outdated Android compileSdkVersion with Compose 1.7",
        project_id="android-client-app",
        domain="mobile",
        languages=["kotlin"],
        frameworks=["android", "compose"],
        initial_error="compileSdkVersion 33 does not meet Compose compiler minimum 34",
        resolution_strategy="update_gradle_compile_sdk",
        changed_files=["app/build.gradle.kts"],
        simulate_tests_passing=True,
        outcome="success",
    )

    # Verify events persisted
    events = ev_repo.list_by_session(session_id)
    assert len(events) >= 6

    # Verify experience record created
    experiences = e_repo.list_by_project("android-client-app")
    assert len(experiences) == 1
    exp = experiences[0]
    assert exp.domain == "mobile"
    assert "kotlin" in exp.languages
    assert exp.outcome == "success"
    assert exp.verification is not None
    assert exp.verification.passed is True
    assert "compileSdkVersion" in exp.initial_problem
