"""Profile lifecycle manager: create, rename, duplicate, export, import, rollback, and activate."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import List, Optional
import uuid

from evodev.config import EvoDevConfig, load_config
from evodev.models.profile import (
    ProfileManifest,
    ProfilePackage,
    ProfileStats,
    ProfileVersion,
)
from evodev.profiles.format import ProfileArchiveFormat
from evodev.storage.repositories import (
    BenchmarkRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


class ProfileManager:
    """Manages the lifecycle, versioning, export, and activation of experience profiles."""

    def __init__(
        self,
        profile_repo: ProfileRepository,
        lesson_repo: LessonRepository,
        strategy_repo: StrategyRepository,
        experience_repo: ExperienceRepository,
        benchmark_repo: Optional[BenchmarkRepository] = None,
        config: Optional[EvoDevConfig] = None,
    ):
        self.profile_repo = profile_repo
        self.lesson_repo = lesson_repo
        self.strategy_repo = strategy_repo
        self.experience_repo = experience_repo
        self.benchmark_repo = benchmark_repo
        self.config = config or load_config()
        self.archive_format = ProfileArchiveFormat(self.config)

    def _resolve_profile(self, identifier: str) -> Optional[ProfileManifest]:
        """Lookup by ID first, then by name."""
        return self.profile_repo.get_by_id(identifier) or self.profile_repo.get_by_name(identifier)

    def create_profile(
        self,
        name: str,
        description: str = "",
        domains: Optional[List[str]] = None,
        technologies: Optional[List[str]] = None,
        activate: bool = False,
    ) -> ProfileManifest:
        """Create a new experience profile."""
        clean_name = name.removesuffix(".vxp")
        manifest = ProfileManifest(
            profile_id=str(uuid.uuid4()),
            name=clean_name,
            version="1.0.0",
            description=description or f"Experience profile for {clean_name}",
            domains=domains or [],
            technologies=technologies or [],
            stats=ProfileStats(),
        )
        self.profile_repo.create(manifest, is_active=activate)
        return manifest

    def rename_profile(self, identifier: str, new_name: str) -> bool:
        """Rename an existing profile."""
        profile = self._resolve_profile(identifier)
        if not profile:
            return False
        clean_name = new_name.removesuffix(".vxp")
        return self.profile_repo.rename(profile.profile_id, clean_name)

    def duplicate_profile(self, source_id_or_name: str, new_name: str) -> ProfileManifest:
        """Create an exact copy of an experience profile with a new identity."""
        source = self._resolve_profile(source_id_or_name)
        if not source:
            raise ValueError(f"Source profile not found: {source_id_or_name}")

        new_manifest = self.create_profile(
            name=new_name,
            description=f"Duplicate of {source.name}: {source.description}",
            domains=list(source.domains),
            technologies=list(source.technologies),
            activate=False,
        )

        # Duplicate lessons
        lessons = self.lesson_repo.list_by_profile(source.profile_id, active_only=False)
        for l in lessons:
            l_copy = l.model_copy(
                update={"id": str(uuid.uuid4()), "profile_id": new_manifest.profile_id}
            )
            self.lesson_repo.save(l_copy)

        # Duplicate strategies
        strategies = self.strategy_repo.list_by_profile(source.profile_id)
        for s in strategies:
            s_copy = s.model_copy(
                update={"id": str(uuid.uuid4()), "profile_id": new_manifest.profile_id}
            )
            self.strategy_repo.save(s_copy)

        return new_manifest

    def delete_profile(self, identifier: str) -> bool:
        """Delete profile and cascade delete all associated lessons and experiences."""
        profile = self._resolve_profile(identifier)
        if not profile:
            return False
        return self.profile_repo.delete(profile.profile_id)

    def list_profiles(self) -> List[ProfileManifest]:
        """List all available profiles."""
        return self.profile_repo.list_all()

    def get_profile(self, identifier: str) -> Optional[ProfileManifest]:
        """Retrieve profile by ID or name."""
        return self._resolve_profile(identifier)

    def get_active_profile(self) -> Optional[ProfileManifest]:
        """Retrieve the currently active profile."""
        return self.profile_repo.get_active()

    def activate_profile(self, identifier: str) -> bool:
        """Activate profile by ID or name."""
        profile = self._resolve_profile(identifier)
        if not profile:
            return False
        return self.profile_repo.activate(profile.profile_id)

    def deactivate_profile(self) -> None:
        """Deactivate all profiles."""
        self.profile_repo.deactivate_all()

    def export_profile(
        self,
        identifier: str,
        output_path: Optional[Path] = None,
        password: Optional[str] = None,
    ) -> Path:
        """Package a profile into a portable .vxp archive file."""
        profile = self._resolve_profile(identifier)
        if not profile:
            raise ValueError(f"Profile not found: {identifier}")

        lessons = self.lesson_repo.list_by_profile(profile.profile_id, active_only=True)
        strategies = self.strategy_repo.list_by_profile(profile.profile_id)
        benchmarks = (
            self.benchmark_repo.get_metrics(profile.profile_id) if self.benchmark_repo else []
        )

        package = ProfilePackage(
            manifest=profile,
            lessons=lessons,
            strategies=strategies,
            preferences={"exported_at": datetime.now(timezone.utc).isoformat()},
            benchmarks=benchmarks,
        )

        target_file = (
            output_path or (self.config.exports_dir / f"{profile.name}.vxp")
        )
        return self.archive_format.pack_to_vxp(package, target_file, password=password)

    def import_profile(
        self,
        vxp_path: Path,
        activate_on_import: bool = False,
        password: Optional[str] = None,
        custom_name: Optional[str] = None,
    ) -> ProfileManifest:
        """Import a .vxp archive, populating database tables with verified experiences."""
        package = self.archive_format.unpack_from_vxp(vxp_path, password=password)

        manifest = package.manifest
        if custom_name:
            manifest.name = custom_name.removesuffix(".vxp")

        # Check if profile with this name already exists; if so, generate unique name or update
        existing = self.profile_repo.get_by_name(manifest.name)
        if existing:
            manifest.name = f"{manifest.name}-{uuid.uuid4().hex[:4]}"

        # Save profile manifest
        self.profile_repo.create(manifest, is_active=activate_on_import)

        # Save imported lessons (update profile_id to match newly inserted profile)
        for lesson in package.lessons:
            lesson.profile_id = manifest.profile_id
            self.lesson_repo.save(lesson)

        # Save imported strategies
        for strategy in package.strategies:
            strategy.profile_id = manifest.profile_id
            self.strategy_repo.save(strategy)

        # Save initial checkpoint version
        self.create_version(manifest.profile_id, message="Imported from .vxp archive")

        return manifest

    def create_version(self, identifier: str, message: str = "") -> ProfileVersion:
        """Create an immutable checkpoint of current profile state for rollback."""
        profile = self._resolve_profile(identifier)
        if not profile:
            raise ValueError(f"Profile not found: {identifier}")

        lessons = self.lesson_repo.list_by_profile(profile.profile_id, active_only=False)
        strategies = self.strategy_repo.list_by_profile(profile.profile_id)
        benchmarks = (
            self.benchmark_repo.get_metrics(profile.profile_id) if self.benchmark_repo else []
        )

        package = ProfilePackage(
            manifest=profile,
            lessons=lessons,
            strategies=strategies,
            preferences={},
            benchmarks=benchmarks,
        )

        # Calculate incremental version string (e.g. 1.0.0 -> 1.0.1)
        versions = self.profile_repo.list_versions(profile.profile_id)
        ver_num = len(versions) + 1
        new_version_str = f"1.0.{ver_num}"

        version_checkpoint = ProfileVersion(
            id=str(uuid.uuid4()),
            profile_id=profile.profile_id,
            version=new_version_str,
            created_at=datetime.now(timezone.utc),
            message=message or f"Checkpoint {new_version_str}",
            manifest=profile,
            package_data_json=package.model_dump_json(),
        )

        self.profile_repo.add_version(version_checkpoint)
        return version_checkpoint

    def list_versions(self, identifier: str) -> List[ProfileVersion]:
        """Fetch version history for a profile."""
        profile = self._resolve_profile(identifier)
        if not profile:
            return []
        return self.profile_repo.list_versions(profile.profile_id)

    def rollback_version(self, identifier: str, version_str: str) -> ProfileManifest:
        """Roll back a profile's lessons and strategies to an earlier checkpoint."""
        profile = self._resolve_profile(identifier)
        if not profile:
            raise ValueError(f"Profile not found: {identifier}")

        version_record = self.profile_repo.get_version(profile.profile_id, version_str)
        if not version_record:
            raise ValueError(f"Version {version_str} not found for profile {profile.name}")

        package = ProfilePackage.model_validate_json(version_record.package_data_json)

        # Purge current lessons and strategies for this profile
        current_lessons = self.lesson_repo.list_by_profile(profile.profile_id, active_only=False)
        for l in current_lessons:
            self.lesson_repo.delete(l.id)

        # Re-insert snapshot lessons and strategies
        for lesson in package.lessons:
            lesson.profile_id = profile.profile_id
            self.lesson_repo.save(lesson)

        for strat in package.strategies:
            strat.profile_id = profile.profile_id
            self.strategy_repo.save(strat)

        # Update profile manifest version
        profile.version = version_str
        profile.updated_at = datetime.now(timezone.utc)
        self.profile_repo.update_manifest(profile)

        return profile
