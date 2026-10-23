"""Unit tests for Phase 4: Portable Experience Profiles (.vxp lifecycle and rollback)."""

from pathlib import Path
import tempfile
import pytest

from evodev.config import EvoDevConfig
from evodev.models.experience import KnowledgeScope, Lesson, StrategyRecord
from evodev.profiles.manager import ProfileManager
from evodev.security.validator import MalformedProfileError
from evodev.storage.db import DatabaseManager
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    BenchmarkRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


@pytest.fixture
def profile_test_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        config = EvoDevConfig(data_dir=Path(temp_dir))
        db = DatabaseManager(config.db_path)
        migrator = MigrationManager(db)
        migrator.run_migrations()

        p_repo = ProfileRepository(db)
        l_repo = LessonRepository(db)
        s_repo = StrategyRepository(db)
        e_repo = ExperienceRepository(db)
        b_repo = BenchmarkRepository(db)

        mgr = ProfileManager(p_repo, l_repo, s_repo, e_repo, b_repo, config)
        try:
            yield mgr, p_repo, l_repo, s_repo, config
        finally:
            db.close()


def test_profile_creation_rename_duplicate(profile_test_env):
    mgr, p_repo, l_repo, _, _ = profile_test_env

    # 1. Create
    p1 = mgr.create_profile(
        name="AndroidExpert.vxp",
        description="Android production experience",
        domains=["mobile"],
        technologies=["kotlin", "compose"],
        activate=True,
    )
    assert p1.name == "AndroidExpert"
    assert mgr.get_active_profile().profile_id == p1.profile_id

    # Add a lesson
    lesson = Lesson(
        profile_id=p1.profile_id,
        title="Compose state pitfall",
        trigger_pattern="mutableStateOf",
        recommended_strategy="Wrap in remember",
        scope=KnowledgeScope.TECHNOLOGY,
    )
    l_repo.save(lesson)

    # 2. Rename
    mgr.rename_profile("AndroidExpert", "AndroidMastery")
    renamed = mgr.get_profile(p1.profile_id)
    assert renamed.name == "AndroidMastery"

    # 3. Duplicate
    p2 = mgr.duplicate_profile("AndroidMastery", "AndroidMasteryCopy")
    assert p2.name == "AndroidMasteryCopy"
    copy_lessons = l_repo.list_by_profile(p2.profile_id)
    assert len(copy_lessons) == 1
    assert copy_lessons[0].title == "Compose state pitfall"
    assert copy_lessons[0].id != lesson.id  # New ID assigned


def test_export_and_import_into_fresh_database(profile_test_env):
    mgr1, _, l_repo1, s_repo1, config = profile_test_env

    # Populate profile in original environment
    p = mgr1.create_profile(name="WebDevPro", domains=["web"], technologies=["react"])
    l1 = Lesson(
        profile_id=p.profile_id,
        title="React 19 Form Action",
        trigger_pattern="Form submission state",
        recommended_strategy="Use useActionState",
        scope=KnowledgeScope.TECHNOLOGY,
    )
    l_repo1.save(l1)

    s1 = StrategyRecord(
        profile_id=p.profile_id,
        name="useActionState",
        category="web",
        attempts_count=5,
        success_count=5,
        bayesian_score=0.85,
    )
    s_repo1.save(s1)

    # Export to .vxp file
    export_path = mgr1.export_profile("WebDevPro")
    assert export_path.is_file()
    assert export_path.name == "WebDevPro.vxp"

    # Now create a COMPLETELY FRESH database environment (Simulates new machine)
    with tempfile.TemporaryDirectory() as fresh_dir:
        fresh_config = EvoDevConfig(data_dir=Path(fresh_dir))
        fresh_db = DatabaseManager(fresh_config.db_path)
        MigrationManager(fresh_db).run_migrations()

        fresh_p_repo = ProfileRepository(fresh_db)
        fresh_l_repo = LessonRepository(fresh_db)
        fresh_s_repo = StrategyRepository(fresh_db)
        fresh_e_repo = ExperienceRepository(fresh_db)

        fresh_mgr = ProfileManager(
            fresh_p_repo,
            fresh_l_repo,
            fresh_s_repo,
            fresh_e_repo,
            config=fresh_config,
        )

        try:
            # Confirm fresh database starts empty
            assert len(fresh_mgr.list_profiles()) == 0

            # Import the .vxp file
            imported_manifest = fresh_mgr.import_profile(export_path, activate_on_import=True)
            assert imported_manifest.name == "WebDevPro"
            assert fresh_mgr.get_active_profile().profile_id == imported_manifest.profile_id

            # Verify restored lessons and strategies
            imported_lessons = fresh_l_repo.list_by_profile(imported_manifest.profile_id)
            assert len(imported_lessons) == 1
            assert imported_lessons[0].title == "React 19 Form Action"

            imported_strategies = fresh_s_repo.list_by_profile(imported_manifest.profile_id)
            assert len(imported_strategies) == 1
            assert imported_strategies[0].name == "useActionState"
            assert imported_strategies[0].success_count == 5
        finally:
            fresh_db.close()


