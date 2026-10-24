"""Experience Inspector and Profile Analytics service.

Provides deep inspection of .vxp archives, storage footprints, expertise
metrics (observed activity vs verified competence), version diffing,
contradiction detection, and safe non-silent mutations with versioning.
"""

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import zipfile

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from pydantic import BaseModel, Field

from evodev.config import EvoDevConfig, load_config
from evodev.learning.consolidator import ExperienceConsolidator
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
from evodev.models.profile import ProfileManifest, ProfilePackage, ProfileVersion
from evodev.profiles.format import ProfileArchiveFormat
from evodev.security.crypto import compute_sha256, decrypt_payload
from evodev.security.redactor import SecretRedactor
from evodev.security.validator import (
    ArchiveSizeExceededError,
    MalformedProfileError,
    ProfileValidator,
    UnsafeArchivePathError,
)
from evodev.storage.repositories import (
    BenchmarkRepository,
    EventRepository,
    ExperienceRepository,
    LessonRepository,
    ProfileRepository,
    StrategyRepository,
)


class ArchiveEntryDetail(BaseModel):
    """Metadata for an individual entry inside a .vxp archive."""

    name: str
    uncompressed_bytes: int
    compressed_bytes: int
    compression_ratio_pct: float
    record_count: Optional[int] = None
    description: str = ""


class ArchiveInspectionResult(BaseModel):
    """Deep structural and integrity inspection of a .vxp archive."""

    file_path: Optional[str] = None
    file_size_bytes: int = 0
    is_valid_zip: bool = False
    is_encrypted: bool = False
    is_corrupt: bool = False
    is_unsupported_version: bool = False
    schema_version: Optional[str] = None
    supported_schema_version: str = "2.0.0"
    encryption_details: Optional[Dict[str, Any]] = None
    entries: List[ArchiveEntryDetail] = Field(default_factory=list)
    total_uncompressed_bytes: Optional[int] = None
    overall_compression_ratio_pct: Optional[float] = None
    integrity_checksum_expected: Optional[str] = None
    integrity_checksum_calculated: Optional[str] = None
    integrity_verified: bool = False
    manifest_summary: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class ExpertiseItem(BaseModel):
    """Detailed activity and verified competence metric for a domain/tech/category."""

    name: str
    category_type: str  # domain, technology, framework, task_category
    observed_activity_count: int  # Total tasks, attempts, and observations
    verified_competence_count: int  # Verified passing tasks, verified lessons, successful strategies
    competence_score_pct: float  # Empirical verified competence rate (0 - 100%)
    verified_lesson_count: int
    candidate_lesson_count: int
    strategy_count: int
    avg_bayesian_score: float
    last_activity_at: Optional[datetime] = None


class ExpertiseAnalytics(BaseModel):
    """Comprehensive multi-dimensional expertise analysis for a profile."""

    profile_id: str
    profile_name: str
    domains: List[ExpertiseItem] = Field(default_factory=list)
    technologies: List[ExpertiseItem] = Field(default_factory=list)
    frameworks: List[ExpertiseItem] = Field(default_factory=list)
    task_categories: List[ExpertiseItem] = Field(default_factory=list)
    total_observed_activity: int = 0
    total_verified_competence: int = 0
    overall_competence_pct: float = 0.0


class ContradictionReport(BaseModel):
    """Analysis of contradictory recommendations or anti-patterns."""

    has_contradictions: bool = False
    conflicting_lessons: List[Dict[str, Any]] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class DetailedRecordView(BaseModel):
    """Full detail view of an individual knowledge record for inspection."""

    record_type: str  # lesson, strategy, experience, benchmark
    record_id: str
    title: str
    data: Dict[str, Any]
    provenance: Optional[Dict[str, Any]] = None
    scope: Optional[str] = None
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[float] = None
    outcome_history: Optional[Dict[str, Any]] = None
    timestamps: Dict[str, Optional[str]] = Field(default_factory=dict)
    contradictions: Optional[ContradictionReport] = None


class StorageAnalytics(BaseModel):
    """Detailed storage metrics across archives, database, cache, and RAM."""

    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    compressed_archive_bytes: int = 0
    uncompressed_archive_bytes: int = 0
    database_file_bytes: int = 0
    database_wal_bytes: int = 0
    database_shm_bytes: int = 0
    total_database_bytes: int = 0
    cache_directory_bytes: int = 0
    process_ram_rss_bytes: int = 0
    process_ram_vms_bytes: int = 0
    process_pid: int = 0
    human_readable: Dict[str, str] = Field(default_factory=dict)


class VersionDiff(BaseModel):
    """Difference analysis between two profile version checkpoints."""

    profile_id: str
    profile_name: str
    version_a: str
    version_b: str
    created_at_a: Optional[str] = None
    created_at_b: Optional[str] = None
    is_rollback: bool = False
    rollback_target: Optional[str] = None
    added_lessons: List[Dict[str, Any]] = Field(default_factory=list)
    updated_lessons: List[Dict[str, Any]] = Field(default_factory=list)
    removed_lessons: List[Dict[str, Any]] = Field(default_factory=list)
    added_strategies: List[Dict[str, Any]] = Field(default_factory=list)
    updated_strategies: List[Dict[str, Any]] = Field(default_factory=list)
    removed_strategies: List[Dict[str, Any]] = Field(default_factory=list)
    benchmark_deltas: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class TimelineEvent(BaseModel):
    """Chronological event milestone in profile history."""

    id: str
    version: str
    timestamp: datetime
    message: str
    is_rollback: bool = False
    verified_lessons_count: int = 0
    candidate_lessons_count: int = 0
    strategies_count: int = 0
    benchmarks_count: int = 0


class ProfileSummary(BaseModel):
    """High-level inspection summary of a profile."""

    profile_id: str
    name: str
    version: str
    description: str
    load_state: str  # ACTIVE, STORED, STANDALONE_VXP, ENCRYPTED, CORRUPT
    schema_version: str
    is_schema_supported: bool
    file_size_bytes: int
    uncompressed_size_bytes: int
    experience_count: int
    verified_lesson_count: int
    candidate_lesson_count: int
    strategy_count: int
    domain_coverage: List[str]
    domain_coverage_pct: float
    created_at: datetime
    updated_at: datetime
    is_active: bool
    archive_path: Optional[str] = None


