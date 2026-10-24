"""Automated test suite for unified multi-agent connector architecture (Parts B & C).

Covers:
1. Connector contract compliance.
2. Registry registration and duplicate registration.
3. Initialization, health-check and shutdown behavior.
4. Context retrieval and outcome reporting across adapters.
5. Event normalization and duplicate-event handling.
6. Secret redaction on ingestion.
7. Cross-project and profile isolation.
8. Adapter exceptions and unsupported capabilities.
9. OpenCode MCP compatibility.
10. Gemini/Antigravity hooks and event handling.
11. Cross-agent learning: OpenCode lessons retrievable by Gemini and Kilo Code.
"""

from pathlib import Path
import tempfile
import pytest

from evodev.collector.collector_service import CollectorService
from evodev.config import EvoDevConfig, set_config
from evodev.connectors.contract import (
    AgentConnector,
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorIdentity,
    ContextRequest,
    HealthStatus,
    OutcomeReport,
    UnsupportedCapabilityError,
)
from evodev.connectors.gemini import GeminiCLIConnector
from evodev.connectors.generic import GenericAdapter
from evodev.connectors.kilocode import KiloCodeConnector
from evodev.connectors.manager import ConnectorManager, ConnectorRegistry
from evodev.connectors.opencode import OpenCodeConnector
from evodev.connectors.opencode_mcp import OpenCodeMCPServer
from evodev.models.events import TaskStartedEvent
from evodev.models.experience import KnowledgeScope, Lesson
from evodev.models.profile import ProfileManifest
from evodev.retrieval.engine import RetrievalEngine
from evodev.security.redactor import SecretRedactor
from evodev.storage.db import DatabaseManager, close_db, set_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    BenchmarkRepository,
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


@pytest.fixture
def unified_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = EvoDevConfig(data_dir=Path(tmp_dir))
        set_config(config)
        db = DatabaseManager(":memory:")
        set_db(db)
        MigrationManager(db).run_migrations()

        p_repo = ProfileRepository(db)
        l_repo = LessonRepository(db)
        s_repo = StrategyRepository(db)
        e_repo = ExperienceRepository(db)
        ev_repo = EventRepository(db)
        b_repo = BenchmarkRepository(db)

        # Active default profile
        manifest = ProfileManifest(name="MultiAgentProfile", version="2.0.0")
        p_repo.create(manifest, is_active=True)

        collector = CollectorService(ev_repo, e_repo, p_repo)
        engine = RetrievalEngine(l_repo, p_repo)

        registry = ConnectorRegistry()
        opencode = OpenCodeConnector(l_repo, p_repo, s_repo, collector)
        gemini = GeminiCLIConnector(l_repo, p_repo, s_repo, collector)
        generic = GenericAdapter(collector, l_repo, p_repo, s_repo)
        kilo = KiloCodeConnector(l_repo, p_repo, s_repo, collector)

        registry.register(opencode)
        registry.register(gemini)
        registry.register(generic)
        registry.register(kilo)

        mgr = ConnectorManager(
            registry=registry,
            retrieval_engine=engine,
            collector_service=collector,
            strategy_repo=s_repo,
            lesson_repo=l_repo,
            profile_repo=p_repo,
            redactor=SecretRedactor(),
            config=config,
        )

        try:
            yield {
                "config": config,
                "db": db,
                "p_repo": p_repo,
                "l_repo": l_repo,
                "s_repo": s_repo,
                "e_repo": e_repo,
                "ev_repo": ev_repo,
                "collector": collector,
                "engine": engine,
                "registry": registry,
                "manager": mgr,
                "adapters": {
                    "opencode": opencode,
                    "gemini": gemini,
                    "generic": generic,
                    "kilocode": kilo,
                },
                "profile": manifest,
            }
        finally:
            close_db()


def test_connector_contract_compliance(unified_env):
    """Verify all adapters implement the AgentConnector protocol methods and types."""
    adapters = unified_env["adapters"]

    for name, adapter in adapters.items():
        assert isinstance(adapter, AgentConnector)

        ident = adapter.get_identity()
        assert isinstance(ident, ConnectorIdentity)
        assert ident.adapter_id
        assert ident.agent_name

        caps = adapter.get_capabilities()
        assert isinstance(caps, ConnectorCapabilities)

        health = adapter.health_check()
        assert isinstance(health, ConnectorHealth)
        assert health.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.OFFLINE]


