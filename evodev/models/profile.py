"""Profile manifest, package, and versioning data models."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from evodev.models.experience import Lesson, StrategyRecord
from evodev.models.memory import MemoryItem
from evodev.models.skills import Skill


class ProfileStats(BaseModel):
    """Aggregate statistics for an experience profile."""

    total_lessons: int = 0
    total_strategies: int = 0
    total_experiences: int = 0
    verified_lessons_count: int = 0
    total_benchmarks: int = 0
    total_memories: int = 0
    total_skills: int = 0


class ProfileManifest(BaseModel):
    """Metadata manifest describing an experience profile (.vxp)."""

    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(description="User-defined profile name, e.g. AndroidExpert.vxp")
    version: str = Field(default="1.0.0", description="Semantic profile version")
    description: str = Field(default="Accumulated EvoDev experience profile")
    author: str = Field(default="ryn")
    schema_version: str = Field(default="2.0.0")
    domains: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stats: ProfileStats = Field(default_factory=ProfileStats)
    payload_checksum: Optional[str] = Field(
        default=None, description="SHA-256 integrity hash of payload content"
    )


class ProfilePackage(BaseModel):
    """Complete in-memory payload of an experience profile archive."""

    manifest: ProfileManifest
    lessons: List[Lesson] = Field(default_factory=list)
    strategies: List[StrategyRecord] = Field(default_factory=list)
    preferences: Dict[str, Any] = Field(default_factory=dict)
    benchmarks: List[Dict[str, Any]] = Field(default_factory=list)
    memories: List[MemoryItem] = Field(default_factory=list)
    skills: List[Skill] = Field(default_factory=list)


class ProfileVersion(BaseModel):
    """Immutable checkpoint of a profile for version history and rollback."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile_id: str
    version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str = "Automated checkpoint"
    manifest: ProfileManifest
    package_data_json: str  # Serialized ProfilePackage for fast rollback


class ProfileExportMeta(BaseModel):
    """Export container metadata."""

    exported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evodev_version: str = "1.0.0"
    is_encrypted: bool = False
    checksum: str
