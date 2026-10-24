"""Tests for categorized persistent memory, secret redaction, and scope enforcement."""

import pytest
from evodev.config import EvoDevConfig
from evodev.memory.manager import MemoryManager, ScopeViolationError
from evodev.models.experience import KnowledgeScope, Lesson
from evodev.models.memory import MemoryCategory
from evodev.models.profile import ProfileManifest
from evodev.security.redactor import SecretRedactor
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import LessonRepository, MemoryRepository, ProfileRepository


@pytest.fixture
def memory_setup(tmp_path):
    config = EvoDevConfig(data_dir=tmp_path / "data")
    config.ensure_directories()
    db = get_db(config)
    MigrationManager(db).run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    mem_repo = MemoryRepository(db)
    redactor = SecretRedactor()

    p_repo.create(ProfileManifest(profile_id="p1", name="TestProfile"), is_active=True)

    manager = MemoryManager(
        memory_repo=mem_repo,
        lesson_repo=l_repo,
        profile_repo=p_repo,
        redactor=redactor,
    )
    return manager, mem_repo, l_repo, p_repo


def test_record_memory_and_secret_redaction(memory_setup):
    manager, mem_repo, _, _ = memory_setup

    item = manager.record_memory(
        category=MemoryCategory.PREFERENCES,
        title="Database key secret sk-proj-1234567890abcdef1234567890 should not leak",
        content={"note": "API key is sk-proj-999888777666555444333222111"},
        scope=KnowledgeScope.GLOBAL,
    )

    assert item.id is not None
    assert "sk-proj-1234567890abcdef1234567890" not in item.title
    assert "[REDACTED_API_KEY]" in item.title or "[REDACTED" in item.title
    assert "sk-proj-999888777666555444333222111" not in str(item.content)


def test_scope_violation_enforcement(memory_setup):
    manager, _, _, _ = memory_setup

    # Project private memory without project_id must raise ScopeViolationError
    with pytest.raises(ScopeViolationError):
        manager.record_memory(
            category=MemoryCategory.PROJECT_PRIVATE,
            title="Internal design spec",
            content={"info": "sensitive"},
            project_id=None,
        )


def test_intelligent_recall_and_cross_project_isolation(memory_setup):
    manager, _, _, _ = memory_setup

    # Memory for Project A
    manager.record_memory(
        category=MemoryCategory.PROJECT_PRIVATE,
        title="Project Alpha architecture",
        content={"db": "PostgreSQL"},
        project_id="proj_alpha",
    )

    # General memory
    manager.record_memory(
        category=MemoryCategory.ARCHITECTURE,
        title="Microservice messaging pattern",
        content={"queue": "RabbitMQ"},
        scope=KnowledgeScope.GLOBAL,
    )

    # Query from Project Alpha: should find both
    results_alpha = manager.retrieve_context(
        query="architecture",
        project_id="proj_alpha",
    )
    titles_alpha = [m.title for m in results_alpha]
    assert any("Project Alpha architecture" in t for t in titles_alpha)
    assert any("Microservice messaging pattern" in t for t in titles_alpha)

    # Query from Project Beta: Project Alpha private memory MUST NOT be visible
    results_beta = manager.retrieve_context(
        query="architecture",
        project_id="proj_beta",
    )
    titles_beta = [m.title for m in results_beta]
    assert not any("Project Alpha architecture" in t for t in titles_beta)
    assert any("Microservice messaging pattern" in t for t in titles_beta)


def test_contradiction_detection_against_anti_patterns(memory_setup):
    manager, _, l_repo, _ = memory_setup

    # Register an active lesson
    lesson = Lesson(
        profile_id="p1",
        title="Use Async I/O for Web Servers",
        trigger_pattern="web server performance",
        recommended_strategy="asyncio event loop",
        anti_patterns=["threading.Thread per request"],
    )
    l_repo.create(lesson)

    # Anti-pattern memory that contradicts recommended strategy
    bad_mem = manager.record_memory(
        category=MemoryCategory.ANTI_PATTERNS,
        title="Asyncio event loop causes deadlocks",
        content={"details": "never use asyncio event loop in production"},
        scope=KnowledgeScope.GLOBAL,
    )

    contradictions = manager.detect_contradictions(bad_mem)
    assert len(contradictions) > 0
    assert "conflicts with recommended lesson" in contradictions[0]


def test_duplicate_memory_consolidation(memory_setup):
    manager, mem_repo, _, _ = memory_setup

    manager.record_memory(
        category=MemoryCategory.PREFERENCES,
        title="Code style prefer ruff",
        content={"tool": "ruff", "version": "0.1.0"},
        scope=KnowledgeScope.GLOBAL,
    )

    # Same title should merge into existing record rather than create duplicate
    merged = manager.record_memory(
        category=MemoryCategory.PREFERENCES,
        title="Code style prefer ruff",
        content={"args": ["--fix"]},
        scope=KnowledgeScope.GLOBAL,
    )

    all_prefs = mem_repo.list_by_profile("p1", category=MemoryCategory.PREFERENCES, active_only=True)
    assert len(all_prefs) == 1
    assert merged.provenance.verification_count >= 2
    assert merged.content.get("args") == ["--fix"]