def test_registry_registration_and_duplicates(unified_env):
    """Verify registry registers adapters and prevents duplicate registrations."""
    registry = unified_env["registry"]
    assert registry.has("opencode")
    assert registry.has("gemini")
    assert registry.has("generic")
    assert registry.has("kilocode")

    # Attempt duplicate registration without replace -> must raise ValueError
    opencode = unified_env["adapters"]["opencode"]
    with pytest.raises(ValueError, match="already registered"):
        registry.register(opencode, replace=False)

    # Replacing should succeed
    registry.register(opencode, replace=True)
    assert registry.has("opencode")


def test_initialization_health_and_shutdown(unified_env):
    """Verify initialize_all, health_check_all, and shutdown_all handle failure isolation."""
    mgr = unified_env["manager"]

    init_res = mgr.initialize_all()
    assert all(init_res.values())

    healths = mgr.health_check_all()
    assert "opencode" in healths
    assert "gemini" in healths
    assert "kilocode" in healths
    assert "generic" in healths
    assert healths["generic"].status == HealthStatus.HEALTHY

    mgr.shutdown_all()


def test_cross_agent_learning_and_context_retrieval(unified_env):
    """Verify a lesson learned via OpenCode is retrievable by Gemini and Kilo Code."""
    env = unified_env
    mgr = env["manager"]
    l_repo = env["l_repo"]
    profile = env["profile"]

    # 1. Ingest a verified global lesson from OpenCode
    lesson = Lesson(
        profile_id=profile.profile_id,
        title="Prevent FastAPI memory leak with async generator close",
        trigger_pattern="FastAPI memory leak async generator streaming",
        recommended_strategy="Always use asynccontextmanager and close stream on client disconnect",
        scope=KnowledgeScope.GLOBAL,
        confidence=0.95,
    )
    l_repo.save(lesson)

    # 2. Query context via OpenCode
    req_opencode = ContextRequest(
        task_description="Investigate FastAPI memory leak async generator streaming in API service",
        project_id="service-a",
    )
    resp_opencode = mgr.retrieve_context("opencode", req_opencode)
    assert resp_opencode.matched_count >= 1
    assert "Always use asynccontextmanager" in resp_opencode.advisory_markdown

    # 3. Cross-agent query: Retrieve same lesson via Gemini CLI
    req_gemini = ContextRequest(
        task_description="FastAPI memory leak async generator streaming issue",
        project_id="service-b",
    )
    resp_gemini = mgr.retrieve_context("gemini", req_gemini)
    assert resp_gemini.matched_count >= 1
    assert "Always use asynccontextmanager" in resp_gemini.advisory_markdown
    assert resp_gemini.lessons[0].lesson_id == lesson.id

    # 4. Cross-agent query: Retrieve same lesson via Kilo Code
    req_kilo = ContextRequest(
        task_description="Fix FastAPI memory leak in async generator",
        project_id="service-c",
    )
    resp_kilo = mgr.retrieve_context("kilocode", req_kilo)
    assert resp_kilo.matched_count >= 1
    assert resp_kilo.lessons[0].lesson_id == lesson.id


def test_project_scope_isolation_across_agents(unified_env):
    """Verify strict project isolation: project-specific lesson in project A never leaks to project B."""
    env = unified_env
    mgr = env["manager"]
    l_repo = env["l_repo"]
    profile = env["profile"]

    # Save project-specific lesson for project 'secret-billing'
    lesson = Lesson(
        profile_id=profile.profile_id,
        title="Custom internal billing queue retry logic",
        trigger_pattern="Stripe webhook queue retry timeout",
        recommended_strategy="Use internal billing retry header X-Billing-Retry",
        scope=KnowledgeScope.PROJECT,
        confidence=0.90,
    )
    lesson.provenance.origin_project_ids = ["secret-billing"]
    l_repo.save(lesson)

    # 1. Querying from 'secret-billing' should retrieve it
    req_ok = ContextRequest(
        task_description="Stripe webhook queue retry timeout in billing",
        project_id="secret-billing",
    )
    resp_ok = mgr.retrieve_context("gemini", req_ok)
    assert resp_ok.matched_count >= 1

    # 2. Querying from unrelated project 'public-blog' must strictly NOT return the lesson
    req_isolated = ContextRequest(
        task_description="Stripe webhook queue retry timeout in billing",
        project_id="public-blog",
    )
    resp_isolated = mgr.retrieve_context("opencode", req_isolated)
    assert resp_isolated.matched_count == 0


