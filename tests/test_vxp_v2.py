"""Tests for portable experience profiles (.vxp v2) and backwards compatibility with legacy v1 archives."""

import json
from pathlib import Path
import zipfile
import pytest

from evodev.config import EvoDevConfig
from evodev.models.experience import KnowledgeScope, Lesson, StrategyRecord
from evodev.models.memory import MemoryCategory, MemoryItem
from evodev.models.profile import ProfileManifest, ProfilePackage
from evodev.models.skills import Skill
from evodev.profiles.format import ProfileArchiveFormat
from evodev.security.crypto import compute_sha256
from evodev.security.validator import MalformedProfileError


@pytest.fixture
def profile_package_v2():
    manifest = ProfileManifest(profile_id="p_v2", name="V2Profile", description="V2 profile with memories and skills")
    lessons = [
        Lesson(
            profile_id="p_v2",
            title="Async Postgres",
            trigger_pattern="database query",
            recommended_strategy="asyncpg connection pool",
        )
    ]
    memories = [
        MemoryItem(
            profile_id="p_v2",
            category=MemoryCategory.ARCHITECTURE,
            title="CQRS Event Sourcing",
            content={"read_db": "Redis", "write_db": "Postgres"},
            scope=KnowledgeScope.GLOBAL,
        )
    ]
    skills = [
        Skill(
            id="s1",
            profile_id="p_v2",
            name="Refactoring Skill",
            description="Extract method",
            category="refactoring",
            current_version="1.0.0",
        )
    ]
    return ProfilePackage(
        manifest=manifest,
        lessons=lessons,
        strategies=[],
        experiences=[],
        benchmarks=[],
        memories=memories,
        skills=skills,
    )


def test_vxp_v2_pack_and_unpack(tmp_path, profile_package_v2):
    vxp_path = tmp_path / "v2_test.vxp"
    archive_format = ProfileArchiveFormat()

    # Pack to .vxp
    archive_format.pack_to_vxp(profile_package_v2, vxp_path)
    assert vxp_path.is_file()

    # Unpack and verify
    unpacked = archive_format.unpack_from_vxp(vxp_path)
    assert unpacked.manifest.name == "V2Profile"
    assert len(unpacked.lessons) == 1
    assert len(unpacked.memories) == 1
    assert unpacked.memories[0].title == "CQRS Event Sourcing"
    assert len(unpacked.skills) == 1
    assert unpacked.skills[0].name == "Refactoring Skill"


def test_vxp_v1_legacy_backwards_compatibility(tmp_path):
    """Ensure older v1 .vxp archives without memories.json and skills.json unpack smoothly."""
    vxp_v1_path = tmp_path / "legacy_v1.vxp"
    archive_format = ProfileArchiveFormat()

    # Construct legacy v1 archive manually
    manifest_data = {
        "profile_id": "p_legacy",
        "name": "LegacyProfile",
        "version": "1.0.0",
        "description": "Old profile",
        "domains": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "author": "EvoDev",
        "schema_version": "1.0.0",
    }
    lessons_json = json.dumps([{
        "id": "l_old",
        "profile_id": "p_legacy",
        "title": "Legacy Lesson",
        "trigger_pattern": "old",
        "recommended_strategy": "old_strat",
        "anti_patterns": [],
        "scope": "global",
        "confidence": 1.0,
        "epistemic_type": "verified_fact",
        "verification_evidence": [],
        "provenance": {"origin_project_ids": [], "verification_count": 1, "failure_count": 0},
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "is_active": True,
    }], indent=2)
    strategies_json = "[]"
    preferences_json = "{}"
    benchmarks_json = "[]"

    # Compute legacy checksum according to format.py:
    combined_v1 = (lessons_json + strategies_json + preferences_json + benchmarks_json).encode("utf-8")
    legacy_checksum = compute_sha256(combined_v1)

    with zipfile.ZipFile(vxp_v1_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest_data, indent=2))
        zf.writestr("lessons.json", lessons_json)
        zf.writestr("strategies.json", strategies_json)
        zf.writestr("preferences.json", preferences_json)
        zf.writestr("benchmarks.json", benchmarks_json)
        zf.writestr("integrity.sha256", legacy_checksum)

    # Legacy v1 archive must unpack without raising MalformedProfileError
    unpacked = archive_format.unpack_from_vxp(vxp_v1_path)
    assert unpacked.manifest.name == "LegacyProfile"
    assert len(unpacked.lessons) == 1
    assert unpacked.memories == []
    assert unpacked.skills == []
