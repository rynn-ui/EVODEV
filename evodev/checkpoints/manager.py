"""Manager coordinating safe Git diff snapshots, SQLite database backups, and profile versions."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional
import uuid

from evodev.config import EvoDevConfig, load_config
from evodev.models.checkpoints import CheckpointRecord, CheckpointType
from evodev.profiles.manager import ProfileManager
from evodev.storage.db import DatabaseManager, close_db
from evodev.storage.repositories import CheckpointRepository

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Creates reviewable, non-destructive checkpoints and orchestrates safe rollback."""

    def __init__(
        self,
        checkpoint_repo: CheckpointRepository,
        config: Optional[EvoDevConfig] = None,
        db: Optional[DatabaseManager] = None,
        profile_manager: Optional[ProfileManager] = None,
    ):
        self.repo = checkpoint_repo
        self.config = config or load_config()
        self.db = db
        self.profile_manager = profile_manager

    def create_git_checkpoint(self, summary: str, repo_path: Optional[Path] = None) -> CheckpointRecord:
        """Capture reviewable Git status, modified files, and diff without resetting user working state."""
        cwd = Path(repo_path or Path.cwd()).resolve()

        status_text = ""
        diff_text = ""
        affected_files: List[str] = []
        is_git = False
        commit_hash = "HEAD"

        try:
            # Check if directory is inside a Git repository
            check_git = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if check_git.returncode == 0:
                is_git = True
                # Get current commit hash
                c_run = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                commit_hash = c_run.stdout.strip() if c_run.stdout else "unknown"

                # Get status porcelain
                s_run = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                status_text = s_run.stdout or ""
                for line in status_text.splitlines():
                    if len(line) > 3:
                        affected_files.append(line[3:].strip())

                # Get diff of tracked files
                d_run = subprocess.run(
                    ["git", "diff", "HEAD"],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                diff_text = d_run.stdout or ""
        except Exception as e:
            logger.warning(f"Git inspection failed: {e}")
            status_text = f"Git inspection unavailable: {e}"
            diff_text = ""

        record = CheckpointRecord(
            checkpoint_type=CheckpointType.GIT,
            reference=f"git:{commit_hash}",
            summary=summary,
            details={
                "is_git_repo": is_git,
                "commit_hash": commit_hash,
                "affected_files": affected_files,
                "status_output": status_text,
                "diff_snippet": diff_text[:10000],  # Bound size
                "total_diff_bytes": len(diff_text),
                "cwd": str(cwd),
            },
        )
        return self.repo.create(record)

    def create_database_checkpoint(self, summary: str) -> CheckpointRecord:
        """Create a timestamped SQLite database copy for recovery of EvoDev-managed state."""
        checkpoints_dir = self.config.data_dir / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"evodev_db_{timestamp_str}_{uuid.uuid4().hex[:6]}.db"
        backup_path = checkpoints_dir / backup_name

        db_path = self.config.db_path
        if db_path.is_file():
            # Flush WAL if active and copy file safely
            try:
                if self.db:
                    with self.db.session() as conn:
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except Exception as e:
                logger.warning(f"Database checkpoint PRAGMA failed: {e}")

            shutil.copy2(db_path, backup_path)
            file_size = backup_path.stat().st_size
        else:
            file_size = 0

        record = CheckpointRecord(
            checkpoint_type=CheckpointType.DATABASE,
            reference=str(backup_path),
            summary=summary,
            details={
                "backup_path": str(backup_path),
                "original_db_path": str(db_path),
                "file_size_bytes": file_size,
            },
        )
        return self.repo.create(record)

    def create_profile_checkpoint(self, profile_id: str, summary: str) -> CheckpointRecord:
        """Create a version checkpoint for an experience profile."""
        if not self.profile_manager:
            raise ValueError("ProfileManager required to create a profile checkpoint.")

        version_obj = self.profile_manager.create_version(profile_id, message=summary)

        record = CheckpointRecord(
            checkpoint_type=CheckpointType.PROFILE,
            reference=f"profile:{profile_id}:v{version_obj.version}",
            summary=summary,
            details={
                "profile_id": profile_id,
                "version": version_obj.version,
                "created_at": version_obj.created_at.isoformat(),
            },
        )
        return self.repo.create(record)

    def list_checkpoints(
        self,
        checkpoint_type: Optional[CheckpointType] = None,
        limit: int = 50,
    ) -> List[CheckpointRecord]:
        """List historical checkpoints."""
        return self.repo.list_checkpoints(checkpoint_type=checkpoint_type, limit=limit)

    def rollback_database_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore the SQLite database from a checkpoint backup file."""
        record = self.repo.get_by_id(checkpoint_id)
        if not record or record.checkpoint_type != CheckpointType.DATABASE:
            raise ValueError(f"Valid database checkpoint not found: {checkpoint_id}")

        backup_path = Path(record.details.get("backup_path", record.reference))
        if not backup_path.is_file():
            raise FileNotFoundError(f"Database backup file missing: {backup_path}")

        close_db()

        target_db = self.config.db_path
        target_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, target_db)

        # Remove stale WAL/SHM sidecars
        wal = target_db.with_name(f"{target_db.name}-wal")
        shm = target_db.with_name(f"{target_db.name}-shm")
        if wal.exists():
            wal.unlink()
        if shm.exists():
            shm.unlink()

        return True
