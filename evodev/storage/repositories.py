"""Repository layer implementing clean CRUD for EvoDev database entities."""

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from evodev.models.checkpoints import CheckpointRecord, CheckpointType
from evodev.models.events import NormalizedEvent
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
from evodev.models.memory import MemoryCategory, MemoryItem
from evodev.models.profile import ProfileManifest, ProfileStats, ProfileVersion
from evodev.models.scheduler import JobStatus, JobType, ScheduledJob
from evodev.models.skills import (
    ProcedureStep,
    Skill,
    SkillEvaluation,
    SkillPrerequisite,
    SkillStatus,
    SkillVersion,
)
from evodev.storage.db import DatabaseManager


class ProfileRepository:
    """Persistence operations for experience profiles and version checkpoints."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def create(self, manifest: ProfileManifest, is_active: bool = False) -> ProfileManifest:
        """Create a new profile."""
        with self.db.session() as conn:
            if is_active:
                conn.execute("UPDATE profiles SET is_active = 0;")
            conn.execute(
                """
                INSERT INTO profiles (id, name, is_active, created_at, updated_at, manifest_json)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    manifest.profile_id,
                    manifest.name,
                    1 if is_active else 0,
                    manifest.created_at.isoformat(),
                    manifest.updated_at.isoformat(),
                    manifest.model_dump_json(),
                ),
            )
        return manifest

    def get_by_id(self, profile_id: str) -> Optional[ProfileManifest]:
        """Fetch profile manifest by profile ID."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT manifest_json FROM profiles WHERE id = ?;", (profile_id,)
            ).fetchone()
            if row:
                return ProfileManifest.model_validate_json(row["manifest_json"])
        return None

    def get_by_name(self, name: str) -> Optional[ProfileManifest]:
        """Fetch profile manifest by user-assigned name."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT manifest_json FROM profiles WHERE name = ?;", (name,)
            ).fetchone()
            if row:
                return ProfileManifest.model_validate_json(row["manifest_json"])
        return None

    def get_active(self) -> Optional[ProfileManifest]:
        """Retrieve the currently active profile manifest."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT manifest_json FROM profiles WHERE is_active = 1 LIMIT 1;"
            ).fetchone()
            if row:
                return ProfileManifest.model_validate_json(row["manifest_json"])
        return None

    def activate(self, profile_id: str) -> bool:
        """Mark a profile active, deactivating all others."""
        with self.db.session() as conn:
            conn.execute("UPDATE profiles SET is_active = 0;")
            cursor = conn.execute(
                "UPDATE profiles SET is_active = 1 WHERE id = ?;", (profile_id,)
            )
            return cursor.rowcount > 0

    def deactivate_all(self) -> None:
        """Deactivate all active profiles."""
        with self.db.session() as conn:
            conn.execute("UPDATE profiles SET is_active = 0;")

    def list_all(self) -> List[ProfileManifest]:
        """Return all stored profiles."""
        with self.db.session() as conn:
            rows = conn.execute("SELECT manifest_json FROM profiles ORDER BY name ASC;").fetchall()
            return [ProfileManifest.model_validate_json(r["manifest_json"]) for r in rows]

    def rename(self, profile_id: str, new_name: str) -> bool:
        """Rename an existing profile."""
        with self.db.session() as conn:
            manifest_row = conn.execute(
                "SELECT manifest_json FROM profiles WHERE id = ?;", (profile_id,)
            ).fetchone()
            if not manifest_row:
                return False

            manifest = ProfileManifest.model_validate_json(manifest_row["manifest_json"])
            manifest.name = new_name
            manifest.updated_at = datetime.now(timezone.utc)

            cursor = conn.execute(
                """
                UPDATE profiles 
                SET name = ?, updated_at = ?, manifest_json = ? 
                WHERE id = ?;
                """,
                (new_name, manifest.updated_at.isoformat(), manifest.model_dump_json(), profile_id),
            )
            return cursor.rowcount > 0

    def update_manifest(self, manifest: ProfileManifest) -> None:
        """Update manifest content and timestamps."""
        with self.db.session() as conn:
            manifest.updated_at = datetime.now(timezone.utc)
            conn.execute(
                "UPDATE profiles SET manifest_json = ?, updated_at = ? WHERE id = ?;",
                (manifest.model_dump_json(), manifest.updated_at.isoformat(), manifest.profile_id),
            )

    def delete(self, profile_id: str) -> bool:
        """Delete profile and cascade delete associated lessons and experiences."""
        with self.db.session() as conn:
            cursor = conn.execute("DELETE FROM profiles WHERE id = ?;", (profile_id,))
            return cursor.rowcount > 0

    def add_version(self, version: ProfileVersion) -> None:
        """Store an immutable version snapshot."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO profile_versions (id, profile_id, version, created_at, message, package_json)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    version.id,
                    version.profile_id,
                    version.version,
                    version.created_at.isoformat(),
                    version.message,
                    version.package_data_json,
                ),
            )

    def list_versions(self, profile_id: str) -> List[ProfileVersion]:
        """Fetch version history for a profile."""
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT id, profile_id, version, created_at, message, package_json 
                FROM profile_versions 
                WHERE profile_id = ? 
                ORDER BY created_at DESC, version DESC;
                """,
                (profile_id,),
            ).fetchall()
            results = []
            for r in rows:
                manifest_row = json.loads(r["package_json"])
                results.append(
                    ProfileVersion(
                        id=r["id"],
                        profile_id=r["profile_id"],
                        version=r["version"],
                        created_at=datetime.fromisoformat(r["created_at"]),
                        message=r["message"],
                        manifest=ProfileManifest.model_validate(manifest_row["manifest"]),
                        package_data_json=r["package_json"],
                    )
                )
            return results

    def get_version(self, profile_id: str, version_str: str) -> Optional[ProfileVersion]:
        """Retrieve a specific version record."""
        with self.db.session() as conn:
            row = conn.execute(
                """
                SELECT id, profile_id, version, created_at, message, package_json 
                FROM profile_versions 
                WHERE profile_id = ? AND version = ?;
                """,
                (profile_id, version_str),
            ).fetchone()
            if row:
                manifest_row = json.loads(row["package_json"])
                return ProfileVersion(
                    id=row["id"],
                    profile_id=row["profile_id"],
                    version=row["version"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    message=row["message"],
                    manifest=ProfileManifest.model_validate(manifest_row["manifest"]),
                    package_data_json=row["package_json"],
                )
        return None


class ExperienceRepository:
    """Persistence operations for task experience records."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, record: ExperienceRecord) -> None:
        """Insert or replace an experience record."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiences (
                    id, profile_id, session_id, task_id, project_id, domain,
                    languages_json, frameworks_json, initial_problem, outcome,
                    verification_json, raw_record_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.id,
                    record.profile_id,
                    record.session_id,
                    record.task_id,
                    record.project_id,
                    record.domain,
                    json.dumps(record.languages),
                    json.dumps(record.frameworks),
                    record.initial_problem,
                    record.outcome,
                    record.verification.model_dump_json() if record.verification else None,
                    record.model_dump_json(),
                    record.created_at.isoformat(),
                ),
            )

    def get_by_id(self, exp_id: str) -> Optional[ExperienceRecord]:
        """Fetch experience record by ID."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT raw_record_json FROM experiences WHERE id = ?;", (exp_id,)
            ).fetchone()
            if row:
                return ExperienceRecord.model_validate_json(row["raw_record_json"])
        return None

    def list_by_profile(
        self, profile_id: str, limit: int = 100, offset: int = 0
    ) -> List[ExperienceRecord]:
        """List experiences for a profile sorted by recency."""
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT raw_record_json FROM experiences 
                WHERE profile_id = ? 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?;
                """,
                (profile_id, limit, offset),
            ).fetchall()
            return [ExperienceRecord.model_validate_json(r["raw_record_json"]) for r in rows]

    def list_by_project(self, project_id: str, limit: int = 100) -> List[ExperienceRecord]:
        """List experiences for a specific project."""
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT raw_record_json FROM experiences 
                WHERE project_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?;
                """,
                (project_id, limit),
            ).fetchall()
            return [ExperienceRecord.model_validate_json(r["raw_record_json"]) for r in rows]

    def count_by_profile(self, profile_id: str) -> int:
        """Count total experiences in a profile."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM experiences WHERE profile_id = ?;", (profile_id,)
            ).fetchone()
            return row[0] if row else 0

    def delete(self, exp_id: str) -> bool:
        """Delete an experience record."""
        with self.db.session() as conn:
            cursor = conn.execute("DELETE FROM experiences WHERE id = ?;", (exp_id,))
            return cursor.rowcount > 0

    def delete_older_than(self, days: int) -> int:
        """Purge experiences older than N days."""
        with self.db.session() as conn:
            cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
            cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
            cursor = conn.execute("DELETE FROM experiences WHERE created_at < ?;", (cutoff_iso,))
            return cursor.rowcount


class LessonRepository:
    """Persistence operations for reusable lessons."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, lesson: Lesson) -> None:
        """Insert or replace a lesson."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO lessons (
                    id, profile_id, title, trigger_pattern, context_conditions_json,
                    recommended_strategy, anti_patterns_json, confidence, epistemic_type,
                    scope, provenance_json, evidence_json, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    lesson.id,
                    lesson.profile_id,
                    lesson.title,
                    lesson.trigger_pattern,
                    json.dumps(lesson.context_conditions),
                    lesson.recommended_strategy,
                    json.dumps(lesson.anti_patterns),
                    lesson.confidence,
                    lesson.epistemic_type.value,
                    lesson.scope.value,
                    lesson.provenance.model_dump_json(),
                    json.dumps([e.model_dump(mode="json") for e in lesson.evidence]),
                    1 if lesson.active else 0,
                    lesson.created_at.isoformat(),
                    lesson.updated_at.isoformat(),
                ),
            )

    def save_many(self, lessons: List[Lesson]) -> None:
        """Batch insert lessons."""
        for lesson in lessons:
            self.save(lesson)

    def get_by_id(self, lesson_id: str) -> Optional[Lesson]:
        """Fetch lesson by ID."""
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM lessons WHERE id = ?;", (lesson_id,)).fetchone()
            if row:
                return self._row_to_lesson(row)
        return None

    def list_by_profile(self, profile_id: str, active_only: bool = True) -> List[Lesson]:
        """List lessons belonging to a profile."""
        with self.db.session() as conn:
            query = "SELECT * FROM lessons WHERE profile_id = ?"
            args = [profile_id]
            if active_only:
                query += " AND is_active = 1"
            query += " ORDER BY confidence DESC, updated_at DESC;"
            rows = conn.execute(query, args).fetchall()
            return [self._row_to_lesson(r) for r in rows]

    def count_by_profile(self, profile_id: str) -> int:
        """Count total active lessons in a profile."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM lessons WHERE profile_id = ? AND is_active = 1;",
                (profile_id,),
            ).fetchone()
            return row[0] if row else 0

    def delete(self, lesson_id: str) -> bool:
        """Delete a lesson."""
        with self.db.session() as conn:
            cursor = conn.execute("DELETE FROM lessons WHERE id = ?;", (lesson_id,))
            return cursor.rowcount > 0

    create = save

    def _row_to_lesson(self, row: sqlite3.Row) -> Lesson:
        """Deserialize database row into Lesson model."""
        evidence_data = json.loads(row["evidence_json"])
        from evodev.models.experience import EpistemicType, KnowledgeScope, Provenance, VerificationEvidence

        return Lesson(
            id=row["id"],
            profile_id=row["profile_id"],
            title=row["title"],
            trigger_pattern=row["trigger_pattern"],
            context_conditions=json.loads(row["context_conditions_json"]),
            recommended_strategy=row["recommended_strategy"],
            anti_patterns=json.loads(row["anti_patterns_json"]),
            confidence=row["confidence"],
            epistemic_type=EpistemicType(row["epistemic_type"]),
            scope=KnowledgeScope(row["scope"]),
            provenance=Provenance.model_validate_json(row["provenance_json"]),
            evidence=[VerificationEvidence.model_validate(e) for e in evidence_data],
            active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class StrategyRepository:
    """Persistence operations for strategy statistics."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, record: StrategyRecord) -> None:
        """Save or update strategy performance record."""
        record.update_score()
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategies (
                    id, profile_id, name, category, attempts_count, success_count,
                    failure_count, regression_count, bayesian_score, avg_duration_seconds, last_attempted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.id,
                    record.profile_id,
                    record.name,
                    record.category,
                    record.attempts_count,
                    record.success_count,
                    record.failure_count,
                    record.regression_count,
                    record.bayesian_score,
                    record.avg_duration_seconds,
                    record.last_attempted_at.isoformat(),
                ),
            )

    def get(self, profile_id: str, name: str) -> Optional[StrategyRecord]:
        """Fetch a specific strategy record."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT * FROM strategies WHERE profile_id = ? AND name = ?;", (profile_id, name)
            ).fetchone()
            if row:
                return self._row_to_strategy(row)
        return None

    def list_by_profile(self, profile_id: str) -> List[StrategyRecord]:
        """List all strategies for a profile."""
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM strategies WHERE profile_id = ? ORDER BY bayesian_score DESC;",
                (profile_id,),
            ).fetchall()
            return [self._row_to_strategy(r) for r in rows]

    def count_by_profile(self, profile_id: str) -> int:
        """Count strategies associated with a profile quickly."""
        with self.db.session() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM strategies WHERE profile_id = ?;", (profile_id,)).fetchone()
            return row["cnt"] if row else 0


    def record_outcome(
        self,
        profile_id: str,
        name: str,
        category: str = "general",
        outcome: StrategyOutcome = StrategyOutcome.SUCCESS,
        duration_sec: float = 0.0,
    ) -> StrategyRecord:
        """Update strategy outcome metrics and recalculate Bayesian score."""
        strat = self.get(profile_id, name)
        if not strat:
            strat = StrategyRecord(
                profile_id=profile_id,
                name=name,
                category=category,
            )

        strat.attempts_count += 1
        if outcome == StrategyOutcome.SUCCESS:
            strat.success_count += 1
        elif outcome == StrategyOutcome.FAILURE:
            strat.failure_count += 1
        elif outcome == StrategyOutcome.REGRESSION:
            strat.regression_count += 1

        if duration_sec > 0:
            total_duration = (strat.avg_duration_seconds * (strat.attempts_count - 1)) + duration_sec
            strat.avg_duration_seconds = total_duration / strat.attempts_count

        strat.last_attempted_at = datetime.now(timezone.utc)
        self.save(strat)
        return strat

    def _row_to_strategy(self, row: sqlite3.Row) -> StrategyRecord:
        return StrategyRecord(
            id=row["id"],
            profile_id=row["profile_id"],
            name=row["name"],
            category=row["category"],
            attempts_count=row["attempts_count"],
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            regression_count=row["regression_count"],
            bayesian_score=row["bayesian_score"],
            avg_duration_seconds=row["avg_duration_seconds"],
            last_attempted_at=datetime.fromisoformat(row["last_attempted_at"]),
        )


