"""Tests for safe checkpoints (Git, SQLite database, and Profile versions) and safe rollback."""

from pathlib import Path
import pytest

from evodev.checkpoints.manager import CheckpointManager
from evodev.config import EvoDevConfig
from evodev.models.checkpoints import CheckpointType
from evodev.models.profile import ProfileManifest
from evodev.profiles.manager import ProfileManager
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    BenchmarkRepository,
    CheckpointRepository,
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


@pytest.fixture
def checkpoints_setup(tmp_path):
    config = EvoDevConfig(data_dir=tmp_path / "data")
    config.ensure_directories()
    db = get_db(config)
    MigrationManager(db).run_migrations()

    cp_repo = CheckpointRepository(db)
    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    s_repo = StrategyRepository(db)
    e_repo = ExperienceRepository(db)
    b_repo = BenchmarkRepository(db)

    p_repo.create(ProfileManifest(profile_id="p1", name="TestProfile"), is_active=True)

    pm = ProfileManager(p_repo, l_repo, s_repo, e_repo, b_repo, config)
    mgr = CheckpointManager(cp_repo, config, db, pm)
    return mgr, cp_repo, config, db, p_repo


def test_git_checkpoint_inspection(checkpoints_setup):
    mgr, cp_repo, _, _, _ = checkpoints_setup

    # Create Git checkpoint in current repo directory
    cp = mgr.create_git_checkpoint("Pre-refactor Git checkpoint", repo_path=Path("."))

    assert cp.id is not None
    assert cp.checkpoint_type == CheckpointType.GIT
    assert "git:" in cp.reference
    assert "affected_files" in cp.details
    assert "status_output" in cp.details


def test_database_checkpoint_and_rollback(checkpoints_setup):
    mgr, cp_repo, config, db, p_repo = checkpoints_setup

    # State before change
    assert p_repo.get_by_id("p1") is not None
    assert p_repo.get_by_id("p2") is None

    # Create DB checkpoint
    cp = mgr.create_database_checkpoint("Baseline DB snapshot")
    assert cp.checkpoint_type == CheckpointType.DATABASE
    backup_file = Path(cp.details["backup_path"])
    assert backup_file.is_file()

    # Make modifying change
    p_repo.create(ProfileManifest(profile_id="p2", name="SecondProfile"))
    assert p_repo.get_by_id("p2") is not None

    # Rollback to checkpoint
    ok = mgr.rollback_database_checkpoint(cp.id)
    assert ok is True

    # Reopen DB to inspect restored state
    new_db = get_db(config)
    new_p_repo = ProfileRepository(new_db)
    assert new_p_repo.get_by_id("p1") is not None
    assert new_p_repo.get_by_id("p2") is None  # Rollback successfully restored baseline


def test_profile_version_checkpoint(checkpoints_setup):
    mgr, cp_repo, _, _, _ = checkpoints_setup

    cp = mgr.create_profile_checkpoint("p1", "Profile v1.0.0 snapshot")
    assert cp.checkpoint_type == CheckpointType.PROFILE
    assert "profile:p1" in cp.reference
