"""Unit and integration tests for Experience Inspector and Profile Analytics."""

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import zipfile

from fastapi.testclient import TestClient
import pytest

from evodev.api.server import create_api_app
from evodev.config import EvoDevConfig, set_config
from evodev.models.experience import (
    EpistemicType,
    ExperienceRecord,
    KnowledgeScope,
    Lesson,
    Provenance,
    StrategyOutcome,
    StrategyRecord,
    VerificationEvidence,
)
from evodev.models.profile import ProfileManifest, ProfilePackage
from evodev.profiles.format import ProfileArchiveFormat
from evodev.profiles.inspector import ProfileInspector
from evodev.profiles.manager import ProfileManager
from evodev.security.crypto import compute_sha256, encrypt_payload
from evodev.storage.db import DatabaseManager, close_db, set_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import (
    BenchmarkRepository,
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


@pytest.fixture
def inspector_env():
    """Isolated test environment with database, repositories, and ProfileInspector."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config = EvoDevConfig(data_dir=Path(temp_dir))
        set_config(config)
        db = DatabaseManager(config.db_path)
        set_db(db)
        MigrationManager(db).run_migrations()

        p_repo = ProfileRepository(db)
        l_repo = LessonRepository(db)
        s_repo = StrategyRepository(db)
        e_repo = ExperienceRepository(db)
        b_repo = BenchmarkRepository(db)
        ev_repo = EventRepository(db)

        mgr = ProfileManager(p_repo, l_repo, s_repo, e_repo, b_repo, config)
        inspector = ProfileInspector(p_repo, l_repo, s_repo, e_repo, b_repo, ev_repo, config)

        try:
            yield inspector, mgr, p_repo, l_repo, s_repo, e_repo, b_repo, config
        finally:
            close_db()


def test_archive_analysis_valid_vxp(inspector_env):
    """Test reading real .vxp archive and enumerating entries, sizes, and integrity."""
    inspector, mgr, p_repo, l_repo, s_repo, _, b_repo, config = inspector_env

    # 1. Create a populated profile
    profile = mgr.create_profile(
        name="AndroidMastery",
        description="Android production lessons",
        domains=["mobile"],
        technologies=["kotlin", "compose"],
        activate=True,
    )

    lesson = Lesson(
        profile_id=profile.profile_id,
        title="Wrap mutableStateOf in remember",
        trigger_pattern="mutableStateOf recomposition",
        recommended_strategy="Wrap with remember { mutableStateOf(...) }",
        scope=KnowledgeScope.TECHNOLOGY,
        evidence=[VerificationEvidence(verification_type="test", passed=True, total_tests=5, passed_tests=5)],
    )
    l_repo.save(lesson)

    strat = StrategyRecord(
        profile_id=profile.profile_id,
        name="rememberMutableState",
        category="mobile",
        attempts_count=8,
        success_count=7,
        bayesian_score=0.82,
    )
    s_repo.save(strat)

    b_repo.save_metric(profile.profile_id, "standard_suite", "success_rate", 0.95, {"passed": 19, "total": 20})

    # 2. Export to real .vxp archive file
    vxp_path = mgr.export_profile("AndroidMastery")
    assert vxp_path.is_file()

    # 3. Inspect archive
    result = inspector.inspect_archive(vxp_path)

    assert result.is_valid_zip is True
    assert result.is_encrypted is False
    assert result.is_corrupt is False
    assert result.is_unsupported_version is False
    assert result.integrity_verified is True
    assert result.integrity_checksum_expected is not None
    assert result.integrity_checksum_expected == result.integrity_checksum_calculated
    assert result.file_size_bytes > 0
    assert result.total_uncompressed_bytes > 0
    assert result.overall_compression_ratio_pct > 0.0

    # Verify real member entries
    entry_names = {e.name for e in result.entries}
    expected_members = {"manifest.json", "lessons.json", "strategies.json", "preferences.json", "benchmarks.json", "integrity.sha256"}
    assert expected_members.issubset(entry_names)

    lessons_entry = next(e for e in result.entries if e.name == "lessons.json")
    assert lessons_entry.record_count == 1
    assert lessons_entry.uncompressed_bytes > 0
    assert lessons_entry.compressed_bytes > 0

    strats_entry = next(e for e in result.entries if e.name == "strategies.json")
    assert strats_entry.record_count == 1

    benchmarks_entry = next(e for e in result.entries if e.name == "benchmarks.json")
    assert benchmarks_entry.record_count == 1


def test_archive_analysis_encrypted_vxp(inspector_env):
    """Test encrypted profiles: graceful state without credentials, and inspection with password."""
    inspector, mgr, _, l_repo, _, _, _, _ = inspector_env

    profile = mgr.create_profile(name="EncryptedSecProfile", domains=["security"])
    l_repo.save(Lesson(
        profile_id=profile.profile_id,
        title="Sanitize SQL inputs",
        trigger_pattern="SQL injection vulnerability",
        recommended_strategy="Use bind parameters",
        scope=KnowledgeScope.DOMAIN,
        evidence=[VerificationEvidence(verification_type="test", passed=True)],
    ))

    password = "CorrectSecretPassword!99"
    vxp_path = mgr.export_profile("EncryptedSecProfile", password=password)
    assert vxp_path.is_file()

    # 1. Inspect WITHOUT password -> Graceful inspection without fabricating entries
    res_no_pwd = inspector.inspect_archive(vxp_path, password=None)
    assert res_no_pwd.is_encrypted is True
    assert res_no_pwd.is_valid_zip is False
    assert res_no_pwd.is_corrupt is False
    assert res_no_pwd.entries == []
    assert res_no_pwd.total_uncompressed_bytes is None
    assert res_no_pwd.encryption_details is not None
    assert res_no_pwd.encryption_details["algorithm"] == "AES-256-GCM"
    assert len(res_no_pwd.encryption_details["salt_hex"]) == 32
    assert len(res_no_pwd.encryption_details["nonce_hex"]) == 24
    assert res_no_pwd.encryption_details["ciphertext_bytes"] > 0
    assert "Password required" in res_no_pwd.error_message

    # 2. Inspect WITH wrong password -> Decryption failure
    res_wrong_pwd = inspector.inspect_archive(vxp_path, password="WrongPassword123")
    assert res_wrong_pwd.is_encrypted is True
    assert res_wrong_pwd.is_corrupt is True
    assert "Decryption failed" in res_wrong_pwd.error_message

    # 3. Inspect WITH correct password -> Full decryption and inspection
    res_correct_pwd = inspector.inspect_archive(vxp_path, password=password)
    assert res_correct_pwd.is_valid_zip is True
    assert res_correct_pwd.is_corrupt is False
    assert res_correct_pwd.integrity_verified is True
    assert len(res_correct_pwd.entries) >= 5
    lessons_entry = next(e for e in res_correct_pwd.entries if e.name == "lessons.json")
    assert lessons_entry.record_count == 1


def test_archive_analysis_corrupt_archives(inspector_env):
    """Test detection of invalid zip headers, truncated data, and SHA-256 mismatch."""
    inspector, _, _, _, _, _, _, config = inspector_env

    # 1. Completely invalid content
    bad_file = config.exports_dir / "bad.vxp"
    bad_file.write_bytes(b"NOT_A_ZIP_AND_TOO_SHORT")
    res_bad = inspector.inspect_archive(bad_file)
    assert res_bad.is_corrupt is True
    assert res_bad.is_valid_zip is False

    # 2. Broken ZIP structure
    broken_zip = config.exports_dir / "broken.vxp"
    broken_zip.write_bytes(b"PK\x03\x04truncated_corrupt_header_bytes")
    res_broken = inspector.inspect_archive(broken_zip)
    assert res_broken.is_corrupt is True
    assert res_broken.is_valid_zip is False

    # 3. Tampered payload checksum mismatch
    tampered_zip = config.exports_dir / "tampered.vxp"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"schema_version": "1.0.0", "name": "Tampered"}))
        zf.writestr("lessons.json", json.dumps([{"title": "Injected lesson"}]))
        zf.writestr("strategies.json", "[]")
        zf.writestr("integrity.sha256", "0000000000000000000000000000000000000000000000000000000000000000")
    tampered_zip.write_bytes(buf.getvalue())

    res_tampered = inspector.inspect_archive(tampered_zip)
    assert res_tampered.is_corrupt is True
    assert res_tampered.integrity_verified is False
    assert "checksum mismatch" in res_tampered.error_message.lower()


def test_archive_analysis_unsupported_version(inspector_env):
    """Test detection of unsupported manifest schema versions."""
    inspector, _, _, _, _, _, _, config = inspector_env

    futuristic_zip = config.exports_dir / "futuristic.vxp"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "schema_version": "2.5.0",
            "name": "FuturisticProfile",
            "version": "3.0.0"
        }))
        zf.writestr("lessons.json", "[]")
        zf.writestr("strategies.json", "[]")
        zf.writestr("preferences.json", "{}")
        zf.writestr("benchmarks.json", "[]")
        # Valid checksum for empty payload
        chk = compute_sha256(b"[][]{}[]")
        zf.writestr("integrity.sha256", chk)
    futuristic_zip.write_bytes(buf.getvalue())


    res = inspector.inspect_archive(futuristic_zip)
    assert res.is_unsupported_version is True
    assert res.schema_version == "2.5.0"
    assert "not supported" in res.error_message.lower()


def test_storage_analytics(inspector_env):
    """Test accurate storage measurements across compressed, uncompressed, DB, WAL, and process RAM."""
    inspector, mgr, _, l_repo, _, _, _, config = inspector_env

    profile = mgr.create_profile(name="StorageProfile", domains=["backend"])
    l_repo.save(Lesson(
        profile_id=profile.profile_id,
        title="Connection pooling optimization",
        trigger_pattern="database connection pool exhausted",
        recommended_strategy="Increase pool size and set connection timeout",
    ))
    mgr.export_profile("StorageProfile")

    storage = inspector.get_storage_analytics(profile.profile_id)

    assert storage.compressed_archive_bytes > 0
    assert storage.uncompressed_archive_bytes > 0
    assert storage.database_file_bytes > 0
    assert storage.total_database_bytes >= storage.database_file_bytes
    assert storage.process_pid > 0
    assert "compressed_archive" in storage.human_readable
    assert "database_file" in storage.human_readable
    assert "process_ram_rss" in storage.human_readable


def test_expertise_calculations_observed_vs_verified(inspector_env):
    """Test mathematical separation of observed activity from verified competence."""
    inspector, mgr, _, l_repo, s_repo, e_repo, _, _ = inspector_env

    profile = mgr.create_profile(name="MobileBackendProfile", domains=["mobile", "backend"])

    # 1. Experiences: 2 verified passing in mobile, 1 failing in mobile
    e_repo.save(ExperienceRecord(
        profile_id=profile.profile_id,
        session_id="s1",
        task_id="t1",
        project_id="proj-alpha",
        domain="mobile",
        languages=["kotlin"],
        frameworks=["compose"],
        initial_problem="Fix Compose crash",
        verification=VerificationEvidence(verification_type="test", passed=True, total_tests=3, passed_tests=3),
        outcome="success",
    ))
    e_repo.save(ExperienceRecord(
        profile_id=profile.profile_id,
        session_id="s2",
        task_id="t2",
        project_id="proj-alpha",
        domain="mobile",
        languages=["kotlin"],
        frameworks=["compose"],
        initial_problem="Add Compose button",
        verification=VerificationEvidence(verification_type="test", passed=True, total_tests=2, passed_tests=2),
        outcome="success",
    ))
    e_repo.save(ExperienceRecord(
        profile_id=profile.profile_id,
        session_id="s3",
        task_id="t3",
        project_id="proj-alpha",
        domain="mobile",
        languages=["kotlin"],
        frameworks=["compose"],
        initial_problem="Experimental compose animation",
        verification=VerificationEvidence(verification_type="test", passed=False, failed_tests=1),
        outcome="failure",
    ))

    # 2. Lessons: 1 verified, 1 candidate (unverified)
    l_repo.save(Lesson(
        profile_id=profile.profile_id,
        title="Compose state hoisting",
        trigger_pattern="State hoisting pattern",
        recommended_strategy="Pass state down, events up",
        context_conditions={"domain": "mobile", "languages": ["kotlin"], "frameworks": ["compose"]},
        provenance=Provenance(verification_count=3),
        evidence=[VerificationEvidence(verification_type="test", passed=True)],
        active=True,
    ))
    l_repo.save(Lesson(
        profile_id=profile.profile_id,
        title="Experimental compose preview",
        trigger_pattern="Compose preview annotation",
        recommended_strategy="Use multipreview annotations",
        context_conditions={"domain": "mobile", "languages": ["kotlin"], "frameworks": ["compose"]},
        provenance=Provenance(verification_count=0),
        evidence=[],  # No passing evidence -> Candidate lesson
        active=True,
    ))

    # 3. Strategy in category "debug": 6 attempts, 5 successes
    s_repo.save(StrategyRecord(
        profile_id=profile.profile_id,
        name="logcatTracing",
        category="debug",
        attempts_count=6,
        success_count=5,
        bayesian_score=0.75,
    ))

    # Calculate expertise
    analytics = inspector.calculate_expertise(profile.profile_id)

    mobile_item = next(d for d in analytics.domains if d.name == "mobile")
    assert mobile_item.observed_activity_count >= 5  # 3 tasks + lessons
    assert mobile_item.verified_competence_count >= 3  # verified tasks + verified lesson provenance
    assert mobile_item.verified_lesson_count == 1
    assert mobile_item.candidate_lesson_count == 1
    assert mobile_item.competence_score_pct > 0.0

    debug_item = next(c for c in analytics.task_categories if c.name == "debug")
    assert debug_item.observed_activity_count == 6
    assert debug_item.verified_competence_count == 5
    assert debug_item.competence_score_pct > 70.0


def test_searchable_and_filterable_views(inspector_env):
    """Test searching and filtering lessons, strategies, projects, tech, and preferences."""
    inspector, mgr, _, l_repo, s_repo, e_repo, b_repo, _ = inspector_env

    profile = mgr.create_profile(name="FilterableProfile", domains=["web"])

    l_repo.save(Lesson(
        profile_id=profile.profile_id,
        title="React 19 Server Actions form handling",
        trigger_pattern="Form submission state",
        recommended_strategy="Use useActionState and Server Actions",
        scope=KnowledgeScope.TECHNOLOGY,
        context_conditions={"domain": "web", "languages": ["typescript"], "frameworks": ["react"]},
        evidence=[VerificationEvidence(passed=True)],
    ))
    l_repo.save(Lesson(
        profile_id=profile.profile_id,
        title="Global architectural idempotency",
        trigger_pattern="API retry loop idempotency",
        recommended_strategy="Use Idempotency-Key headers",
        scope=KnowledgeScope.GLOBAL,
        context_conditions={"domain": "web"},
        evidence=[],  # Candidate
    ))

    s_repo.save(StrategyRecord(
        profile_id=profile.profile_id,
        name="useActionState",
        category="frontend",
        attempts_count=4,
        success_count=4,
        bayesian_score=0.83,
    ))

    e_repo.save(ExperienceRecord(
        profile_id=profile.profile_id,
        session_id="s1",
        task_id="t1",
        project_id="web-portal",
        domain="web",
        languages=["typescript"],
        frameworks=["react"],
        initial_problem="Form action bug",
        outcome="success",
    ))

    b_repo.save_metric(profile.profile_id, "web_bench", "latency_ms", 120.5, {})

    # 1. Search keyword
    res_q = inspector.get_searchable_views(profile.profile_id, query="server actions")
    assert len(res_q["lessons"]) == 1
    assert res_q["lessons"][0]["title"] == "React 19 Server Actions form handling"

    # 2. Scope filter
    res_scope = inspector.get_searchable_views(profile.profile_id, scope="global")
    assert len(res_scope["lessons"]) == 1
    assert res_scope["lessons"][0]["scope"] == "global"

    # 3. Status filter (verified vs candidate)
    res_ver = inspector.get_searchable_views(profile.profile_id, status="verified")
    assert len(res_ver["lessons"]) == 1
    assert res_ver["lessons"][0]["status"] == "verified"

    res_cand = inspector.get_searchable_views(profile.profile_id, status="candidate")
    assert len(res_cand["lessons"]) == 1
    assert res_cand["lessons"][0]["status"] == "candidate"

    # 4. Projects & Technologies (unfiltered)
    res_all = inspector.get_searchable_views(profile.profile_id)
    assert len(res_all["projects"]) == 1
    assert res_all["projects"][0]["project_id"] == "web-portal"
    assert res_all["projects"][0]["success_rate_pct"] == 100.0

    tech_names = [t["name"].lower() for t in res_all["technologies"]]
    assert "react" in tech_names or "typescript" in tech_names

    # 5. Preferences & Benchmarks
    assert "default_profile" in res_all["preferences"]
    assert len(res_all["benchmarks"]) == 1



def test_record_detail_and_contradictions(inspector_env):
    """Test detailed record inspector with provenance, evidence, and conflict detection."""
    inspector, mgr, _, l_repo, _, _, _, _ = inspector_env

    profile = mgr.create_profile(name="ConflictProfile", domains=["devops"])

    # Lesson 1
    l1 = Lesson(
        profile_id=profile.profile_id,
        title="Docker multistage caching optimization",
        trigger_pattern="docker build slow caching layer",
        recommended_strategy="Use BuildKit with --cache-from and multi-stage builds",
        anti_patterns=["single-stage build with apt-get update in separate RUN"],
        confidence=0.88,
        scope=KnowledgeScope.TECHNOLOGY,
        provenance=Provenance(origin_project_ids=["proj-x"], verification_count=4),
        evidence=[VerificationEvidence(verification_type="build", compiler_exit_code=0, passed=True)],
    )
    l_repo.save(l1)

    # Lesson 2: Directly contradicts Lesson 1 (prescribes Lesson 1's anti-pattern)
    l2 = Lesson(
        profile_id=profile.profile_id,
        title="Single stage docker build simplification",
        trigger_pattern="docker build slow caching layer",
        recommended_strategy="single-stage build with apt-get update in separate RUN",
        anti_patterns=["multi-stage build complexity"],
        confidence=0.60,
        scope=KnowledgeScope.TECHNOLOGY,
    )
    l_repo.save(l2)

    # Inspect Lesson 2
    detail = inspector.get_record_detail("lesson", l2.id)
    assert detail.record_id == l2.id
    assert detail.contradictions is not None
    assert detail.contradictions.has_contradictions is True
    assert len(detail.contradictions.conflicting_lessons) == 1
    assert detail.contradictions.conflicting_lessons[0]["id"] == l1.id

    # Inspect Lesson 1 (evidence & provenance verified)
    detail1 = inspector.get_record_detail("lesson", l1.id)
    assert detail1.provenance["verification_count"] == 4
    assert len(detail1.evidence) == 1
    assert detail1.evidence[0]["compiler_exit_code"] == 0


def test_version_comparison_and_timeline(inspector_env):
    """Test version difference detection (additions, updates, removals, rollbacks)."""
    inspector, mgr, _, l_repo, s_repo, _, b_repo, _ = inspector_env

    profile = mgr.create_profile(name="VersionedProfile")

    # Version 1.0.1
    l1 = Lesson(
        profile_id=profile.profile_id,
        title="Base lesson 1",
        trigger_pattern="pattern 1",
        recommended_strategy="strategy 1",
        confidence=0.75,
    )
    l_repo.save(l1)
    v1 = mgr.create_version(profile.profile_id, message="Initial baseline V1")
    assert v1.version == "1.0.1"

    # Version 1.0.2: Add Lesson 2, update Lesson 1 confidence, add Strategy 1
    l1.confidence = 0.90
    l_repo.save(l1)

    l2 = Lesson(
        profile_id=profile.profile_id,
        title="Added lesson 2",
        trigger_pattern="pattern 2",
        recommended_strategy="strategy 2",
        confidence=0.85,
    )
    l_repo.save(l2)

    s1 = StrategyRecord(profile_id=profile.profile_id, name="newStrategy", attempts_count=3, success_count=3)
    s_repo.save(s1)

    v2 = mgr.create_version(profile.profile_id, message="Added lesson 2 and strategy")
    assert v2.version == "1.0.2"

    # Compare 1.0.1 vs 1.0.2
    diff = inspector.compare_versions(profile.profile_id, "1.0.1", "1.0.2")
    assert len(diff.added_lessons) == 1
    assert diff.added_lessons[0]["title"] == "Added lesson 2"
    assert len(diff.updated_lessons) == 1
    assert diff.updated_lessons[0]["changes"]["confidence_delta"] == 0.15
    assert len(diff.added_strategies) == 1
    assert diff.added_strategies[0]["name"] == "newStrategy"

    # Rollback to 1.0.1
    mgr.rollback_version(profile.profile_id, "1.0.1")
    v3 = mgr.create_version(profile.profile_id, message="Rollback to version 1.0.1")

    timeline = inspector.get_expertise_timeline(profile.profile_id)
    assert len(timeline) == 3
    assert timeline[0].version == "1.0.1"
    assert timeline[2].is_rollback is True


def test_safe_mutations_require_explicit_confirmation(inspector_env):
    """Test that editing or deleting profiles or lessons requires explicit confirmation and records history."""
    inspector, mgr, _, l_repo, _, _, _, _ = inspector_env

    profile = mgr.create_profile(name="SafeMutateProfile")
    lesson = Lesson(
        profile_id=profile.profile_id,
        title="Initial mutable lesson",
        trigger_pattern="mutable trigger",
        recommended_strategy="Old strategy advice",
        active=True,
    )
    l_repo.save(lesson)

    # 1. Modification WITHOUT confirmation fails
    with pytest.raises(ValueError, match="confirmation is required"):
        inspector.modify_lesson_safely(
            lesson.id,
            updates={"recommended_strategy": "New strategy"},
            confirm=False,
        )

    # 2. Modification WITH confirmation succeeds and records checkpoints
    versions_before = len(mgr.list_versions(profile.profile_id))
    updated_lesson = inspector.modify_lesson_safely(
        lesson.id,
        updates={"recommended_strategy": "New verified strategy", "active": False},
        confirm=True,
        reason="Manual correction",
    )
    assert updated_lesson.recommended_strategy == "New verified strategy"
    assert updated_lesson.active is False

    versions_after = len(mgr.list_versions(profile.profile_id))
    # Created pre-edit and post-edit checkpoints
    assert versions_after >= versions_before + 2

    # 3. Deletion WITHOUT confirmation fails
    with pytest.raises(ValueError, match="confirmation is required"):
        inspector.delete_lesson_safely(lesson.id, confirm=False)

    # 4. Deletion WITH confirmation succeeds and records checkpoint
    success = inspector.delete_lesson_safely(lesson.id, confirm=True)
    assert success is True
    assert l_repo.get_by_id(lesson.id) is None


def test_privacy_boundaries_and_secret_redaction(inspector_env):
    """Test that secrets in titles, triggers, or evidence are redacted by inspector."""
    inspector, mgr, _, l_repo, _, e_repo, _, _ = inspector_env

    profile = mgr.create_profile(name="PrivacyProfile")

    # Store lesson with embedded API keys
    secret_key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz12345678"
    lesson = Lesson(
        profile_id=profile.profile_id,
        title=f"Fix API authentication with key {secret_key}",
        trigger_pattern=f"Error connecting using bearer token sk-ant-12345678901234567890123456789012",
        recommended_strategy=f"Pass authorization header with valid token",
        evidence=[VerificationEvidence(evidence_snippet=f"Failed auth for user password='SuperSecretPassword123'")],
    )
    l_repo.save(lesson)

    # Check search views
    views = inspector.get_searchable_views(profile.profile_id)
    inspected_title = views["lessons"][0]["title"]
    assert secret_key not in inspected_title
    assert "[REDACTED_ANTHROPIC_KEY]" in inspected_title

    # Check record detail
    detail = inspector.get_record_detail("lesson", lesson.id)
    assert secret_key not in detail.title
    assert "SuperSecretPassword123" not in detail.evidence[0]["evidence_snippet"]
    assert "[REDACTED_password_SECRET]" in detail.evidence[0]["evidence_snippet"]


def test_inspector_api_endpoints(inspector_env):
    """Test FastAPI REST endpoints for inspector."""
    inspector, mgr, p_repo, l_repo, _, _, _, config = inspector_env
    api_app = create_api_app(config)
    client = TestClient(api_app)

    profile = mgr.create_profile(name="ApiProfile", domains=["web"])
    lesson = Lesson(
        profile_id=profile.profile_id,
        title="Web optimization lesson",
        trigger_pattern="web slow bundle",
        recommended_strategy="Code splitting",
        evidence=[VerificationEvidence(passed=True)],
    )
    l_repo.save(lesson)

    # 1. GET /api/inspector/profiles
    res_list = client.get("/api/inspector/profiles")
    assert res_list.status_code == 200
    assert any(p["name"] == "ApiProfile" for p in res_list.json())

    # 2. GET /api/inspector/profile/{id}
    res_sum = client.get(f"/api/inspector/profile/{profile.profile_id}")
    assert res_sum.status_code == 200
    data_sum = res_sum.json()
    assert data_sum["name"] == "ApiProfile"
    assert data_sum["verified_lesson_count"] == 1

    # 3. GET /api/inspector/archive/{id}
    res_arch = client.get(f"/api/inspector/archive/{profile.profile_id}")
    assert res_arch.status_code == 200
    data_arch = res_arch.json()
    assert data_arch["is_valid_zip"] is True
    assert len(data_arch["entries"]) >= 4

    # 4. GET /api/inspector/expertise/{id}
    res_exp = client.get(f"/api/inspector/expertise/{profile.profile_id}")
    assert res_exp.status_code == 200
    assert "domains" in res_exp.json()

    # 5. GET /api/inspector/views/{id}
    res_views = client.get(f"/api/inspector/views/{profile.profile_id}?query=optimization")
    assert res_views.status_code == 200
    assert len(res_views.json()["lessons"]) == 1

    # 6. GET /api/inspector/record/lesson/{id}
    res_rec = client.get(f"/api/inspector/record/lesson/{lesson.id}")
    assert res_rec.status_code == 200
    assert res_rec.json()["record_id"] == lesson.id

    # 7. GET /api/inspector/storage
    res_stor = client.get("/api/inspector/storage")
    assert res_stor.status_code == 200
    assert "human_readable" in res_stor.json()

    # 8. POST /api/inspector/lessons/{id}/modify (without confirm -> 400)
    res_mod_bad = client.post(
        f"/api/inspector/lessons/{lesson.id}/modify",
        json={"updates": {"recommended_strategy": "New strategy"}, "confirm": False},
    )
    assert res_mod_bad.status_code == 400

    # 9. POST /api/inspector/lessons/{id}/modify (with confirm -> 200)
    res_mod_ok = client.post(
        f"/api/inspector/lessons/{lesson.id}/modify",
        json={"updates": {"recommended_strategy": "New strategy via API"}, "confirm": True},
    )
    assert res_mod_ok.status_code == 200
    assert res_mod_ok.json()["recommended_strategy"] == "New strategy via API"

    # 10. DELETE /api/inspector/lessons/{id} (with confirm -> 200)
    res_del = client.request(
        "DELETE",
        f"/api/inspector/lessons/{lesson.id}",
        json={"confirm": True},
    )
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"