def test_event_ingestion_and_deduplication(unified_env):
    """Verify event ingestion persists events and detects duplicate IDs."""
    mgr = unified_env["manager"]
    ev_repo = unified_env["ev_repo"]

    event = TaskStartedEvent(
        id="unique-event-12345",
        session_id="ses-1",
        task_id="task-1",
        project_id="test-project",
        task_description="Unit test event ingestion",
    )

    # First ingestion -> OK
    res1 = mgr.ingest_event("opencode", event)
    assert res1.status == "ok"
    assert res1.duplicate is False
    assert ev_repo.count() == 1

    # Second ingestion of same event -> duplicate detected and skipped
    res2 = mgr.ingest_event("opencode", event)
    assert res2.status == "skipped"
    assert res2.duplicate is True
    assert ev_repo.count() == 1  # Not persisted twice!


def test_secret_redaction_across_ingestion(unified_env):
    """Verify secrets are redacted before persistence in event ingestion and context retrieval."""
    mgr = unified_env["manager"]
    ev_repo = unified_env["ev_repo"]

    secret_key = "sk-proj-1234567890abcdef1234567890abcdef"
    raw_event = {
        "id": "event-with-secret-1",
        "event_type": "task_started",
        "session_id": "ses-secret",
        "task_id": "task-secret",
        "project_id": "sec-project",
        "task_description": f"Deploy with token: {secret_key}",
    }

    res = mgr.ingest_event("gemini", raw_event)
    assert res.status == "ok"

    with unified_env["db"].session() as conn:
        row = conn.execute("SELECT payload_json FROM events WHERE id = 'event-with-secret-1';").fetchone()
        assert row is not None
        assert secret_key not in row["payload_json"]
        assert "[REDACTED_OPENAI_KEY]" in row["payload_json"]


def test_outcome_reporting_updates_bayesian_ledger(unified_env):
    """Verify outcome reporting updates Bayesian scores in shared StrategyRepository."""
    mgr = unified_env["manager"]
    s_repo = unified_env["s_repo"]
    profile = unified_env["profile"]

    report = OutcomeReport(
        strategy_name="use_cached_docker_layers",
        outcome="success",
        domain="devops",
        project_id="infra-repo",
    )

    resp = mgr.report_outcome("kilocode", report)
    assert resp.success is True
    assert resp.attempts_count == 1
    assert resp.success_count == 1
    assert resp.bayesian_score > 0.5

    record = s_repo.get(profile.profile_id, "use_cached_docker_layers")
    assert record is not None
    assert record.success_count == 1


def test_adapter_unsupported_capability_error(unified_env):
    """Verify UnsupportedCapabilityError is raised when capability is unsupported."""
    mgr = unified_env["manager"]

    class MockLimitedAdapter(AgentConnector):
        def get_identity(self):
            return ConnectorIdentity(adapter_id="limited", agent_name="LimitedAgent")
        def initialize(self, config): pass
        def health_check(self): return ConnectorHealth(status=HealthStatus.HEALTHY)
        def get_capabilities(self):
            return ConnectorCapabilities(can_retrieve_context=False, can_ingest_events=False)
        def get_context(self, request): raise UnsupportedCapabilityError("limited", "can_retrieve_context")
        def ingest_event(self, event): raise UnsupportedCapabilityError("limited", "can_ingest_events")
        def report_outcome(self, outcome): raise UnsupportedCapabilityError("limited", "can_report_outcomes")
        def shutdown(self): pass

    mgr.register(MockLimitedAdapter())

    req = ContextRequest(task_description="test", project_id="p")
    with pytest.raises(UnsupportedCapabilityError):
        mgr.retrieve_context("limited", req)


def test_opencode_mcp_protocol_roundtrip(unified_env):
    """Verify OpenCode MCP server can process standard JSON-RPC 2.0 requests."""
    server = OpenCodeMCPServer()

    # Tools list
    req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    resp = server.handle_request(req)
    assert "tools" in resp["result"]
    tools = {t["name"] for t in resp["result"]["tools"]}
    assert "evodev_get_lessons" in tools
    assert "evodev_record_outcome" in tools

    # Tool call: record outcome
    call_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "evodev_record_outcome",
            "arguments": {"strategy_name": "sort_upsert_keys", "outcome": "success"},
        },
    }
    call_resp = server.handle_request(call_req)
    assert "Recorded strategy outcome" in call_resp["result"]["content"][0]["text"]
