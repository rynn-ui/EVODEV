"""Archive format handler for packing and unpacking .vxp portable profile files."""

import io
import json
from pathlib import Path
from typing import Optional
import zipfile

from evodev.config import EvoDevConfig, load_config
from evodev.models.experience import Lesson, StrategyRecord
from evodev.models.memory import MemoryItem
from evodev.models.profile import ProfileManifest, ProfilePackage
from evodev.models.skills import Skill
from evodev.security.crypto import (
    compute_sha256,
    decrypt_payload,
    encrypt_payload,
)
from evodev.security.validator import (
    MalformedProfileError,
    ProfileValidator,
    ValidationError,
)


class ProfileArchiveFormat:
    """Handles serialization, compression, integrity checking, and encryption of .vxp files."""

    def __init__(self, config: Optional[EvoDevConfig] = None):
        self.config = config or load_config()
        self.validator = ProfileValidator(self.config)

    def pack_to_vxp(
        self,
        package: ProfilePackage,
        output_path: Path,
        password: Optional[str] = None,
    ) -> Path:
        """Serialize a ProfilePackage into a .vxp archive file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Prepare JSON payloads
        lessons_data = json.dumps([l.model_dump(mode="json") for l in package.lessons], indent=2)
        strategies_data = json.dumps(
            [s.model_dump(mode="json") for s in package.strategies], indent=2
        )
        preferences_data = json.dumps(package.preferences, indent=2)
        benchmarks_data = json.dumps(package.benchmarks, indent=2)

        memories_data = json.dumps([m.model_dump(mode="json") for m in package.memories], indent=2)
        skills_data = json.dumps([s.model_dump(mode="json") for s in package.skills], indent=2)

        # 2. Compute canonical integrity checksum over payload data
        combined_payload = (
            lessons_data + strategies_data + preferences_data + benchmarks_data + memories_data + skills_data
        ).encode("utf-8")
        checksum = compute_sha256(combined_payload)

        # 3. Update manifest
        package.manifest.payload_checksum = checksum
        package.manifest.stats.total_lessons = len(package.lessons)
        package.manifest.stats.total_strategies = len(package.strategies)
        package.manifest.stats.verified_lessons_count = sum(
            1 for l in package.lessons if l.evidence and any(e.passed for e in l.evidence)
        )
        package.manifest.stats.total_benchmarks = len(package.benchmarks)
        package.manifest.stats.total_memories = len(package.memories)
        package.manifest.stats.total_skills = len(package.skills)
        manifest_data = package.manifest.model_dump_json(indent=2)

        # 4. Pack into in-memory ZIP archive
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", manifest_data)
            zf.writestr("lessons.json", lessons_data)
            zf.writestr("strategies.json", strategies_data)
            zf.writestr("preferences.json", preferences_data)
            zf.writestr("benchmarks.json", benchmarks_data)
            zf.writestr("memories.json", memories_data)
            zf.writestr("skills.json", skills_data)
            zf.writestr("integrity.sha256", checksum)

        zip_bytes = zip_buf.getvalue()

        # 5. Apply optional AES-256-GCM encryption
        if password:
            final_bytes = encrypt_payload(zip_bytes, password)
        else:
            final_bytes = zip_bytes

        # 6. Write to disk
        with open(output_path, "wb") as f:
            f.write(final_bytes)

        return output_path

    def unpack_from_vxp(
        self,
        vxp_path: Path,
        password: Optional[str] = None,
    ) -> ProfilePackage:
        """Read and validate a .vxp archive file, returning a validated ProfilePackage."""
        vxp_path = Path(vxp_path)
        if not vxp_path.is_file():
            raise FileNotFoundError(f"Experience profile archive not found: {vxp_path}")

        with open(vxp_path, "rb") as f:
            raw_bytes = f.read()

        # Decrypt if password provided or payload starts with salt header (not standard PK\x03\x04)
        is_zip = raw_bytes.startswith(b"PK\x03\x04")
        if not is_zip or password:
            if not password:
                raise MalformedProfileError("Profile appears encrypted or malformed. Password required.")
            raw_bytes = decrypt_payload(raw_bytes, password)

        # Parse zip
        zip_buf = io.BytesIO(raw_bytes)
        try:
            with zipfile.ZipFile(zip_buf, "r") as zf:
                # 1. Enforce safety checks (Zip Slip, Zip Bomb)
                self.validator.validate_archive_safety(zf)

                # 2. Check required files
                namelist = set(zf.namelist())
                required = {"manifest.json", "lessons.json", "strategies.json", "integrity.sha256"}
                if not required.issubset(namelist):
                    missing = required - namelist
                    raise MalformedProfileError(f"Missing required archive members: {missing}")

                # 3. Read members
                manifest_json = zf.read("manifest.json").decode("utf-8")
                lessons_json = zf.read("lessons.json").decode("utf-8")
                strategies_json = zf.read("strategies.json").decode("utf-8")
                preferences_json = (
                    zf.read("preferences.json").decode("utf-8")
                    if "preferences.json" in namelist
                    else "{}"
                )
                benchmarks_json = (
                    zf.read("benchmarks.json").decode("utf-8")
                    if "benchmarks.json" in namelist
                    else "[]"
                )
                memories_json = (
                    zf.read("memories.json").decode("utf-8")
                    if "memories.json" in namelist
                    else "[]"
                )
                skills_json = (
                    zf.read("skills.json").decode("utf-8")
                    if "skills.json" in namelist
                    else "[]"
                )
                expected_checksum = zf.read("integrity.sha256").decode("utf-8").strip()

                # 4. Verify cryptographic integrity checksum (supports v2 and legacy v1)
                combined_v2 = (
                    lessons_json + strategies_json + preferences_json + benchmarks_json + memories_json + skills_json
                ).encode("utf-8")
                combined_v1 = (
                    lessons_json + strategies_json + preferences_json + benchmarks_json
                ).encode("utf-8")
                checksum_v2 = compute_sha256(combined_v2)
                checksum_v1 = compute_sha256(combined_v1)

                if expected_checksum not in (checksum_v2, checksum_v1):
                    raise MalformedProfileError(
                        f"Integrity digest verification failed! Archive may have been tampered with. Expected {expected_checksum}, calculated {checksum_v2}."
                    )

                # 5. Parse typed data models
                manifest = ProfileManifest.model_validate_json(manifest_json)
                lessons_raw = json.loads(lessons_json)
                strategies_raw = json.loads(strategies_json)
                preferences = json.loads(preferences_json)
                benchmarks = json.loads(benchmarks_json)
                memories_raw = json.loads(memories_json)
                skills_raw = json.loads(skills_json)

                lessons = [Lesson.model_validate(l) for l in lessons_raw]
                strategies = [StrategyRecord.model_validate(s) for s in strategies_raw]
                memories = [MemoryItem.model_validate(m) for m in memories_raw]
                skills = [Skill.model_validate(s) for s in skills_raw]

                return ProfilePackage(
                    manifest=manifest,
                    lessons=lessons,
                    strategies=strategies,
                    preferences=preferences,
                    benchmarks=benchmarks,
                    memories=memories,
                    skills=skills,
                )

        except zipfile.BadZipFile as e:
            raise MalformedProfileError(f"Invalid or corrupted .vxp archive: {e}")