class EventRepository:
    """Storage and querying for normalized raw lifecycle events."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, event: NormalizedEvent) -> None:
        """Record a normalized event."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO events (id, session_id, task_id, project_id, event_type, timestamp, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event.id,
                    event.session_id,
                    event.task_id,
                    event.project_id,
                    event.event_type.value,
                    event.timestamp.isoformat(),
                    event.model_dump_json(),
                ),
            )

    def list_by_session(self, session_id: str) -> List[NormalizedEvent]:
        """Fetch all events for a given session."""
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM events WHERE session_id = ? ORDER BY timestamp ASC;",
                (session_id,),
            ).fetchall()
            return [NormalizedEvent.model_validate_json(r["payload_json"]) for r in rows]

    def count(self) -> int:
        """Return total event count."""
        with self.db.session() as conn:
            row = conn.execute("SELECT COUNT(*) FROM events;").fetchone()
            return row[0] if row else 0

    def delete_older_than(self, days: int) -> int:
        """Purge events older than N days."""
        with self.db.session() as conn:
            cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
            cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
            cursor = conn.execute("DELETE FROM events WHERE timestamp < ?;", (cutoff_iso,))
            return cursor.rowcount


class BenchmarkRepository:
    """Persistence for empirical benchmark records."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save_metric(
        self,
        profile_id: str,
        suite_name: str,
        metric_name: str,
        value: float,
        details: Dict[str, Any],
    ) -> None:
        """Store a benchmark result."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO benchmarks (id, profile_id, suite_name, metric_name, metric_value, details_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(uuid.uuid4()),
                    profile_id,
                    suite_name,
                    metric_name,
                    value,
                    json.dumps(details),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_metrics(self, profile_id: str) -> List[Dict[str, Any]]:
        """Retrieve recorded benchmarks for a profile."""
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT suite_name, metric_name, metric_value, details_json, recorded_at 
                FROM benchmarks 
                WHERE profile_id = ? 
                ORDER BY recorded_at DESC;
                """,
                (profile_id,),
            ).fetchall()
            return [
                {
                    "suite_name": r["suite_name"],
                    "metric_name": r["metric_name"],
                    "metric_value": r["metric_value"],
                    "details": json.loads(r["details_json"]),
                    "recorded_at": r["recorded_at"],
                }
                for r in rows
            ]


class MemoryRepository:
    """Persistence operations for categorized persistent memory items."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, memory: MemoryItem) -> MemoryItem:
        """Create or update a persistent memory item."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, profile_id, category, title, content_json, scope, project_id,
                    confidence, epistemic_type, provenance_json, evidence_json, is_active,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    content_json = excluded.content_json,
                    scope = excluded.scope,
                    project_id = excluded.project_id,
                    confidence = excluded.confidence,
                    epistemic_type = excluded.epistemic_type,
                    provenance_json = excluded.provenance_json,
                    evidence_json = excluded.evidence_json,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at;
                """,
                (
                    memory.id,
                    memory.profile_id,
                    memory.category.value,
                    memory.title,
                    json.dumps(memory.content),
                    memory.scope.value,
                    memory.project_id,
                    memory.confidence,
                    memory.epistemic_type.value,
                    memory.provenance.model_dump_json(),
                    json.dumps([e.model_dump(mode="json") for e in memory.evidence]),
                    1 if memory.is_active else 0,
                    memory.created_at.isoformat(),
                    memory.updated_at.isoformat(),
                ),
            )
        return memory

    def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """Fetch memory item by ID."""
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?;", (memory_id,)).fetchone()
            if row:
                return self._row_to_memory(row)
        return None

    def list_by_profile(
        self,
        profile_id: str,
        category: Optional[MemoryCategory] = None,
        project_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[MemoryItem]:
        """List memory items for a profile with optional category and project filtering."""
        with self.db.session() as conn:
            query = "SELECT * FROM memories WHERE profile_id = ?"
            params: List[Any] = [profile_id]
            if category:
                query += " AND category = ?"
                params.append(category.value)
            if project_id:
                query += " AND (project_id IS NULL OR project_id = ? OR scope != 'project')"
                params.append(project_id)
            if active_only:
                query += " AND is_active = 1"
            query += " ORDER BY updated_at DESC;"

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_memory(r) for r in rows]

    def search(
        self,
        profile_id: str,
        query: str,
        category: Optional[MemoryCategory] = None,
        scope: Optional[KnowledgeScope] = None,
        project_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        """Search memory items matching text query in title or content."""
        with self.db.session() as conn:
            sql = "SELECT * FROM memories WHERE profile_id = ? AND is_active = 1"
            params: List[Any] = [profile_id]
            if category:
                sql += " AND category = ?"
                params.append(category.value)
            if scope:
                sql += " AND scope = ?"
                params.append(scope.value)
            if project_id:
                sql += " AND (project_id IS NULL OR project_id = ? OR scope != 'project')"
                params.append(project_id)

            terms = query.lower().split()
            rows = conn.execute(sql, params).fetchall()
            results = []
            for r in rows:
                mem = self._row_to_memory(r)
                text = f"{mem.title} {json.dumps(mem.content)}".lower()
                if not terms or any(t in text for t in terms):
                    results.append(mem)
            return results

    def delete(self, memory_id: str) -> bool:
        """Delete memory item."""
        with self.db.session() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?;", (memory_id,))
            return cursor.rowcount > 0

    def count_by_profile(self, profile_id: str) -> int:
        """Count active memories for a profile."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE profile_id = ? AND is_active = 1;",
                (profile_id,),
            ).fetchone()
            return row[0] if row else 0

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            profile_id=row["profile_id"],
            category=MemoryCategory(row["category"]),
            title=row["title"],
            content=json.loads(row["content_json"]),
            scope=KnowledgeScope(row["scope"]),
            project_id=row["project_id"],
            confidence=row["confidence"],
            epistemic_type=EpistemicType(row["epistemic_type"]),
            provenance=Provenance.model_validate_json(row["provenance_json"]),
            evidence=[VerificationEvidence.model_validate(e) for e in json.loads(row["evidence_json"])],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class SkillRepository:
    """Persistence operations for self-improving skills, versions, and evaluations."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save_skill(self, skill: Skill) -> Skill:
        """Create or update a skill record."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO skills (
                    id, profile_id, name, description, category, current_version,
                    status, scope, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    description = excluded.description,
                    category = excluded.category,
                    current_version = excluded.current_version,
                    status = excluded.status,
                    scope = excluded.scope,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    skill.id,
                    skill.profile_id,
                    skill.name,
                    skill.description,
                    skill.category,
                    skill.current_version,
                    skill.status.value,
                    skill.scope.value,
                    json.dumps(skill.metadata),
                    skill.created_at.isoformat(),
                    skill.updated_at.isoformat(),
                ),
            )
            # Save any attached versions
            for ver in skill.versions:
                self._save_version_conn(conn, ver)
        return skill

    def get_skill_by_id(self, skill_id: str) -> Optional[Skill]:
        """Fetch skill by ID with all versions attached."""
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM skills WHERE id = ?;", (skill_id,)).fetchone()
            if row:
                skill = self._row_to_skill(row)
                skill.versions = self._list_versions_conn(conn, skill_id)
                return skill
        return None

    def get_skill_by_name(self, profile_id: str, name: str) -> Optional[Skill]:
        """Fetch skill by unique profile and name."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT * FROM skills WHERE profile_id = ? AND name = ?;",
                (profile_id, name),
            ).fetchone()
            if row:
                skill = self._row_to_skill(row)
                skill.versions = self._list_versions_conn(conn, skill.id)
                return skill
        return None

    def list_skills(self, profile_id: str, status: Optional[SkillStatus] = None) -> List[Skill]:
        """List all skills in profile."""
        with self.db.session() as conn:
            query = "SELECT * FROM skills WHERE profile_id = ?"
            params: List[Any] = [profile_id]
            if status:
                query += " AND status = ?"
                params.append(status.value)
            query += " ORDER BY updated_at DESC;"

            rows = conn.execute(query, params).fetchall()
            skills = []
            for r in rows:
                s = self._row_to_skill(r)
                s.versions = self._list_versions_conn(conn, s.id)
                skills.append(s)
            return skills

    def save_version(self, version: SkillVersion) -> SkillVersion:
        """Save a new version of a skill."""
        with self.db.session() as conn:
            self._save_version_conn(conn, version)
        return version

    def get_version(self, skill_id: str, version_tag: str) -> Optional[SkillVersion]:
        """Fetch a specific version of a skill."""
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT * FROM skill_versions WHERE skill_id = ? AND version = ?;",
                (skill_id, version_tag),
            ).fetchone()
            if row:
                return self._row_to_version(row)
        return None

    def list_versions(self, skill_id: str) -> List[SkillVersion]:
        """List all versions of a skill."""
        with self.db.session() as conn:
            return self._list_versions_conn(conn, skill_id)

    def save_evaluation(self, eval_record: SkillEvaluation) -> SkillEvaluation:
        """Store a benchmark evaluation trial for a skill version."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO skill_evaluations (id, skill_version_id, task_id, benchmark_id, passed, evidence_json, evaluated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    eval_record.id,
                    eval_record.skill_version_id,
                    eval_record.task_id,
                    eval_record.benchmark_id,
                    1 if eval_record.passed else 0,
                    json.dumps(eval_record.evidence),
                    eval_record.evaluated_at.isoformat(),
                ),
            )
        return eval_record

    def list_evaluations(self, skill_version_id: str) -> List[SkillEvaluation]:
        """Retrieve evaluation history for a skill version."""
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM skill_evaluations WHERE skill_version_id = ? ORDER BY evaluated_at DESC;",
                (skill_version_id,),
            ).fetchall()
            return [
                SkillEvaluation(
                    id=r["id"],
                    skill_version_id=r["skill_version_id"],
                    task_id=r["task_id"],
                    benchmark_id=r["benchmark_id"],
                    passed=bool(r["passed"]),
                    evidence=json.loads(r["evidence_json"]),
                    evaluated_at=datetime.fromisoformat(r["evaluated_at"]),
                )
                for r in rows
            ]

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill and all associated versions/evaluations."""
        with self.db.session() as conn:
            cursor = conn.execute("DELETE FROM skills WHERE id = ?;", (skill_id,))
            return cursor.rowcount > 0

    get_by_id = get_skill_by_id
    list_by_profile = list_skills
    save = save_skill
    delete = delete_skill

    def _save_version_conn(self, conn: sqlite3.Connection, version: SkillVersion) -> None:
        conn.execute(
            """
            INSERT INTO skill_versions (
                id, skill_id, version, instructions, prerequisites_json,
                procedures_json, validation_steps_json, expected_outcomes_json,
                evaluation_summary_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_id, version) DO UPDATE SET
                instructions = excluded.instructions,
                prerequisites_json = excluded.prerequisites_json,
                procedures_json = excluded.procedures_json,
                validation_steps_json = excluded.validation_steps_json,
                expected_outcomes_json = excluded.expected_outcomes_json,
                evaluation_summary_json = excluded.evaluation_summary_json;
            """,
            (
                version.id,
                version.skill_id,
                version.version,
                version.instructions,
                json.dumps([p.model_dump(mode="json") for p in version.prerequisites]),
                json.dumps([p.model_dump(mode="json") for p in version.procedures]),
                json.dumps(version.validation_steps),
                json.dumps(version.expected_outcomes),
                json.dumps(version.evaluation_summary),
                version.created_at.isoformat(),
            ),
        )

    def _list_versions_conn(self, conn: sqlite3.Connection, skill_id: str) -> List[SkillVersion]:
        rows = conn.execute(
            "SELECT * FROM skill_versions WHERE skill_id = ? ORDER BY created_at DESC;",
            (skill_id,),
        ).fetchall()
        return [self._row_to_version(r) for r in rows]

    def _row_to_skill(self, row: sqlite3.Row) -> Skill:
        return Skill(
            id=row["id"],
            profile_id=row["profile_id"],
            name=row["name"],
            description=row["description"],
            category=row["category"],
            current_version=row["current_version"],
            status=SkillStatus(row["status"]),
            scope=KnowledgeScope(row["scope"]),
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _row_to_version(self, row: sqlite3.Row) -> SkillVersion:
        return SkillVersion(
            id=row["id"],
            skill_id=row["skill_id"],
            version=row["version"],
            instructions=row["instructions"],
            prerequisites=[SkillPrerequisite.model_validate(p) for p in json.loads(row["prerequisites_json"])],
            procedures=[ProcedureStep.model_validate(p) for p in json.loads(row["procedures_json"])],
            validation_steps=json.loads(row["validation_steps_json"]),
            expected_outcomes=json.loads(row["expected_outcomes_json"]),
            evaluation_summary=json.loads(row["evaluation_summary_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class CheckpointRepository:
    """Persistence operations for Git, DB, and Profile checkpoints."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def create(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        """Store a new checkpoint audit entry."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (id, checkpoint_type, reference, summary, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    checkpoint.id,
                    checkpoint.checkpoint_type.value,
                    checkpoint.reference,
                    checkpoint.summary,
                    json.dumps(checkpoint.details),
                    checkpoint.created_at.isoformat(),
                ),
            )
        return checkpoint

    def get_by_id(self, checkpoint_id: str) -> Optional[CheckpointRecord]:
        """Fetch checkpoint by ID."""
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM checkpoints WHERE id = ?;", (checkpoint_id,)).fetchone()
            if row:
                return self._row_to_checkpoint(row)
        return None

    def list_checkpoints(
        self,
        checkpoint_type: Optional[CheckpointType] = None,
        limit: int = 50,
    ) -> List[CheckpointRecord]:
        """List checkpoints ordered by creation time descending."""
        with self.db.session() as conn:
            query = "SELECT * FROM checkpoints"
            params: List[Any] = []
            if checkpoint_type:
                query += " WHERE checkpoint_type = ?"
                params.append(checkpoint_type.value)
            query += " ORDER BY created_at DESC LIMIT ?;"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_checkpoint(r) for r in rows]

    def delete(self, checkpoint_id: str) -> bool:
        """Remove a checkpoint record."""
        with self.db.session() as conn:
            cursor = conn.execute("DELETE FROM checkpoints WHERE id = ?;", (checkpoint_id,))
            return cursor.rowcount > 0

    def _row_to_checkpoint(self, row: sqlite3.Row) -> CheckpointRecord:
        return CheckpointRecord(
            id=row["id"],
            checkpoint_type=CheckpointType(row["checkpoint_type"]),
            reference=row["reference"],
            summary=row["summary"],
            details=json.loads(row["details_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class ScheduleRepository:
    """Persistence operations for persistent background scheduled jobs."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, job: ScheduledJob) -> ScheduledJob:
        """Save or update a scheduled job."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO scheduled_jobs (
                    id, name, job_type, schedule_expr, next_run_at, last_run_at,
                    last_status, params_json, enabled, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    job_type = excluded.job_type,
                    schedule_expr = excluded.schedule_expr,
                    next_run_at = excluded.next_run_at,
                    last_run_at = excluded.last_run_at,
                    last_status = excluded.last_status,
                    params_json = excluded.params_json,
                    enabled = excluded.enabled;
                """,
                (
                    job.id,
                    job.name,
                    job.job_type.value,
                    job.schedule_expr,
                    job.next_run_at.isoformat(),
                    job.last_run_at.isoformat() if job.last_run_at else None,
                    job.last_status,
                    json.dumps(job.params),
                    1 if job.enabled else 0,
                    job.created_at.isoformat(),
                ),
            )
        return job

    def get_by_id(self, job_id: str) -> Optional[ScheduledJob]:
        """Fetch scheduled job by ID."""
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM scheduled_jobs WHERE id = ?;", (job_id,)).fetchone()
            if row:
                return self._row_to_job(row)
        return None

    def get_by_name(self, name: str) -> Optional[ScheduledJob]:
        """Fetch scheduled job by name."""
        with self.db.session() as conn:
            row = conn.execute("SELECT * FROM scheduled_jobs WHERE name = ?;", (name,)).fetchone()
            if row:
                return self._row_to_job(row)
        return None

    def list_jobs(self, enabled_only: bool = False) -> List[ScheduledJob]:
        """List all scheduled jobs."""
        with self.db.session() as conn:
            query = "SELECT * FROM scheduled_jobs"
            params: List[Any] = []
            if enabled_only:
                query += " WHERE enabled = 1"
            query += " ORDER BY next_run_at ASC;"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_job(r) for r in rows]

    def list_due_jobs(self, as_of: datetime) -> List[ScheduledJob]:
        """List enabled jobs whose next_run_at is earlier than or equal to as_of."""
        with self.db.session() as conn:
            rows = conn.execute(
                """
                SELECT * FROM scheduled_jobs
                WHERE enabled = 1 AND next_run_at <= ?
                ORDER BY next_run_at ASC;
                """,
                (as_of.isoformat(),),
            ).fetchall()
            return [self._row_to_job(r) for r in rows]

    def delete(self, job_id: str) -> bool:
        """Delete a scheduled job."""
        with self.db.session() as conn:
            cursor = conn.execute("DELETE FROM scheduled_jobs WHERE id = ?;", (job_id,))
            return cursor.rowcount > 0

    def _row_to_job(self, row: sqlite3.Row) -> ScheduledJob:
        return ScheduledJob(
            id=row["id"],
            name=row["name"],
            job_type=JobType(row["job_type"]),
            schedule_expr=row["schedule_expr"],
            next_run_at=datetime.fromisoformat(row["next_run_at"]),
            last_run_at=datetime.fromisoformat(row["last_run_at"]) if row["last_run_at"] else None,
            last_status=row["last_status"],
            params=json.loads(row["params_json"]),
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

