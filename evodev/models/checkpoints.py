"""Checkpoint data models for Git, database, and profile version snapshots."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class CheckpointType(str, Enum):
    """Domain boundaries for non-destructive checkpoints."""

    GIT = "git"  # Working directory / Git uncommitted changes snapshot
    DATABASE = "database"  # SQLite database snapshot / savepoint
    PROFILE = "profile"  # .vxp experience profile version snapshot


class CheckpointRecord(BaseModel):
    """An audit record for a safe, reviewable checkpoint."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    checkpoint_type: CheckpointType
    reference: str = Field(description="Git ref/stash tag, DB snapshot file, or profile version")
    summary: str = Field(description="Human readable explanation of why this checkpoint was created")
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed metadata (affected files, modified line counts, diffs, backup paths)",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
