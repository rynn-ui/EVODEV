"""Unit tests for multi-factor ranking, retrieval engine, and context assembly."""

import pytest

from evodev.models.experience import KnowledgeScope, Lesson, Provenance
from evodev.models.profile import ProfileManifest
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.retrieval.ranker import MultiFactorRanker
from evodev.storage.db import DatabaseManager
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import LessonRepository, ProfileRepository


@pytest.fixture
def retrieval_stack():
    db = DatabaseManager(":memory:")
    migrator = MigrationManager(db)
    migrator.run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)

    manifest = ProfileManifest(name="CrossProjectProfile", version="1.0.0")
    p_repo.create(manifest, is_active=True)

    ranker = MultiFactorRanker()
    engine = RetrievalEngine(l_repo, p_repo, ranker)
    assembler = ContextAssembler()

    return manifest, l_repo, p_repo, ranker, engine, assembler


def test_strict_project_scope_isolation(retrieval_stack):
    manifest, l_repo, _, ranker, _, _ = retrieval_stack

    # Project-specific lesson created in Project A
    lesson = Lesson(
        profile_id=manifest.profile_id,
        title="Project A internal auth schema",
        trigger_pattern="AuthManager database schema",
        recommended_strategy="Use project A internal auth tables",
        scope=KnowledgeScope.PROJECT,
        provenance=Provenance(origin_project_ids=["project-A"]),
        confidence=0.9,
    )

    # 1. Querying from Project A should succeed
    score_a = ranker.calculate_score(
        lesson=lesson,
        target_project_id="project-A",
        target_task_description="AuthManager database schema query",
    )
    assert score_a > 0.5

    # 2. Querying from Project B MUST BE ABSOLUTELY EXCLUDED (-1.0)
    score_b = ranker.calculate_score(
        lesson=lesson,
        target_project_id="project-B",
        target_task_description="AuthManager database schema query",
    )
    assert score_b == -1.0


def test_cross_project_retrieval_of_promoted_lessons(retrieval_stack):
    manifest, l_repo, _, _, engine, assembler = retrieval_stack

    # Technology scoped lesson learned previously on Android Project 1
    android_lesson = Lesson(
        profile_id=manifest.profile_id,
        title="Android Compose compileSdkVersion compatibility",
        trigger_pattern="Compose compiler requires compileSdkVersion 34",
        context_conditions={"domain": "mobile", "languages": ["kotlin"], "frameworks": ["compose"]},
        recommended_strategy="Update compileSdk to 34 in build.gradle.kts",
        scope=KnowledgeScope.TECHNOLOGY,
        provenance=Provenance(origin_project_ids=["android-proj-1", "android-proj-2"]),
        confidence=0.92,
    )
    l_repo.save(android_lesson)

    # Unrelated Web React lesson
    react_lesson = Lesson(
        profile_id=manifest.profile_id,
        title="React 19 useActionState hook",
        trigger_pattern="Form submission state handling",
        context_conditions={"domain": "web", "languages": ["typescript"], "frameworks": ["react"]},
        recommended_strategy="Use useActionState instead of manual useState for forms",
        scope=KnowledgeScope.TECHNOLOGY,
        provenance=Provenance(origin_project_ids=["web-proj-1"]),
        confidence=0.88,
    )
    l_repo.save(react_lesson)

    # Query from completely NEW Android Project 7
    results = engine.retrieve_relevant_lessons(
        task_description="Build error: Compose compiler 1.7 requires compileSdkVersion 34, currently 33",
        project_id="android-project-7",  # Brand new unseen project!
        domain="mobile",
        technologies=["kotlin", "compose"],
        profile_id=manifest.profile_id,
    )

    assert len(results) >= 1
    top_lesson, score = results[0]
    assert top_lesson.title == "Android Compose compileSdkVersion compatibility"
    assert score > 0.60

    # Format context for coding agent
    context_text = assembler.assemble(results, profile_name="CrossProjectProfile")
    assert "EvoDev Verified Experience Advisory" in context_text
    assert "Update compileSdk to 34 in build.gradle.kts" in context_text
    assert "React 19" not in context_text  # Irrelevant knowledge filtered out!
