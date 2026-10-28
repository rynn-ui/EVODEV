"""Unit tests for agent connectors (OpenCode, Gemini CLI, Generic, Simulation)."""

import json
from pathlib import Path
import tempfile
import pytest

from evodev.collector.collector_service import CollectorService
from evodev.connectors.gemini import GeminiCLIConnector
from evodev.connectors.generic import GenericAdapter
from evodev.connectors.opencode import OpenCodeConnector
from evodev.connectors.opencode_mcp import OpenCodeMCPServer
from evodev.models.experience import KnowledgeScope, Lesson
from evodev.models.profile import ProfileManifest
from evodev.storage.db import DatabaseManager
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


@pytest.fixture
def connector_stack():
    db = DatabaseManager(":memory:")
    migrator = MigrationManager(db)
    migrator.run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    s_repo = StrategyRepository(db)
    e_repo = ExperienceRepository(db)
    ev_repo = EventRepository(db)

    manifest = ProfileManifest(name="ConnectorsProfile", version="1.0.0")
    p_repo.create(manifest, is_active=True)

    collector = CollectorService(ev_repo, e_repo, p_repo)

    return db, p_repo, l_repo, s_repo, e_repo, ev_repo, collector, manifest


def test_opencode_connector_real_installation(connector_stack):
    _, p_repo, l_repo, _, _, _, _, _ = connector_stack
    connector = OpenCodeConnector(l_repo, p_repo)

    # OpenCode is installed on the host machine
    assert connector.is_available() is True
    version = connector.get_version()
    assert version is not None
    assert "1.19" in version

    # Test config generation
    cfg = connector.generate_config(python_executable="python")
    assert "mcp" in cfg
    assert "evodev" in cfg["mcp"]
    assert cfg["mcp"]["evodev"]["type"] == "local"
    assert cfg["mcp"]["evodev"]["command"] == ["python", "-m", "evodev.connectors.opencode_mcp"]
    assert cfg["mcp"]["evodev"]["enabled"] is True

    with tempfile.TemporaryDirectory() as tmp_proj:
        cfg_path = connector.apply_to_project(Path(tmp_proj))
        assert cfg_path.is_file()
        with open(cfg_path, "r", encoding="utf-8") as f:
            written = json.load(f)
        assert written["mcp"]["evodev"]["type"] == "local"
        assert written["mcp"]["evodev"]["enabled"] is True


def test_opencode_session_harvester(connector_stack):
    _, _, _, _, e_repo, _, collector, _ = connector_stack
    connector = OpenCodeConnector()

    sample_session = {
        "id": "ses_test123",
        "messages": [
            {
                "role": "user",
                "parts": [{"type": "text", "text": "Fix Dockerfile build failure for Alpine node"}],
            },
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "tool_use",
                        "name": "run_command",
                        "input": {"command": "docker build ."},
                    },
                    {
                        "type": "tool_result",
                        "name": "run_command",
                        "content": "Successfully built image",
                        "exit_code": 0,
                    },
                ],
            },
        ],
    }

    events = connector.harvest_exported_session(sample_session, "docker-project", collector)
    assert len(events) >= 3

    # Check experience record was synthesized
    exps = e_repo.list_by_project("docker-project")
    assert len(exps) == 1
    assert "Dockerfile" in exps[0].initial_problem


def test_opencode_mcp_server_protocol(connector_stack):
    server = OpenCodeMCPServer()

    # 1. Initialize
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    init_res = server.handle_request(init_req)
    assert init_res["result"]["serverInfo"]["name"] == "evodev"

    # 2. List tools
    list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    list_res = server.handle_request(list_req)
    tool_names = [t["name"] for t in list_res["result"]["tools"]]
    assert "evodev_get_lessons" in tool_names
    assert "evodev_record_outcome" in tool_names
    assert "evodev_report_verification" in tool_names

    # 3. Call tool: record outcome
    call_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "evodev_record_outcome",
            "arguments": {
                "strategy_name": "update_docker_base_image",
                "outcome": "success",
                "domain": "devops",
            },
        },
    }
    call_res = server.handle_request(call_req)
    assert "Recorded strategy outcome" in call_res["result"]["content"][0]["text"]


def test_gemini_cli_connector_hooks_and_mcp():
    connector = GeminiCLIConnector()
    assert connector.get_name() == "GeminiCLI"

    hooks = connector.generate_hooks_config("python")
    hook_entry = hooks["evodev-experience-layer"]
    assert "PreInvocation" in hook_entry
    assert "PostToolUse" in hook_entry
    assert "Stop" in hook_entry

    with tempfile.TemporaryDirectory() as tmp_ws:
        res = connector.apply_to_workspace(Path(tmp_ws), "python")
        assert res["hooks"].is_file()
        assert res["mcp"].is_file()


def test_generic_adapter(connector_stack):
    _, p_repo, l_repo, _, _, _, collector, manifest = connector_stack
    adapter = GenericAdapter(collector, l_repo, p_repo)

    # Ingest lesson
    lesson = Lesson(
        profile_id=manifest.profile_id,
        title="PostgreSQL deadlocks on concurrent upsert",
        trigger_pattern="deadlock detected in transaction",
        recommended_strategy="Sort keys before bulk upsert",
        scope=KnowledgeScope.GLOBAL,
    )
    l_repo.save(lesson)

    # Query context via Generic Adapter
    res = adapter.query_context(
        task_description="Fix error: deadlock detected in transaction",
        project_id="payment-service",
    )
    assert len(res["lessons"]) == 1
    assert res["lessons"][0]["title"] == "PostgreSQL deadlocks on concurrent upsert"
    assert "Sort keys before bulk upsert" in res["formatted_advisory"]
