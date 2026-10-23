"""Unit tests for storage, database connection, migrations, and repositories."""

import pytest

from evodev.models.experience import (
    EpistemicType,
    ExperienceRecord,
    KnowledgeScope,
    Lesson,
    StrategyOutcome,
    VerificationEvidence,
)
from evodev.models.profile import ProfileManifest, ProfilePackage, ProfileVersion
from evodev.storage.db import DatabaseManager
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


@pytest.fixture
def in_memory_db():
    db = DatabaseManager(":memory:")
    migrator = MigrationManager(db)
    migrator.run_migrations()
    return db


def test_profile_repository_crud(in_memory_db):
    repo = ProfileRepository(in_memory_db)

    # 1. Create
    m1 = ProfileManifest(name="WebDevPro", version="1.0.0")
    repo.create(m1, is_active=True)

    m2 = ProfileManifest(name="AndroidExpert", version="1.0.0")
    repo.create(m2, is_active=False)

    # 2. Get by name & active
    active = repo.get_active()
    assert active is not None
    assert active.name == "WebDevPro"

    retrieved = repo.get_by_name("AndroidExpert")
    assert retrieved is not None
    assert retrieved.name == "AndroidExpert"

    # 3. Activate
    repo.activate(m2.profile_id)
    active2 = repo.get_active()
    assert active2.name == "AndroidExpert"

    # 4. Rename
    success = repo.rename(m1.profile_id, "WebDevEnterprise")
    assert success is True
    renamed = repo.get_by_id(m1.profile_id)
    assert renamed.name == "WebDevEnterprise"

    # 5. List
    all_profiles = repo.list_all()
    assert len(all_profiles) == 2

    # 6. Delete
    repo.delete(m1.profile_id)
    assert repo.get_by_id(m1.profile_id) is None


def test_profile_version_history(in_memory_db):
    repo = ProfileRepository(in_memory_db)
    manifest = ProfileManifest(name="MLBuilder", version="1.0.0")
    repo.create(manifest, is_active=True)

    pkg = ProfilePackage(manifest=manifest, lessons=[], strategies=[])
    v1 = ProfileVersion(
        profile_id=manifest.profile_id,
        version="1.0.0",
        message="Initial checkpoint",
        manifest=manifest,
        package_data_json=pkg.model_dump_json(),
    )
    repo.add_version(v1)

    versions = repo.list_versions(manifest.profile_id)
    assert len(versions) == 1
    assert versions[0].version == "1.0.0"

    fetched = repo.get_version(manifest.profile_id, "1.0.0")
    assert fetched is not None
    assert fetched.message == "Initial checkpoint"


def test_experience_and_lesson_repository(in_memory_db):
    p_repo = ProfileRepository(in_memory_db)
    e_repo = ExperienceRepository(in_memory_db)
    l_repo = LessonRepository(in_memory_db)

    manifest = ProfileManifest(name="BackendPro", version="1.0.0")
    p_repo.create(manifest, is_active=True)

    # Experience save & query
    exp = ExperienceRecord(
        profile_id=manifest.profile_id,
        session_id="s-101",
        task_id="t-202",
        project_id="proj-alpha",
        domain="backend",
        languages=["python"],
        frameworks=["fastapi"],
        initial_problem="Database connection pool exhausted under concurrent load",
        outcome="success",
        verification=VerificationEvidence(
            verification_type="test",
            passed=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
        ),
    )
    e_repo.save(exp)
    assert e_repo.count_by_profile(manifest.profile_id) == 1

    fetched_exp = e_repo.get_by_id(exp.id)
    assert fetched_exp is not None
    assert fetched_exp.project_id == "proj-alpha"

    # Lesson save & query
    lesson = Lesson(
        profile_id=manifest.profile_id,
        title="FastAPI SQLAlchemy pool sizing",
        trigger_pattern="TimeoutError: QueuePool limit exceeded",
        recommended_strategy="Set pool_size=20, max_overflow=10 and recycle=1800",
        confidence=0.85,
        scope=KnowledgeScope.TECHNOLOGY,
    )
    l_repo.save(lesson)
    assert l_repo.count_by_profile(manifest.profile_id) == 1

    lessons = l_repo.list_by_profile(manifest.profile_id)
    assert len(lessons) == 1
    assert lessons[0].title == "FastAPI SQLAlchemy pool sizing"


def test_strategy_repository(in_memory_db):
    p_repo = ProfileRepository(in_memory_db)
    s_repo = StrategyRepository(in_memory_db)

    manifest = ProfileManifest(name="SecExpert", version="1.0.0")
    p_repo.create(manifest, is_active=True)

    # Record first success
    strat = s_repo.record_outcome(
        profile_id=manifest.profile_id,
        name="sanitize_inputs",
        category="security",
        outcome=StrategyOutcome.SUCCESS,
        duration_sec=2.5,
    )
    assert strat.attempts_count == 1
    assert strat.success_count == 1
    assert strat.bayesian_score > 0.6

    # Record regression
    strat2 = s_repo.record_outcome(
        profile_id=manifest.profile_id,
        name="sanitize_inputs",
        category="security",
        outcome=StrategyOutcome.REGRESSION,
        duration_sec=3.0,
    )
    assert strat2.attempts_count == 2
    assert strat2.regression_count == 1
    assert strat2.bayesian_score < strat.bayesian_score
