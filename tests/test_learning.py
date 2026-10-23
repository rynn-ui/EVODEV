"""Unit tests for lesson extraction, strategy tracking, and experience consolidation."""

from datetime import datetime, timezone
import pytest

from evodev.learning.consolidator import ExperienceConsolidator
from evodev.learning.extractor import LessonExtractor
from evodev.learning.strategy_tracker import StrategyTracker
from evodev.models.experience import (
    EpistemicType,
    ExperienceRecord,
    KnowledgeScope,
    Lesson,
    Provenance,
    StrategyOutcome,
    VerificationEvidence,
)
from evodev.models.profile import ProfileManifest
from evodev.storage.db import DatabaseManager
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


@pytest.fixture
def learning_stack():
    db = DatabaseManager(":memory:")
    migrator = MigrationManager(db)
    migrator.run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    s_repo = StrategyRepository(db)

    manifest = ProfileManifest(name="AndroidProfile", version="1.0.0")
    p_repo.create(manifest, is_active=True)

    extractor = LessonExtractor()
    tracker = StrategyTracker(s_repo)
    consolidator = ExperienceConsolidator(l_repo)

    return manifest, extractor, tracker, consolidator, l_repo, s_repo


def test_extractor_requires_verification(learning_stack):
    manifest, extractor, _, _, _, _ = learning_stack

    # 1. Unverified task without passing tests -> should NOT extract positive lessons
    unverified_record = ExperienceRecord(
        profile_id=manifest.profile_id,
        session_id="s1",
        task_id="t1",
        project_id="p1",
        initial_problem="Syntax error in parser",
        outcome="failure",
        verification=None,
    )
    lessons = extractor.extract_lessons(unverified_record)
    assert len(lessons) == 0

    # 2. Verified task with passing tests -> extracts lesson
    verified_record = ExperienceRecord(
        profile_id=manifest.profile_id,
        session_id="s2",
        task_id="t2",
        project_id="p1",
        domain="mobile",
        languages=["kotlin"],
        frameworks=["android", "compose"],
        initial_problem="Compose 1.7 requires compileSdkVersion 34, found 33 in build.gradle",
        strategies_attempted=["update_gradle_compile_sdk"],
        errors_observed=["compileSdkVersion 33 does not meet Compose compiler minimum 34"],
        file_changes=["build.gradle.kts"],
        verification=VerificationEvidence(
            verification_type="test",
            passed=True,
            total_tests=8,
            passed_tests=8,
            failed_tests=0,
        ),
        outcome="success",
    )
    lessons = extractor.extract_lessons(verified_record)
    assert len(lessons) == 1
    l = lessons[0]
    assert "update_gradle_compile_sdk" in l.recommended_strategy
    assert len(l.anti_patterns) >= 1
    assert l.scope in (KnowledgeScope.TECHNOLOGY, KnowledgeScope.DOMAIN)
    assert l.confidence >= 0.80


def test_consolidator_merges_provenance_and_promotes(learning_stack):
    manifest, extractor, _, consolidator, l_repo, _ = learning_stack

    # Project 1 observation
    rec1 = ExperienceRecord(
        profile_id=manifest.profile_id,
        session_id="s1",
        task_id="t1",
        project_id="project-alpha",
        domain="mobile",
        languages=["kotlin"],
        frameworks=["android", "compose"],
        initial_problem="Error: Compose compiler 1.7 requires compileSdkVersion 34",
        strategies_attempted=["update_gradle_compile_sdk"],
        verification=VerificationEvidence(passed=True, total_tests=5, passed_tests=5),
        outcome="success",
    )
    l1 = extractor.extract_lessons(rec1)[0]
    l1.scope = KnowledgeScope.PROJECT  # Initially project scope
    consolidator.consolidate_lesson(l1)

    # Initial state: 1 project in provenance
    stored = l_repo.list_by_profile(manifest.profile_id)[0]
    assert len(stored.provenance.origin_project_ids) == 1
    assert stored.provenance.verification_count == 1

    # Project 2 recurrence of identical problem
    rec2 = ExperienceRecord(
        profile_id=manifest.profile_id,
        session_id="s2",
        task_id="t2",
        project_id="project-beta",  # Different repository!
        domain="mobile",
        languages=["kotlin"],
        frameworks=["android", "compose"],
        initial_problem="Error: Compose compiler 1.7 requires compileSdkVersion 34",
        strategies_attempted=["update_gradle_compile_sdk"],
        verification=VerificationEvidence(passed=True, total_tests=12, passed_tests=12),
        outcome="success",
    )
    l2 = extractor.extract_lessons(rec2)[0]
    consolidator.consolidate_lesson(l2)

    # After consolidation: single deduplicated lesson with merged provenance and promoted scope!
    all_lessons = l_repo.list_by_profile(manifest.profile_id, active_only=False)
    assert len(all_lessons) == 1
    merged = all_lessons[0]
    assert len(merged.provenance.origin_project_ids) == 2
    assert "project-alpha" in merged.provenance.origin_project_ids
    assert "project-beta" in merged.provenance.origin_project_ids
    assert merged.provenance.verification_count == 2
    # Scope promoted from PROJECT to TECHNOLOGY
    assert merged.scope == KnowledgeScope.TECHNOLOGY
    assert merged.confidence > l1.confidence


def test_consolidator_resolves_contradictions(learning_stack):
    manifest, _, _, consolidator, l_repo, _ = learning_stack

    # Old lesson: recommend downgrading library (confidence 0.60)
    old_lesson = Lesson(
        profile_id=manifest.profile_id,
        title="Downgrade library version",
        trigger_pattern="Dependency conflict in package-lock.json",
        recommended_strategy="Downgrade package X to 1.0.0",
        anti_patterns=["Upgrade package X to 2.0.0"],
        confidence=0.60,
    )
    l_repo.save(old_lesson)

    # New lesson with higher confidence and proof that upgrading works
    new_lesson = Lesson(
        profile_id=manifest.profile_id,
        title="Upgrade package with peer resolution",
        trigger_pattern="Dependency conflict in package-lock.json",
        recommended_strategy="Upgrade package X to 2.0.0",
        anti_patterns=["Downgrade package X to 1.0.0"],
        confidence=0.90,
    )
    consolidator.consolidate_lesson(new_lesson)

    # Old lesson should be marked inactive / superseded
    old_reloaded = l_repo.get_by_id(old_lesson.id)
    assert old_reloaded.active is False

    new_reloaded = l_repo.get_by_id(new_lesson.id)
    assert new_reloaded.active is True
