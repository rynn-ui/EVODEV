"""Tests for Hermes Agent connector adapter."""

import json
from pathlib import Path
import pytest

from evodev.config import EvoDevConfig
from evodev.connectors.contract import ContextRequest, OutcomeReport
from evodev.connectors.hermes import HermesConnector
from evodev.models.experience import KnowledgeScope, Lesson, StrategyOutcome
from evodev.models.profile import ProfileManifest
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    EventRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


@pytest.fixture
def hermes_setup(tmp_path):
    config = EvoDevConfig(data_dir=tmp_path / "data")
    config.ensure_directories()
    db = get_db(config)
    MigrationManager(db).run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    s_repo = StrategyRepository(db)
    ev_repo = EventRepository(db)

    p_repo.create(ProfileManifest(profile_id="p1", name="TestProfile"), is_active=True)

    engine = RetrievalEngine(l_repo, p_repo)
    connector = HermesConnector(
        retrieval_engine=engine,
        event_repo=ev_repo,
        strategy_repo=s_repo,
        lesson_repo=l_repo,
        profile_repo=p_repo,
    )
    return connector, l_repo, s_repo, tmp_path


def test_hermes_connector_contract_and_capabilities(hermes_setup):
    connector, _, _, _ = hermes_setup

    ident = connector.get_identity()
    assert ident.adapter_id == "hermes"
    assert "Hermes" in ident.agent_name

    caps = connector.get_capabilities()
    assert caps.supports_context_retrieval is True
    assert caps.supports_outcome_reporting is True
    assert "hermes_tool_calling" in caps.custom_features

    health = connector.health_check()
    assert health.is_healthy is True


def test_hermes_context_retrieval_and_outcome_reporting(hermes_setup):
    connector, l_repo, s_repo, _ = hermes_setup

    l_repo.create(
        Lesson(
            profile_id="p1",
            title="Hermes Structured Function Calling",
            trigger_pattern="json schemas",
            recommended_strategy="Pydantic models with extra='forbid'",
            scope=KnowledgeScope.GLOBAL,
        )
    )

    req = ContextRequest(
        project_id="proj_hermes",
        task_description="Define function calling json schemas for agent",
    )
    resp = connector.get_context(req)
    assert len(resp.lessons) >= 1
    assert "Pydantic models" in resp.lessons[0].recommended_strategy

    # Report outcome
    out_rep = OutcomeReport(
        project_id="proj_hermes",
        outcome=StrategyOutcome.SUCCESS,
        applied_strategies=["hermes_tool_calling_strategy"],
    )
    out_resp = connector.report_outcome(out_rep)
    assert out_resp.acknowledged is True

    # Check strategy recorded
    strat = s_repo.get("p1", "hermes_tool_calling_strategy")
    assert strat is not None
    assert strat.success_count == 1


def test_hermes_config_file_generation(hermes_setup):
    connector, _, _, tmp_path = hermes_setup

    conf_file = connector.generate_hermes_config(tmp_path)
    assert conf_file.is_file()

    with open(conf_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["agent"] == "hermes"
    assert "evodev_integration" in data
    tools = data["evodev_integration"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "evodev_retrieve_memory" in tool_names
    assert "evodev_report_outcome" in tool_names
