"""Unit tests for EvoDev CLI commands and FastAPI daemon endpoints."""

from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner

from evodev.api.server import create_api_app
from evodev.cli.main import app
from evodev.config import EvoDevConfig, set_config
from evodev.models.experience import KnowledgeScope, Lesson
from evodev.models.profile import ProfileManifest
from evodev.storage.db import DatabaseManager, close_db, set_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import LessonRepository, ProfileRepository

runner = CliRunner()


@pytest.fixture
def cli_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        config = EvoDevConfig(data_dir=Path(temp_dir))
        set_config(config)
        db = DatabaseManager(config.db_path)
        set_db(db)
        MigrationManager(db).run_migrations()

        # Create active profile
        p_repo = ProfileRepository(db)
        manifest = ProfileManifest(name="CLITestProfile", version="1.0.0")
        p_repo.create(manifest, is_active=True)

        try:
            yield config, db, p_repo
        finally:
            close_db()


def test_cli_status_and_doctor(cli_env):
    res_status = runner.invoke(app, ["status"])
    assert res_status.exit_code == 0
    assert "Runtime Status" in res_status.stdout
    assert "CLITestProfile" in res_status.stdout

    res_doc = runner.invoke(app, ["doctor"])
    assert res_doc.exit_code == 0
    assert "SQLite Database" in res_doc.stdout
    assert "Secret Redactor" in res_doc.stdout


def test_cli_profile_management(cli_env):
    _, _, p_repo = cli_env

    # 1. Create Profile
    res_create = runner.invoke(app, ["profiles", "create", "NewMobileProfile", "--domain", "mobile"])
    assert res_create.exit_code == 0
    assert "Created profile" in res_create.stdout

    # 2. List Profiles
    res_list = runner.invoke(app, ["profiles", "list"])
    assert res_list.exit_code == 0
    assert "NewMobileProfile" in res_list.stdout

    # 3. Rename Profile
    res_rename = runner.invoke(app, ["profiles", "rename", "NewMobileProfile", "RenamedMobile"])
    assert res_rename.exit_code == 0
    assert "Renamed profile" in res_rename.stdout


def test_cli_connectors_and_retention(cli_env):
    res_conn = runner.invoke(app, ["connectors", "list"])
    assert res_conn.exit_code == 0
    assert "OpenCode" in res_conn.stdout
    assert "Gemini CLI" in res_conn.stdout

    res_ret = runner.invoke(app, ["retention", "status"])
    assert res_ret.exit_code == 0
    assert "Storage Retention" in res_ret.stdout


def test_api_daemon_endpoints(cli_env):
    config, db, p_repo = cli_env
    api_app = create_api_app(config)
    client = TestClient(api_app)

    # 1. GET /api/status
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["product_name"] == config.product_name
    assert data["active_profile"]["name"] == "CLITestProfile"

    # 2. Add lesson and test POST /api/query
    l_repo = LessonRepository(db)
    lesson = Lesson(
        profile_id=data["active_profile"]["profile_id"],
        title="Docker multi-stage build caching",
        trigger_pattern="Docker build slow caching",
        recommended_strategy="Order COPY package.json before source files",
        scope=KnowledgeScope.GLOBAL,
    )
    l_repo.save(lesson)

    query_payload = {
        "task_description": "Docker build slow caching issue in CI pipeline",
        "project_id": "api-service",
        "domain": "general",
    }
    query_res = client.post("/api/query", json=query_payload)
    assert query_res.status_code == 200
    q_data = query_res.json()
    assert q_data["matched_count"] >= 1
    assert "Order COPY package.json" in q_data["advisory_markdown"]

    # 3. Test Ingestion via POST /api/events
    event_payload = {
        "event_type": "task_started",
        "session_id": "api-ses-1",
        "task_id": "api-task-1",
        "project_id": "api-service",
        "task_description": "Setup test pipeline",
    }
    event_res = client.post("/api/events", json=event_payload)
    assert event_res.status_code == 200
    assert event_res.json()["status"] == "ingested"