def test_encrypted_profile_export_and_import(profile_test_env):
    mgr, _, l_repo, _, _ = profile_test_env

    p = mgr.create_profile(name="EncryptedSecProfile", domains=["security"])
    l = Lesson(
        profile_id=p.profile_id,
        title="Sanitize SQL inputs",
        trigger_pattern="SQL injection risk",
        recommended_strategy="Use parameterized queries",
    )
    l_repo.save(l)

    # Export with password
    password = "SuperSecretPassword123!"
    vxp_path = mgr.export_profile("EncryptedSecProfile", password=password)
    assert vxp_path.is_file()

    # Attempting to unpack without password fails
    with pytest.raises(Exception):
        mgr.archive_format.unpack_from_vxp(vxp_path, password=None)

    # Unpack with wrong password fails
    with pytest.raises(Exception):
        mgr.archive_format.unpack_from_vxp(vxp_path, password="WrongPassword")

    # Unpack with correct password succeeds
    pkg = mgr.archive_format.unpack_from_vxp(vxp_path, password=password)
    assert pkg.manifest.name == "EncryptedSecProfile"
    assert len(pkg.lessons) == 1


def test_versioning_and_rollback(profile_test_env):
    mgr, _, l_repo, _, _ = profile_test_env

    # 1. Initial Profile State (Version 1.0.1)
    p = mgr.create_profile(name="MLBuilder", domains=["ml"])
    l1 = Lesson(
        profile_id=p.profile_id,
        title="PyTorch CUDA out of memory",
        trigger_pattern="CUDA out of memory",
        recommended_strategy="Use torch.cuda.empty_cache() and reduce batch_size",
    )
    l_repo.save(l1)
    v1 = mgr.create_version(p.profile_id, message="Baseline V1 with 1 lesson")
    assert v1.version == "1.0.1"

    # 2. Add bad/experimental lesson and create Version 1.0.2
    l2 = Lesson(
        profile_id=p.profile_id,
        title="Experimental quantization",
        trigger_pattern="Quantization error",
        recommended_strategy="Force float16 without calibration",
    )
    l_repo.save(l2)
    assert len(l_repo.list_by_profile(p.profile_id)) == 2

    v2 = mgr.create_version(p.profile_id, message="Added experimental quantization")
    assert v2.version == "1.0.2"

    # 3. Check version history
    history = mgr.list_versions(p.profile_id)
    assert len(history) == 2
    assert history[0].version == "1.0.2"
    assert history[1].version == "1.0.1"

    # 4. Rollback to V1
    rolled_back_profile = mgr.rollback_version(p.profile_id, "1.0.1")
    assert rolled_back_profile.version == "1.0.1"

    # Verify lessons rolled back to original state (l2 is gone!)
    restored_lessons = l_repo.list_by_profile(p.profile_id)
    assert len(restored_lessons) == 1
    assert restored_lessons[0].title == "PyTorch CUDA out of memory"