class ProfileInspector:
    """Inspector and Analytics engine for experience profiles and .vxp packages."""

    KNOWN_CORE_DOMAINS = ["general", "mobile", "web", "backend", "ml", "security", "devops"]

    def __init__(
        self,
        profile_repo: ProfileRepository,
        lesson_repo: LessonRepository,
        strategy_repo: StrategyRepository,
        experience_repo: ExperienceRepository,
        benchmark_repo: Optional[BenchmarkRepository] = None,
        event_repo: Optional[EventRepository] = None,
        config: Optional[EvoDevConfig] = None,
    ):
        self.profile_repo = profile_repo
        self.lesson_repo = lesson_repo
        self.strategy_repo = strategy_repo
        self.experience_repo = experience_repo
        self.benchmark_repo = benchmark_repo
        self.event_repo = event_repo
        self.config = config or load_config()
        self.archive_format = ProfileArchiveFormat(self.config)
        self.validator = ProfileValidator(self.config)
        self.redactor = SecretRedactor()
        self.consolidator = ExperienceConsolidator(self.lesson_repo, self.config)

    def _resolve_profile(self, identifier: str) -> Optional[ProfileManifest]:
        """Lookup by ID first, then by name."""
        return self.profile_repo.get_by_id(identifier) or self.profile_repo.get_by_name(identifier)

    # =========================================================================
    # 1. Profile Summary & Header Metrics
    # =========================================================================

    def get_profile_summary(self, identifier: str) -> ProfileSummary:
        """Calculate complete summary metrics for a profile."""
        profile = self._resolve_profile(identifier)
        if not profile:
            raise ValueError(f"Profile not found: {identifier}")

        active_profile = self.profile_repo.get_active()
        is_active = bool(active_profile and active_profile.profile_id == profile.profile_id)

        # Query actual database counts
        all_lessons = self.lesson_repo.list_by_profile(profile.profile_id, active_only=False)
        strategies = self.strategy_repo.list_by_profile(profile.profile_id)
        exp_count = self.experience_repo.count_by_profile(profile.profile_id)

        # Distinguish verified lessons from candidate lessons
        verified_count = sum(
            1 for l in all_lessons if l.active and l.evidence and any(e.passed for e in l.evidence)
        )
        candidate_count = len(all_lessons) - verified_count

        # Check for real exported archive on disk
        archive_file = self.config.exports_dir / f"{profile.name}.vxp"
        if not archive_file.is_file():
            # Check profiles directory
            archive_file = self.config.profiles_dir / f"{profile.name}.vxp"

        file_size_bytes = 0
        uncompressed_size_bytes = 0
        load_state = "ACTIVE" if is_active else "STORED"
        archive_path_str = None

        if archive_file.is_file():
            archive_path_str = str(archive_file)
            file_size_bytes = archive_file.stat().st_size
            try:
                insp = self.inspect_archive(archive_file)
                if insp.total_uncompressed_bytes is not None:
                    uncompressed_size_bytes = insp.total_uncompressed_bytes
                if insp.is_encrypted:
                    load_state = "ENCRYPTED_ARCHIVE"
                elif insp.is_corrupt:
                    load_state = "CORRUPT_ARCHIVE"
            except Exception:
                pass

        if uncompressed_size_bytes == 0:
            # Measure actual in-memory uncompressed footprint of profile payload
            package = ProfilePackage(
                manifest=profile,
                lessons=all_lessons,
                strategies=strategies,
                preferences={},
                benchmarks=self.benchmark_repo.get_metrics(profile.profile_id)
                if self.benchmark_repo
                else [],
            )
            raw_json = (
                package.manifest.model_dump_json()
                + json.dumps([l.model_dump(mode="json") for l in package.lessons])
                + json.dumps([s.model_dump(mode="json") for s in package.strategies])
                + json.dumps(package.preferences)
                + json.dumps(package.benchmarks)
            )
            uncompressed_size_bytes = len(raw_json.encode("utf-8"))
            if file_size_bytes == 0:
                # Estimate compressed size from in-memory zip
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("manifest.json", package.manifest.model_dump_json())
                    zf.writestr("lessons.json", json.dumps([l.model_dump(mode="json") for l in package.lessons]))
                    zf.writestr("strategies.json", json.dumps([s.model_dump(mode="json") for s in package.strategies]))
                file_size_bytes = len(zip_buf.getvalue())

        # Calculate actual domain coverage from stored lessons & profile manifest
        observed_domains = set(profile.domains)
        for l in all_lessons:
            cond_domain = l.context_conditions.get("domain")
            if cond_domain:
                observed_domains.add(cond_domain)

        domain_coverage = sorted(list(observed_domains)) if observed_domains else ["general"]
        coverage_pct = round(
            min(100.0, (len(domain_coverage) / float(max(1, len(self.KNOWN_CORE_DOMAINS)))) * 100),
            1,
        )

        schema_ver = profile.schema_version or "2.0.0"
        is_schema_supported = schema_ver in {"1.0.0", "2.0.0"}

        return ProfileSummary(
            profile_id=profile.profile_id,
            name=profile.name,
            version=profile.version,
            description=profile.description,
            load_state=load_state,
            schema_version=schema_ver,
            is_schema_supported=is_schema_supported,
            file_size_bytes=file_size_bytes,
            uncompressed_size_bytes=uncompressed_size_bytes,
            experience_count=exp_count,
            verified_lesson_count=verified_count,
            candidate_lesson_count=candidate_count,
            strategy_count=len(strategies),
            domain_coverage=domain_coverage,
            domain_coverage_pct=coverage_pct,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            is_active=is_active,
            archive_path=archive_path_str,
        )

    # =========================================================================
    # 2. Real .vxp Archive Format Inspection & Enumeration
    # =========================================================================

    def inspect_archive(
        self,
        vxp_path_or_bytes: Union[Path, str, bytes],
        password: Optional[str] = None,
    ) -> ArchiveInspectionResult:
        """Enumerate real archive entries, sizes, compression ratios, and integrity."""
        file_path_str = None
        if isinstance(vxp_path_or_bytes, (Path, str)):
            p = Path(vxp_path_or_bytes)
            file_path_str = str(p)
            if not p.is_file():
                return ArchiveInspectionResult(
                    file_path=file_path_str,
                    is_corrupt=True,
                    error_message=f"Archive file not found: {p}",
                )
            with open(p, "rb") as f:
                raw_bytes = f.read()
        else:
            raw_bytes = vxp_path_or_bytes

        total_file_bytes = len(raw_bytes)

        # 1. Check for Encryption
        is_zip = raw_bytes.startswith(b"PK\x03\x04")
        if not is_zip:
            # Check AES-256-GCM header (16 salt + 12 nonce + ciphertext)
            if len(raw_bytes) >= 28:
                salt_hex = raw_bytes[:16].hex()
                nonce_hex = raw_bytes[16:28].hex()
                ciphertext_len = len(raw_bytes) - 28

                if not password:
                    # Gracefully return encrypted status without decrypting or fabricating internal contents
                    return ArchiveInspectionResult(
                        file_path=file_path_str,
                        file_size_bytes=total_file_bytes,
                        is_valid_zip=False,
                        is_encrypted=True,
                        is_corrupt=False,
                        encryption_details={
                            "algorithm": "AES-256-GCM",
                            "kdf": "PBKDF2-HMAC-SHA256 (100,000 iterations)",
                            "salt_hex": salt_hex,
                            "nonce_hex": nonce_hex,
                            "ciphertext_bytes": ciphertext_len,
                            "status": "Authentication credentials required to inspect entries",
                        },
                        entries=[],
                        total_uncompressed_bytes=None,
                        overall_compression_ratio_pct=None,
                        error_message="Profile is encrypted with AES-256-GCM. Password required to decrypt and inspect internal entries.",
                    )

                # Attempt Decryption with provided password
                try:
                    raw_bytes = decrypt_payload(raw_bytes, password)
                except Exception as e:
                    return ArchiveInspectionResult(
                        file_path=file_path_str,
                        file_size_bytes=total_file_bytes,
                        is_valid_zip=False,
                        is_encrypted=True,
                        is_corrupt=True,
                        encryption_details={
                            "algorithm": "AES-256-GCM",
                            "salt_hex": salt_hex,
                            "nonce_hex": nonce_hex,
                            "ciphertext_bytes": ciphertext_len,
                            "status": "Decryption failed",
                        },
                        error_message=f"Decryption failed: Incorrect password or corrupted authentication tag ({e}).",
                    )
            else:
                return ArchiveInspectionResult(
                    file_path=file_path_str,
                    file_size_bytes=total_file_bytes,
                    is_valid_zip=False,
                    is_corrupt=True,
                    error_message="Invalid file format: Not a valid ZIP archive or encrypted container.",
                )

        # 2. Inspect ZIP structure
        zip_buf = io.BytesIO(raw_bytes)
        try:
            with zipfile.ZipFile(zip_buf, "r") as zf:
                # Enforce security checks (Zip Slip, Zip Bomb)
                try:
                    self.validator.validate_archive_safety(zf)
                except (UnsafeArchivePathError, ArchiveSizeExceededError) as e:
                    return ArchiveInspectionResult(
                        file_path=file_path_str,
                        file_size_bytes=total_file_bytes,
                        is_valid_zip=True,
                        is_corrupt=True,
                        error_message=f"Security validation failed: {e}",
                    )

                namelist = set(zf.namelist())
                entries: List[ArchiveEntryDetail] = []
                total_uncompressed = 0
                total_compressed = 0

                entry_descriptions = {
                    "manifest.json": "Profile metadata, UUID, schema version, checksums, author",
                    "lessons.json": "Verified & candidate engineering lessons with provenance",
                    "strategies.json": "Empirical Bayesian success/regression outcome records",
                    "preferences.json": "User style rules, test runner choices, scope overrides",
                    "benchmarks.json": "Empirical evaluation scores across benchmark suites",
                    "memories.json": "Categorized persistent memories across 8 cognitive partitions",
                    "skills.json": "Self-improving, versioned skills and procedures",
                    "integrity.sha256": "SHA-256 cryptographic digest of uncompressed payload",
                }

                for info in zf.infolist():
                    uncomp = info.file_size
                    comp = info.compress_size
                    total_uncompressed += uncomp
                    total_compressed += comp

                    ratio = (
                        round((1.0 - (comp / float(uncomp))) * 100, 1)
                        if uncomp > 0 and comp <= uncomp
                        else 0.0
                    )

                    # Calculate record count for known JSON entries
                    record_count = None
                    try:
                        content_bytes = zf.read(info.filename)
                        if info.filename == "manifest.json":
                            record_count = 1
                        elif info.filename in ("lessons.json", "strategies.json", "benchmarks.json", "memories.json", "skills.json"):
                            parsed = json.loads(content_bytes.decode("utf-8"))
                            record_count = len(parsed) if isinstance(parsed, list) else 0
                        elif info.filename == "preferences.json":
                            parsed = json.loads(content_bytes.decode("utf-8"))
                            record_count = len(parsed) if isinstance(parsed, dict) else 0
                        elif info.filename == "integrity.sha256":
                            record_count = 1
                    except Exception:
                        pass

                    desc = entry_descriptions.get(info.filename, "Additional profile artifact")

                    entries.append(
                        ArchiveEntryDetail(
                            name=info.filename,
                            uncompressed_bytes=uncomp,
                            compressed_bytes=comp,
                            compression_ratio_pct=ratio,
                            record_count=record_count,
                            description=desc,
                        )
                    )

                overall_ratio = (
                    round((1.0 - (total_compressed / float(total_uncompressed))) * 100, 1)
                    if total_uncompressed > 0 and total_compressed <= total_uncompressed
                    else 0.0
                )

                # 3. Check cryptographic integrity
                expected_sha = None
                calculated_sha = None
                integrity_verified = False

                if "integrity.sha256" in namelist:
                    expected_sha = zf.read("integrity.sha256").decode("utf-8").strip()
                    lessons_data = (
                        zf.read("lessons.json").decode("utf-8") if "lessons.json" in namelist else ""
                    )
                    strategies_data = (
                        zf.read("strategies.json").decode("utf-8")
                        if "strategies.json" in namelist
                        else ""
                    )
                    preferences_data = (
                        zf.read("preferences.json").decode("utf-8")
                        if "preferences.json" in namelist
                        else "{}"
                    )
                    benchmarks_data = (
                        zf.read("benchmarks.json").decode("utf-8")
                        if "benchmarks.json" in namelist
                        else "[]"
                    )
                    memories_data = (
                        zf.read("memories.json").decode("utf-8")
                        if "memories.json" in namelist
                        else "[]"
                    )
                    skills_data = (
                        zf.read("skills.json").decode("utf-8")
                        if "skills.json" in namelist
                        else "[]"
                    )

                    combined_v2 = (
                        lessons_data + strategies_data + preferences_data + benchmarks_data + memories_data + skills_data
                    ).encode("utf-8")
                    combined_v1 = (
                        lessons_data + strategies_data + preferences_data + benchmarks_data
                    ).encode("utf-8")

                    calc_v2 = compute_sha256(combined_v2)
                    calc_v1 = compute_sha256(combined_v1)

                    if expected_sha == calc_v2:
                        calculated_sha = calc_v2
                        integrity_verified = True
                    elif expected_sha == calc_v1:
                        calculated_sha = calc_v1
                        integrity_verified = True
                    else:
                        calculated_sha = calc_v2
                        integrity_verified = False

                # 4. Manifest summary & schema version check
                manifest_summary = None
                is_unsupported_ver = False
                schema_ver = "2.0.0"

                if "manifest.json" in namelist:
                    try:
                        m_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                        schema_ver = m_data.get("schema_version", "2.0.0")
                        is_unsupported_ver = schema_ver not in {"1.0.0", "2.0.0"}
                        manifest_summary = {
                            "profile_id": m_data.get("profile_id"),
                            "name": m_data.get("name"),
                            "version": m_data.get("version"),
                            "author": m_data.get("author"),
                            "description": m_data.get("description"),
                            "domains": m_data.get("domains", []),
                            "technologies": m_data.get("technologies", []),
                            "schema_version": schema_ver,
                            "stats": m_data.get("stats", {}),
                        }
                    except Exception:
                        pass

                is_corrupt = (
                    ("integrity.sha256" in namelist and not integrity_verified)
                    or ("manifest.json" not in namelist)
                    or ("lessons.json" not in namelist)
                )

                err = None
                if is_unsupported_ver and is_corrupt:
                    err = f"Profile uses unsupported schema version {schema_ver} and archive integrity check failed."
                elif is_unsupported_ver:
                    err = f"Profile uses schema version {schema_ver}, which is not supported by this engine (supported: 1.0.0, 2.0.0)."
                elif is_corrupt:
                    err = "Archive integrity verification failed: Checksum mismatch or missing required members."

                return ArchiveInspectionResult(
                    file_path=file_path_str,
                    file_size_bytes=total_file_bytes,
                    is_valid_zip=True,
                    is_encrypted=bool(password),
                    is_corrupt=is_corrupt,
                    is_unsupported_version=is_unsupported_ver,
                    schema_version=schema_ver,
                    supported_schema_version="1.0.0",
                    entries=entries,
                    total_uncompressed_bytes=total_uncompressed,
                    overall_compression_ratio_pct=overall_ratio,
                    integrity_checksum_expected=expected_sha,
                    integrity_checksum_calculated=calculated_sha,
                    integrity_verified=integrity_verified,
                    manifest_summary=manifest_summary,
                    error_message=err,
                )

        except zipfile.BadZipFile as e:
            return ArchiveInspectionResult(
                file_path=file_path_str,
                file_size_bytes=total_file_bytes,
                is_valid_zip=False,
                is_corrupt=True,
                error_message=f"Corrupt .vxp archive: {e}",
            )

    # =========================================================================
    # 3. Interactive Expertise Analytics (Observed vs Verified)
    # =========================================================================

    def calculate_expertise(self, identifier: str) -> ExpertiseAnalytics:
        """Calculate real expertise metrics for domains, technologies, frameworks, and task categories.
        
        Strictly distinguishes:
        - Observed Activity: raw task experiences, tool invocations, and attempts.
        - Verified Competence: empirical passing tests, verified lessons, and Bayesian strategy success.
        """
        profile = self._resolve_profile(identifier)
        if not profile:
            raise ValueError(f"Profile not found: {identifier}")

        p_id = profile.profile_id
        lessons = self.lesson_repo.list_by_profile(p_id, active_only=False)
        strategies = self.strategy_repo.list_by_profile(p_id)
        experiences = self.experience_repo.list_by_profile(p_id, limit=1000)

        # Buckets for aggregation
        domain_data: Dict[str, Dict[str, Any]] = {}
        tech_data: Dict[str, Dict[str, Any]] = {}
        framework_data: Dict[str, Dict[str, Any]] = {}
        category_data: Dict[str, Dict[str, Any]] = {}

        def _get_bucket(store: Dict[str, Dict[str, Any]], key: str, cat_type: str) -> Dict[str, Any]:
            norm_key = key.strip().lower()
            if norm_key not in store:
                store[norm_key] = {
                    "name": key.strip(),
                    "category_type": cat_type,
                    "observed_activity": 0,
                    "verified_competence": 0,
                    "verified_lessons": 0,
                    "candidate_lessons": 0,
                    "strategy_count": 0,
                    "bayesian_scores": [],
                    "last_activity": None,
                }
            return store[norm_key]

        # 1. Process Experiences (Task observations & empirical verification)
        for exp in experiences:
            exp_verified = bool(exp.verification and exp.verification.passed)
            # Domain
            dom = exp.domain or "general"
            b = _get_bucket(domain_data, dom, "domain")
            b["observed_activity"] += 1
            if exp_verified:
                b["verified_competence"] += 1
            if not b["last_activity"] or exp.created_at > b["last_activity"]:
                b["last_activity"] = exp.created_at

            # Languages / Technologies
            for lang in exp.languages:
                if lang:
                    tb = _get_bucket(tech_data, lang, "technology")
                    tb["observed_activity"] += 1
                    if exp_verified:
                        tb["verified_competence"] += 1
                    if not tb["last_activity"] or exp.created_at > tb["last_activity"]:
                        tb["last_activity"] = exp.created_at

            # Frameworks
            for fw in exp.frameworks:
                if fw:
                    fb = _get_bucket(framework_data, fw, "framework")
                    fb["observed_activity"] += 1
                    if exp_verified:
                        fb["verified_competence"] += 1
                    if not fb["last_activity"] or exp.created_at > fb["last_activity"]:
                        fb["last_activity"] = exp.created_at

        # 2. Process Lessons (Knowledge, confidence, and verification evidence)
        for lesson in lessons:
            is_verified = bool(lesson.active and lesson.evidence and any(e.passed for e in lesson.evidence))
            ver_count = lesson.provenance.verification_count if lesson.provenance else 1

            # Domain
            dom = lesson.context_conditions.get("domain") or (profile.domains[0] if profile.domains else "general")
            b = _get_bucket(domain_data, dom, "domain")
            b["observed_activity"] += max(1, ver_count)
            if is_verified:
                b["verified_competence"] += ver_count
                b["verified_lessons"] += 1
            else:
                b["candidate_lessons"] += 1
            if not b["last_activity"] or lesson.updated_at > b["last_activity"]:
                b["last_activity"] = lesson.updated_at

            # Languages / Technologies
            langs = lesson.context_conditions.get("languages", [])
            for lang in langs:
                if lang:
                    tb = _get_bucket(tech_data, lang, "technology")
                    tb["observed_activity"] += max(1, ver_count)
                    if is_verified:
                        tb["verified_competence"] += ver_count
                        tb["verified_lessons"] += 1
                    else:
                        tb["candidate_lessons"] += 1
                    if not tb["last_activity"] or lesson.updated_at > tb["last_activity"]:
                        tb["last_activity"] = lesson.updated_at

            # Frameworks
            fws = lesson.context_conditions.get("frameworks", [])
            for fw in fws:
                if fw:
                    fb = _get_bucket(framework_data, fw, "framework")
                    fb["observed_activity"] += max(1, ver_count)
                    if is_verified:
                        fb["verified_competence"] += ver_count
                        fb["verified_lessons"] += 1
                    else:
                        fb["candidate_lessons"] += 1
                    if not fb["last_activity"] or lesson.updated_at > fb["last_activity"]:
                        fb["last_activity"] = lesson.updated_at

        # 3. Process Strategies (Task categories & Bayesian empirical score)
        for strat in strategies:
            cat = strat.category or "general"
            cb = _get_bucket(category_data, cat, "task_category")
            cb["observed_activity"] += strat.attempts_count
            cb["verified_competence"] += strat.success_count
            cb["strategy_count"] += 1
            cb["bayesian_scores"].append(strat.bayesian_score)
            if not cb["last_activity"] or strat.last_attempted_at > cb["last_activity"]:
                cb["last_activity"] = strat.last_attempted_at

        # Ensure declared profile domains and technologies exist in the analytics even if initial
        for d in profile.domains:
            _get_bucket(domain_data, d, "domain")
        for t in profile.technologies:
            _get_bucket(tech_data, t, "technology")

        # Convert to typed ExpertiseItem models
        def _build_items(store: Dict[str, Dict[str, Any]]) -> List[ExpertiseItem]:
            results = []
            for item in store.values():
                obs = item["observed_activity"]
                ver = item["verified_competence"]
                # Competence calculation: Laplace smoothed verification rate
                score = round(((ver + 1.0) / float(obs + 2.0)) * 100, 1) if obs > 0 else 50.0
                # Clamp within 0 - 100%
                score = max(5.0, min(99.0, score))
                scores = item["bayesian_scores"]
                avg_b = round(sum(scores) / float(len(scores)), 3) if scores else 0.50

                results.append(
                    ExpertiseItem(
                        name=item["name"],
                        category_type=item["category_type"],
                        observed_activity_count=obs,
                        verified_competence_count=ver,
                        competence_score_pct=score,
                        verified_lesson_count=item["verified_lessons"],
                        candidate_lesson_count=item["candidate_lessons"],
                        strategy_count=item["strategy_count"],
                        avg_bayesian_score=avg_b,
                        last_activity_at=item["last_activity"],
                    )
                )
            results.sort(key=lambda x: (x.observed_activity_count, x.competence_score_pct), reverse=True)
            return results

        domain_items = _build_items(domain_data)
        tech_items = _build_items(tech_data)
        fw_items = _build_items(framework_data)
        cat_items = _build_items(category_data)

        total_obs = sum(d.observed_activity_count for d in domain_items) + sum(c.observed_activity_count for c in cat_items)
        total_ver = sum(d.verified_competence_count for d in domain_items) + sum(c.verified_competence_count for c in cat_items)
        overall_comp = (
            round(((total_ver + 1.0) / float(total_obs + 2.0)) * 100, 1)
            if total_obs > 0
            else 50.0
        )

        return ExpertiseAnalytics(
            profile_id=p_id,
            profile_name=profile.name,
            domains=domain_items,
            technologies=tech_items,
            frameworks=fw_items,
            task_categories=cat_items,
            total_observed_activity=total_obs,
            total_verified_competence=total_ver,
            overall_competence_pct=overall_comp,
        )

    # =========================================================================
    # 4. Searchable & Filterable Views
    # =========================================================================

    def get_searchable_views(
        self,
        identifier: str,
        query: str = "",
        scope: str = "",
        status: str = "",
        domain: str = "",
        category: str = "",
    ) -> Dict[str, Any]:
        """Provide clean, filtered views for lessons, strategies, projects, tech, prefs, and benchmarks."""
        profile = self._resolve_profile(identifier)
        if not profile:
            raise ValueError(f"Profile not found: {identifier}")

        p_id = profile.profile_id
        q_lower = query.strip().lower()

        # 1. Lessons
        all_lessons = self.lesson_repo.list_by_profile(p_id, active_only=False)
        filtered_lessons = []
        for l in all_lessons:
            is_verified = bool(l.active and l.evidence and any(e.passed for e in l.evidence))
            l_status = "verified" if is_verified else "candidate"

            # Filters
            if status and status.lower() != "all" and l_status != status.lower():
                continue
            if scope and scope.lower() != "all" and l.scope.value.lower() != scope.lower():
                continue
            l_dom = (l.context_conditions.get("domain") or "").lower()
            if domain and domain.lower() != "all" and l_dom != domain.lower():
                continue

            # Query search
            if q_lower:
                match_text = (
                    f"{l.title} {l.trigger_pattern} {l.recommended_strategy} "
                    f"{' '.join(l.anti_patterns)} {l.scope.value}"
                ).lower()
                if q_lower not in match_text:
                    continue

            filtered_lessons.append({
                "id": l.id,
                "title": self.redactor.redact_text(l.title),
                "trigger_pattern": self.redactor.redact_text(l.trigger_pattern),
                "recommended_strategy": self.redactor.redact_text(l.recommended_strategy),
                "anti_patterns": [self.redactor.redact_text(ap) for ap in l.anti_patterns],
                "confidence": l.confidence,
                "scope": l.scope.value,
                "epistemic_type": l.epistemic_type.value,
                "status": l_status,
                "is_active": l.active,
                "evidence_count": len(l.evidence),
                "verification_count": l.provenance.verification_count if l.provenance else 1,
                "created_at": l.created_at.isoformat(),
                "updated_at": l.updated_at.isoformat(),
            })

        # 2. Strategies
        all_strats = self.strategy_repo.list_by_profile(p_id)
        filtered_strats = []
        for s in all_strats:
            if category and category.lower() != "all" and s.category.lower() != category.lower():
                continue
            if q_lower and q_lower not in s.name.lower() and q_lower not in s.category.lower():
                continue

            filtered_strats.append({
                "id": s.id,
                "name": s.name,
                "category": s.category,
                "attempts_count": s.attempts_count,
                "success_count": s.success_count,
                "failure_count": s.failure_count,
                "regression_count": s.regression_count,
                "bayesian_score": round(s.bayesian_score, 3),
                "avg_duration_seconds": round(s.avg_duration_seconds, 2),
                "last_attempted_at": s.last_attempted_at.isoformat(),
            })

        # 3. Projects
        experiences = self.experience_repo.list_by_profile(p_id, limit=500)
        project_map: Dict[str, Dict[str, Any]] = {}
        for exp in experiences:
            pid = exp.project_id
            if pid not in project_map:
                project_map[pid] = {
                    "project_id": pid,
                    "task_count": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "languages": set(),
                    "frameworks": set(),
                    "first_seen": exp.created_at,
                    "last_seen": exp.created_at,
                }
            item = project_map[pid]
            item["task_count"] += 1
            if exp.outcome == "success":
                item["success_count"] += 1
            else:
                item["failed_count"] += 1
            for lang in exp.languages:
                item["languages"].add(lang)
            for fw in exp.frameworks:
                item["frameworks"].add(fw)
            if exp.created_at < item["first_seen"]:
                item["first_seen"] = exp.created_at
            if exp.created_at > item["last_seen"]:
                item["last_seen"] = exp.created_at

        # Also aggregate project provenance from lessons
        for l in all_lessons:
            for pid in l.provenance.origin_project_ids:
                if pid not in project_map:
                    project_map[pid] = {
                        "project_id": pid,
                        "task_count": 1,
                        "success_count": 1,
                        "failed_count": 0,
                        "languages": set(),
                        "frameworks": set(),
                        "first_seen": l.created_at,
                        "last_seen": l.updated_at,
                    }

        projects_list = []
        for p_info in project_map.values():
            if q_lower and q_lower not in p_info["project_id"].lower():
                continue
            rate = (
                round((p_info["success_count"] / float(p_info["task_count"])) * 100, 1)
                if p_info["task_count"] > 0
                else 0.0
            )
            projects_list.append({
                "project_id": p_info["project_id"],
                "task_count": p_info["task_count"],
                "success_count": p_info["success_count"],
                "failed_count": p_info["failed_count"],
                "success_rate_pct": rate,
                "languages": sorted(list(p_info["languages"])),
                "frameworks": sorted(list(p_info["frameworks"])),
                "first_seen": p_info["first_seen"].isoformat(),
                "last_seen": p_info["last_seen"].isoformat(),
            })
        projects_list.sort(key=lambda x: x["task_count"], reverse=True)

        # 4. Technologies
        tech_map: Dict[str, Dict[str, Any]] = {}
        for l in all_lessons:
            for t in l.context_conditions.get("languages", []) + l.context_conditions.get("frameworks", []):
                if not t:
                    continue
                t_lower = t.lower()
                if t_lower not in tech_map:
                    tech_map[t_lower] = {
                        "name": t,
                        "lesson_count": 0,
                        "verified_lessons": 0,
                        "confidences": [],
                    }
                tech_map[t_lower]["lesson_count"] += 1
                if l.active and l.evidence and any(e.passed for e in l.evidence):
                    tech_map[t_lower]["verified_lessons"] += 1
                tech_map[t_lower]["confidences"].append(l.confidence)

        technologies_list = []
        for t_info in tech_map.values():
            if q_lower and q_lower not in t_info["name"].lower():
                continue
            avg_c = (
                round(sum(t_info["confidences"]) / float(len(t_info["confidences"])), 2)
                if t_info["confidences"]
                else 0.50
            )
            technologies_list.append({
                "name": t_info["name"],
                "lesson_count": t_info["lesson_count"],
                "verified_lessons": t_info["verified_lessons"],
                "avg_confidence": avg_c,
            })
        technologies_list.sort(key=lambda x: x["lesson_count"], reverse=True)

        # 5. Preferences
        preferences = {
            "default_profile": self.config.default_profile_name,
            "secret_redaction_enabled": self.config.secret_redaction_enabled,
            "min_confidence_threshold": self.config.min_confidence_threshold,
            "promotion_min_occurrences": self.config.promotion_min_occurrences,
            "retention_days": self.config.retention_days,
            "max_stored_experiences": self.config.max_stored_experiences,
            "profile_domains": profile.domains,
            "profile_technologies": profile.technologies,
        }

        # 6. Benchmarks
        benchmarks = (
            self.benchmark_repo.get_metrics(p_id) if self.benchmark_repo else []
        )
        if q_lower:
            benchmarks = [
                b for b in benchmarks
                if q_lower in b.get("suite_name", "").lower()
                or q_lower in b.get("metric_name", "").lower()
            ]

        return {
            "profile_id": p_id,
            "profile_name": profile.name,
            "lessons": filtered_lessons,
            "strategies": filtered_strats,
            "projects": projects_list,
            "technologies": technologies_list,
            "preferences": preferences,
            "benchmarks": benchmarks,
        }

    # =========================================================================
    # 5. Detailed Record Inspector (Provenance, Contradictions, Evidence)
    # =========================================================================

    def get_record_detail(self, record_type: str, record_id: str) -> DetailedRecordView:
        """Inspect deep provenance, verification evidence, confidence, and contradictions."""
        if record_type == "lesson":
            lesson = self.lesson_repo.get_by_id(record_id)
            if not lesson:
                raise ValueError(f"Lesson not found: {record_id}")

            # Check contradictions using consolidator conflict detection
            other_lessons = [
                l for l in self.lesson_repo.list_by_profile(lesson.profile_id, active_only=False)
                if l.id != lesson.id
            ]
            conflicts = self.consolidator._find_conflicts(other_lessons, lesson)

            conflict_report = ContradictionReport(
                has_contradictions=len(conflicts) > 0,
                conflicting_lessons=[
                    {
                        "id": c.id,
                        "title": self.redactor.redact_text(c.title),
                        "recommended_strategy": self.redactor.redact_text(c.recommended_strategy),
                        "anti_patterns": [self.redactor.redact_text(a) for a in c.anti_patterns],
                        "active": c.active,
                        "confidence": c.confidence,
                    }
                    for c in conflicts
                ],
                notes=[
                    f"Contradicts strategy in active lesson '{c.title}'" for c in conflicts
                ] if conflicts else ["No conflicting lessons or anti-pattern collisions detected."],
            )

            # Redact evidence snippets
            clean_evidence = []
            for ev in lesson.evidence:
                clean_evidence.append({
                    "verification_type": ev.verification_type,
                    "passed": ev.passed,
                    "confidence_score": ev.confidence_score,
                    "total_tests": ev.total_tests,
                    "passed_tests": ev.passed_tests,
                    "failed_tests": ev.failed_tests,
                    "compiler_exit_code": ev.compiler_exit_code,
                    "linter_clean": ev.linter_clean,
                    "human_confirmed": ev.human_confirmed,
                    "evidence_snippet": self.redactor.redact_text(ev.evidence_snippet or ""),
                    "timestamp": ev.timestamp.isoformat(),
                })

            return DetailedRecordView(
                record_type="lesson",
                record_id=lesson.id,
                title=self.redactor.redact_text(lesson.title),
                data={
                    "id": lesson.id,
                    "profile_id": lesson.profile_id,
                    "title": self.redactor.redact_text(lesson.title),
                    "trigger_pattern": self.redactor.redact_text(lesson.trigger_pattern),
                    "recommended_strategy": self.redactor.redact_text(lesson.recommended_strategy),
                    "anti_patterns": [self.redactor.redact_text(a) for a in lesson.anti_patterns],
                    "context_conditions": lesson.context_conditions,
                    "active": lesson.active,
                    "confidence": lesson.confidence,
                    "scope": lesson.scope.value,
                    "epistemic_type": lesson.epistemic_type.value,
                },
                provenance={
                    "origin_task_ids": lesson.provenance.origin_task_ids,
                    "origin_project_ids": lesson.provenance.origin_project_ids,
                    "verification_count": lesson.provenance.verification_count,
                    "failure_count": lesson.provenance.failure_count,
                    "regression_count": lesson.provenance.regression_count,
                    "first_observed_at": lesson.provenance.first_observed_at.isoformat(),
                    "last_verified_at": lesson.provenance.last_verified_at.isoformat(),
                },
                scope=lesson.scope.value,
                evidence=clean_evidence,
                confidence=lesson.confidence,
                outcome_history={
                    "verification_count": lesson.provenance.verification_count,
                    "failure_count": lesson.provenance.failure_count,
                    "regression_count": lesson.provenance.regression_count,
                },
                timestamps={
                    "created_at": lesson.created_at.isoformat(),
                    "updated_at": lesson.updated_at.isoformat(),
                    "last_verified_at": lesson.provenance.last_verified_at.isoformat(),
                },
                contradictions=conflict_report,
            )

        elif record_type == "strategy":
            # Lookup strategy across profiles if needed
            rows = []
            for p in self.profile_repo.list_all():
                s = self.strategy_repo.get(p.profile_id, record_id)
                if s:
                    rows.append(s)
            if not rows:
                raise ValueError(f"Strategy record not found: {record_id}")
            strat = rows[0]

            return DetailedRecordView(
                record_type="strategy",
                record_id=strat.id,
                title=f"Strategy: {strat.name}",
                data={
                    "name": strat.name,
                    "category": strat.category,
                    "attempts_count": strat.attempts_count,
                    "success_count": strat.success_count,
                    "failure_count": strat.failure_count,
                    "regression_count": strat.regression_count,
                    "bayesian_score": strat.bayesian_score,
                    "avg_duration_seconds": strat.avg_duration_seconds,
                },
                confidence=strat.bayesian_score,
                outcome_history={
                    "attempts": strat.attempts_count,
                    "successes": strat.success_count,
                    "failures": strat.failure_count,
                    "regressions": strat.regression_count,
                    "bayesian_score": strat.bayesian_score,
                },
                timestamps={
                    "last_attempted_at": strat.last_attempted_at.isoformat(),
                },
            )

        elif record_type == "experience":
            exp = self.experience_repo.get_by_id(record_id)
            if not exp:
                raise ValueError(f"Experience record not found: {record_id}")

            ev_list = []
            if exp.verification:
                ev_list.append({
                    "verification_type": exp.verification.verification_type,
                    "passed": exp.verification.passed,
                    "confidence_score": exp.verification.confidence_score,
                    "total_tests": exp.verification.total_tests,
                    "passed_tests": exp.verification.passed_tests,
                    "evidence_snippet": self.redactor.redact_text(exp.verification.evidence_snippet or ""),
                    "timestamp": exp.verification.timestamp.isoformat(),
                })

            return DetailedRecordView(
                record_type="experience",
                record_id=exp.id,
                title=f"Experience in {exp.project_id}",
                data={
                    "task_id": exp.task_id,
                    "project_id": exp.project_id,
                    "domain": exp.domain,
                    "languages": exp.languages,
                    "frameworks": exp.frameworks,
                    "initial_problem": self.redactor.redact_text(exp.initial_problem),
                    "strategies_attempted": exp.strategies_attempted,
                    "outcome": exp.outcome,
                    "user_feedback": self.redactor.redact_text(exp.user_feedback or ""),
                },
                evidence=ev_list,
                timestamps={
                    "created_at": exp.created_at.isoformat(),
                },
            )

        raise ValueError(f"Unsupported record type: {record_type}")

    # =========================================================================
    # 6. Storage Analytics (Compressed, Uncompressed, DB, Cache, RAM)
    # =========================================================================

    def get_storage_analytics(self, identifier: Optional[str] = None) -> StorageAnalytics:
        """Calculate exact storage footprint distinguishing all layers."""
        p_name = None
        p_id = None
        if identifier:
            profile = self._resolve_profile(identifier)
            if profile:
                p_name = profile.name
                p_id = profile.profile_id

        # 1. Database file sizes
        db_file = self.config.db_path
        db_bytes = db_file.stat().st_size if db_file.is_file() else 0

        wal_file = Path(str(db_file) + "-wal")
        wal_bytes = wal_file.stat().st_size if wal_file.is_file() else 0

        shm_file = Path(str(db_file) + "-shm")
        shm_bytes = shm_file.stat().st_size if shm_file.is_file() else 0

        total_db_bytes = db_bytes + wal_bytes + shm_bytes

        # 2. Archive file sizes (.vxp)
        comp_archive_bytes = 0
        uncomp_archive_bytes = 0

        if p_name:
            vxp_file = self.config.exports_dir / f"{p_name}.vxp"
            if not vxp_file.is_file():
                vxp_file = self.config.profiles_dir / f"{p_name}.vxp"
            if vxp_file.is_file():
                comp_archive_bytes = vxp_file.stat().st_size
                try:
                    insp = self.inspect_archive(vxp_file)
                    if insp.total_uncompressed_bytes is not None:
                        uncomp_archive_bytes = insp.total_uncompressed_bytes
                except Exception:
                    pass

        if comp_archive_bytes == 0:
            # Aggregate all .vxp files in exports_dir
            for f in self.config.exports_dir.glob("*.vxp"):
                if f.is_file():
                    comp_archive_bytes += f.stat().st_size

        # 3. Cache directory size
        cache_bytes = 0
        pytest_cache = Path(".pytest_cache")
        if pytest_cache.is_dir():
            for root, _, files in os.walk(pytest_cache):
                for fn in files:
                    fp = Path(root) / fn
                    try:
                        cache_bytes += fp.stat().st_size
                    except OSError:
                        pass

        # 4. Process RAM Usage (RSS and VMS)
        pid = os.getpid()
        ram_rss = 0
        ram_vms = 0
        if HAS_PSUTIL:
            try:
                proc = psutil.Process(pid)
                mem = proc.memory_info()
                ram_rss = mem.rss
                ram_vms = mem.vms
            except Exception:
                pass

        def _fmt(b: int) -> str:
            if b >= 1024 * 1024:
                return f"{round(b / (1024.0 * 1024.0), 2)} MB"
            elif b >= 1024:
                return f"{round(b / 1024.0, 1)} KB"
            return f"{b} B"

        return StorageAnalytics(
            profile_id=p_id,
            profile_name=p_name,
            compressed_archive_bytes=comp_archive_bytes,
            uncompressed_archive_bytes=uncomp_archive_bytes,
            database_file_bytes=db_bytes,
            database_wal_bytes=wal_bytes,
            database_shm_bytes=shm_bytes,
            total_database_bytes=total_db_bytes,
            cache_directory_bytes=cache_bytes,
            process_ram_rss_bytes=ram_rss,
            process_ram_vms_bytes=ram_vms,
            process_pid=pid,
            human_readable={
                "compressed_archive": _fmt(comp_archive_bytes),
                "uncompressed_archive": _fmt(uncomp_archive_bytes),
                "database_file": _fmt(db_bytes),
                "database_wal": _fmt(wal_bytes),
                "total_database": _fmt(total_db_bytes),
                "cache": _fmt(cache_bytes),
                "process_ram_rss": _fmt(ram_rss),
                "process_ram_vms": _fmt(ram_vms),
            },
        )

    # =========================================================================
    # 7. Version Comparison & Expertise Timeline
    # =========================================================================

    def compare_versions(
        self,
        identifier: str,
        version_a_str: str,
        version_b_str: str,
    ) -> VersionDiff:
        """Calculate additions, updates, removals, rollbacks, and benchmark changes."""
        profile = self._resolve_profile(identifier)
        if not profile:
            raise ValueError(f"Profile not found: {identifier}")

        p_id = profile.profile_id
        ver_a = self.profile_repo.get_version(p_id, version_a_str)
        ver_b = self.profile_repo.get_version(p_id, version_b_str)

        if not ver_a:
            raise ValueError(f"Version {version_a_str} not found for profile {profile.name}")
        if not ver_b:
            raise ValueError(f"Version {version_b_str} not found for profile {profile.name}")

        pkg_a = ProfilePackage.model_validate_json(ver_a.package_data_json)
        pkg_b = ProfilePackage.model_validate_json(ver_b.package_data_json)

        # 1. Diff Lessons
        lessons_a = {l.id: l for l in pkg_a.lessons}
        lessons_b = {l.id: l for l in pkg_b.lessons}

        added_lessons = []
        updated_lessons = []
        removed_lessons = []

        for lid, lb in lessons_b.items():
            if lid not in lessons_a:
                added_lessons.append({
                    "id": lb.id,
                    "title": self.redactor.redact_text(lb.title),
                    "confidence": lb.confidence,
                    "scope": lb.scope.value,
                })
            else:
                la = lessons_a[lid]
                changes = {}
                if la.confidence != lb.confidence:
                    changes["confidence_delta"] = round(lb.confidence - la.confidence, 3)
                if la.active != lb.active:
                    changes["active_changed"] = f"{la.active} -> {lb.active}"
                if la.recommended_strategy != lb.recommended_strategy:
                    changes["strategy_updated"] = True
                if changes:
                    updated_lessons.append({
                        "id": lb.id,
                        "title": self.redactor.redact_text(lb.title),
                        "changes": changes,
                    })

        for lid, la in lessons_a.items():
            if lid not in lessons_b:
                removed_lessons.append({
                    "id": la.id,
                    "title": self.redactor.redact_text(la.title),
                    "confidence": la.confidence,
                    "scope": la.scope.value,
                })

        # 2. Diff Strategies
        strats_a = {s.name: s for s in pkg_a.strategies}
        strats_b = {s.name: s for s in pkg_b.strategies}

        added_strats = []
        updated_strats = []
        removed_strats = []

        for name, sb in strats_b.items():
            if name not in strats_a:
                added_strats.append({
                    "name": sb.name,
                    "category": sb.category,
                    "bayesian_score": sb.bayesian_score,
                })
            else:
                sa = strats_a[name]
                changes = {}
                if sa.attempts_count != sb.attempts_count:
                    changes["attempts_delta"] = sb.attempts_count - sa.attempts_count
                if sa.success_count != sb.success_count:
                    changes["success_delta"] = sb.success_count - sa.success_count
                if sa.bayesian_score != sb.bayesian_score:
                    changes["score_delta"] = round(sb.bayesian_score - sa.bayesian_score, 3)
                if changes:
                    updated_strats.append({
                        "name": sb.name,
                        "category": sb.category,
                        "changes": changes,
                    })

        for name, sa in strats_a.items():
            if name not in strats_b:
                removed_strats.append({
                    "name": sa.name,
                    "category": sa.category,
                })

        # 3. Check for Rollback
        is_rollback = False
        rollback_target = None
        if "rollback" in ver_b.message.lower():
            is_rollback = True
            m = re.search(r"rollback.*?(\d+\.\d+\.\d+)", ver_b.message.lower())
            if m:
                rollback_target = m.group(1)

        # 4. Diff Benchmarks
        bench_a = {b.get("metric_name"): b.get("metric_value") for b in pkg_a.benchmarks if "metric_name" in b}
        bench_b = {b.get("metric_name"): b.get("metric_value") for b in pkg_b.benchmarks if "metric_name" in b}

        benchmark_deltas = []
        for m_name, val_b in bench_b.items():
            val_a = bench_a.get(m_name)
            delta = round(val_b - val_a, 4) if val_a is not None else None
            benchmark_deltas.append({
                "metric_name": m_name,
                "value_a": val_a,
                "value_b": val_b,
                "delta": delta,
            })

        summary = (
            f"Comparison: {version_a_str} -> {version_b_str}. "
            f"+{len(added_lessons)} / ~{len(updated_lessons)} / -{len(removed_lessons)} lessons; "
            f"+{len(added_strats)} / ~{len(updated_strats)} / -{len(removed_strats)} strategies."
        )

        return VersionDiff(
            profile_id=p_id,
            profile_name=profile.name,
            version_a=version_a_str,
            version_b=version_b_str,
            created_at_a=ver_a.created_at.isoformat(),
            created_at_b=ver_b.created_at.isoformat(),
            is_rollback=is_rollback,
            rollback_target=rollback_target,
            added_lessons=added_lessons,
            updated_lessons=updated_lessons,
            removed_lessons=removed_lessons,
            added_strategies=added_strats,
            updated_strategies=updated_strats,
            removed_strategies=removed_strats,
            benchmark_deltas=benchmark_deltas,
            summary=summary,
        )

    def get_expertise_timeline(self, identifier: str) -> List[TimelineEvent]:
        """Fetch chronological timeline of version checkpoints and milestone events."""
        profile = self._resolve_profile(identifier)
        if not profile:
            raise ValueError(f"Profile not found: {identifier}")

        versions = self.profile_repo.list_versions(profile.profile_id)
        # Sort oldest first for timeline progression
        versions_sorted = sorted(versions, key=lambda v: (v.created_at, v.version))

        events: List[TimelineEvent] = []
        for v in versions_sorted:
            is_rb = "rollback" in v.message.lower()
            try:
                pkg = ProfilePackage.model_validate_json(v.package_data_json)
                ver_count = sum(
                    1 for l in pkg.lessons if l.active and l.evidence and any(e.passed for e in l.evidence)
                )
                cand_count = len(pkg.lessons) - ver_count
                strat_count = len(pkg.strategies)
                bench_count = len(pkg.benchmarks)
            except Exception:
                ver_count = 0
                cand_count = 0
                strat_count = 0
                bench_count = 0

            events.append(
                TimelineEvent(
                    id=v.id,
                    version=v.version,
                    timestamp=v.created_at,
                    message=v.message,
                    is_rollback=is_rb,
                    verified_lessons_count=ver_count,
                    candidate_lessons_count=cand_count,
                    strategies_count=strat_count,
                    benchmarks_count=bench_count,
                )
            )

        return events

    # =========================================================================
    # 8. Safe Non-Silent Profile Mutations with Version Checkpoints
    # =========================================================================

    def modify_lesson_safely(
        self,
        lesson_id: str,
        updates: Dict[str, Any],
        confirm: bool = False,
        reason: str = "User updated lesson",
    ) -> Lesson:
        """Modify a lesson only with explicit confirmation, preserving version history."""
        if not confirm:
            raise ValueError("Explicit confirmation is required to modify knowledge records.")

        lesson = self.lesson_repo.get_by_id(lesson_id)
        if not lesson:
            raise ValueError(f"Lesson not found: {lesson_id}")

        profile = self.profile_repo.get_by_id(lesson.profile_id)
        if not profile:
            raise ValueError(f"Associated profile not found: {lesson.profile_id}")

        # 1. Create automatic checkpoint BEFORE applying mutation
        self._create_version_checkpoint(
            profile.profile_id,
            message=f"Pre-edit checkpoint before modifying lesson: '{lesson.title[:40]}'",
        )

        # 2. Apply modifications
        if "title" in updates:
            lesson.title = self.validator.sanitize_lesson_text(updates["title"])
        if "recommended_strategy" in updates:
            lesson.recommended_strategy = self.validator.sanitize_lesson_text(
                updates["recommended_strategy"]
            )
        if "active" in updates:
            lesson.active = bool(updates["active"])
        if "confidence" in updates:
            lesson.confidence = max(0.05, min(0.99, float(updates["confidence"])))
        if "anti_patterns" in updates and isinstance(updates["anti_patterns"], list):
            lesson.anti_patterns = [self.validator.sanitize_lesson_text(a) for a in updates["anti_patterns"]]

        lesson.updated_at = datetime.now(timezone.utc)
        self.lesson_repo.save(lesson)

        # 3. Create post-edit checkpoint
        self._create_version_checkpoint(
            profile.profile_id,
            message=f"Modified lesson '{lesson.title[:40]}': {reason}",
        )

        return lesson

    def delete_lesson_safely(
        self,
        lesson_id: str,
        confirm: bool = False,
    ) -> bool:
        """Delete a lesson only with explicit confirmation, preserving version history."""
        if not confirm:
            raise ValueError("Explicit confirmation is required to delete knowledge records.")

        lesson = self.lesson_repo.get_by_id(lesson_id)
        if not lesson:
            return False

        profile = self.profile_repo.get_by_id(lesson.profile_id)
        if profile:
            self._create_version_checkpoint(
                profile.profile_id,
                message=f"Pre-delete checkpoint before deleting lesson: '{lesson.title[:40]}'",
            )

        success = self.lesson_repo.delete(lesson_id)

        if profile and success:
            self._create_version_checkpoint(
                profile.profile_id,
                message=f"Deleted lesson '{lesson.title[:40]}'",
            )

        return success

    def delete_profile_safely(
        self,
        identifier: str,
        confirm: bool = False,
    ) -> bool:
        """Delete an entire profile only with explicit confirmation."""
        if not confirm:
            raise ValueError("Explicit confirmation is required to delete an experience profile.")

        profile = self._resolve_profile(identifier)
        if not profile:
            return False

        return self.profile_repo.delete(profile.profile_id)

    def _create_version_checkpoint(self, profile_id: str, message: str) -> ProfileVersion:
        """Helper to create version checkpoint."""
        profile = self.profile_repo.get_by_id(profile_id)
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")

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

        versions = self.profile_repo.list_versions(profile.profile_id)
        ver_num = len(versions) + 1
        new_version_str = f"1.0.{ver_num}"

        version_checkpoint = ProfileVersion(
            profile_id=profile.profile_id,
            version=new_version_str,
            created_at=datetime.now(timezone.utc),
            message=message,
            manifest=profile,
            package_data_json=package.model_dump_json(),
        )

        self.profile_repo.add_version(version_checkpoint)
        return version_checkpoint
