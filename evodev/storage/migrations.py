"""Schema migration management for SQLite database."""

from datetime import datetime, timezone
import sqlite3
from typing import Callable, Dict, List

from evodev.storage.db import DatabaseManager


class MigrationManager:
    """Applies versioned schema migrations sequentially to ensure consistent data structure."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def init_migration_table(self, conn: sqlite3.Connection) -> None:
        """Create the schema_migrations tracking table if absent."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL
            );
        """)

    def get_applied_versions(self, conn: sqlite3.Connection) -> List[int]:
        """Fetch list of already applied migration numbers."""
        self.init_migration_table(conn)
        cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        return [row[0] for row in cursor.fetchall()]

    def run_migrations(self) -> int:
        """Run all outstanding migrations in order. Returns count of migrations applied."""
        applied_count = 0
        with self.db.session() as conn:
            applied = set(self.get_applied_versions(conn))
            migrations = self._get_migrations()

            for version in sorted(migrations.keys()):
                if version not in applied:
                    migration_fn = migrations[version]
                    migration_fn(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?);",
                        (version, datetime.now(timezone.utc).isoformat()),
                    )
                    applied_count += 1
        return applied_count

    def _get_migrations(self) -> Dict[int, Callable[[sqlite3.Connection], None]]:
        """Dictionary of version numbers to migration functions."""
        return {
            1: self._migration_v1_initial_schema,
            2: self._migration_v2_memories_skills_checkpoints_schedules,
        }

    def _migration_v1_initial_schema(self, conn: sqlite3.Connection) -> None:
        """Initial database schema for EvoDev experience, lessons, profiles, and events."""
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                manifest_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profile_versions (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                version TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                message TEXT NOT NULL,
                package_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS experiences (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                languages_json TEXT NOT NULL,
                frameworks_json TEXT NOT NULL,
                initial_problem TEXT NOT NULL,
                outcome TEXT NOT NULL,
                verification_json TEXT,
                raw_record_json TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                trigger_pattern TEXT NOT NULL,
                context_conditions_json TEXT NOT NULL,
                recommended_strategy TEXT NOT NULL,
                anti_patterns_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                epistemic_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                attempts_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                regression_count INTEGER NOT NULL DEFAULT 0,
                bayesian_score REAL NOT NULL DEFAULT 0.5,
                avg_duration_seconds REAL NOT NULL DEFAULT 0.0,
                last_attempted_at TIMESTAMP NOT NULL,
                UNIQUE(profile_id, name)
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS benchmarks (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                suite_name TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                details_json TEXT NOT NULL,
                recorded_at TIMESTAMP NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_experiences_project ON experiences(project_id);
            CREATE INDEX IF NOT EXISTS idx_experiences_profile ON experiences(profile_id);
            CREATE INDEX IF NOT EXISTS idx_lessons_scope ON lessons(profile_id, scope);
            CREATE INDEX IF NOT EXISTS idx_lessons_active ON lessons(is_active);
            CREATE INDEX IF NOT EXISTS idx_strategies_profile ON strategies(profile_id);
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
            CREATE INDEX IF NOT EXISTS idx_profile_versions ON profile_versions(profile_id, version);
        """)

    def _migration_v2_memories_skills_checkpoints_schedules(self, conn: sqlite3.Connection) -> None:
        """Schema for persistent memories, self-improving skills, safe checkpoints, and background scheduler."""
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content_json TEXT NOT NULL,
                scope TEXT NOT NULL,
                project_id TEXT,
                confidence REAL NOT NULL DEFAULT 1.0,
                epistemic_type TEXT NOT NULL DEFAULT 'verified_fact',
                provenance_json TEXT NOT NULL DEFAULT '{}',
                evidence_json TEXT NOT NULL DEFAULT '[]',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                current_version TEXT NOT NULL DEFAULT '1.0.0',
                status TEXT NOT NULL DEFAULT 'draft',
                scope TEXT NOT NULL DEFAULT 'domain',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                UNIQUE(profile_id, name)
            );

            CREATE TABLE IF NOT EXISTS skill_versions (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                version TEXT NOT NULL,
                instructions TEXT NOT NULL,
                prerequisites_json TEXT NOT NULL DEFAULT '[]',
                procedures_json TEXT NOT NULL DEFAULT '[]',
                validation_steps_json TEXT NOT NULL DEFAULT '[]',
                expected_outcomes_json TEXT NOT NULL DEFAULT '[]',
                evaluation_summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL,
                UNIQUE(skill_id, version)
            );

            CREATE TABLE IF NOT EXISTS skill_evaluations (
                id TEXT PRIMARY KEY,
                skill_version_id TEXT NOT NULL REFERENCES skill_versions(id) ON DELETE CASCADE,
                task_id TEXT NOT NULL,
                benchmark_id TEXT,
                passed INTEGER NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                evaluated_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                checkpoint_type TEXT NOT NULL,
                reference TEXT NOT NULL,
                summary TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                job_type TEXT NOT NULL,
                schedule_expr TEXT NOT NULL,
                next_run_at TIMESTAMP NOT NULL,
                last_run_at TIMESTAMP,
                last_status TEXT,
                params_json TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_profile_cat ON memories(profile_id, category);
            CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
            CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
            CREATE INDEX IF NOT EXISTS idx_skills_profile ON skills(profile_id);
            CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id);
            CREATE INDEX IF NOT EXISTS idx_skill_evals_ver ON skill_evaluations(skill_version_id);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_type ON checkpoints(checkpoint_type);
            CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next ON scheduled_jobs(enabled, next_run_at);
        """)

