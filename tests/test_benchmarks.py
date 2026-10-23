"""Unit tests for the benchmark evaluation framework."""

import pytest

from evodev.evaluation.benchmark import BenchmarkSuiteRunner
from evodev.models.experience import KnowledgeScope, Lesson, Provenance
from evodev.models.profile import ProfileManifest
from evodev.retrieval.engine import RetrievalEngine
from evodev.retrieval.ranker import MultiFactorRanker
from evodev.storage.db import DatabaseManager
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import BenchmarkRepository, LessonRepository, ProfileRepository


def test_benchmark_suite_proves_measurable_improvement():
    db = DatabaseManager(":memory:")
    migrator = MigrationManager(db)
    migrator.run_migrations()

    p_repo = ProfileRepository(db)
    l_repo = LessonRepository(db)
    b_repo = BenchmarkRepository(db)

    # 1. Base Agent Benchmark (Empty profile / 0 experience)
    manifest = ProfileManifest(name="FreshProfile", version="1.0.0")
    p_repo.create(manifest, is_active=True)

    ranker = MultiFactorRanker()
    engine = RetrievalEngine(l_repo, p_repo, ranker)
    runner = BenchmarkSuiteRunner(engine, b_repo)

    base_metrics = runner.run_suite(
        suite_name="standard_dev_challenges",
        profile_id=manifest.profile_id,
        agent_mode="base_agent",
    )
    # Base agent with no prior experience falls into pitfall solutions
    assert base_metrics.success_rate == 0.0
    assert base_metrics.total_tasks == 3
    assert base_metrics.regressed_tasks == 3

    # 2. Teach EvoDev by adding verified lessons for the challenges
    l1 = Lesson(
        profile_id=manifest.profile_id,
        title="Android Compose SDK version",
        trigger_pattern="Compose compiler requires compileSdkVersion 34",
        context_conditions={"domain": "mobile", "technologies": ["android", "compose"]},
        recommended_strategy="Apply update_gradle_compile_sdk to match minimum requirements",
        anti_patterns=["ignore_compiler_warning_and_downgrade"],
        scope=KnowledgeScope.TECHNOLOGY,
        provenance=Provenance(origin_project_ids=["p1"]),
        confidence=0.95,
    )
    l2 = Lesson(
        profile_id=manifest.profile_id,
        title="FastAPI SQLAlchemy Pool Exhaustion",
        trigger_pattern="QueuePool limit reached connection timed out",
        context_conditions={"domain": "backend", "technologies": ["python", "sqlalchemy"]},
        recommended_strategy="Apply configure_pooled_engine_with_overflow_and_recycle",
        anti_patterns=["create_new_engine_per_request"],
        scope=KnowledgeScope.TECHNOLOGY,
        provenance=Provenance(origin_project_ids=["p2"]),
        confidence=0.95,
    )
    l3 = Lesson(
        profile_id=manifest.profile_id,
        title="React stale closure in interval",
        trigger_pattern="State variable in setInterval callback retains initial value",
        context_conditions={"domain": "web", "technologies": ["react"]},
        recommended_strategy="Apply use_functional_state_updater_or_useRef",
        anti_patterns=["add_empty_dependency_array"],
        scope=KnowledgeScope.TECHNOLOGY,
        provenance=Provenance(origin_project_ids=["p3"]),
        confidence=0.95,
    )
    l_repo.save_many([l1, l2, l3])

    # 3. Re-run benchmark with EvoDev experience enabled
    experienced_metrics = runner.run_suite(
        suite_name="standard_dev_challenges",
        profile_id=manifest.profile_id,
        agent_mode="evodev_experienced",
    )

    # Measured improvement: 100% success rate on the benchmark challenges!
    assert experienced_metrics.success_rate == 1.0
    assert experienced_metrics.passed_tasks == 3
    assert experienced_metrics.regressed_tasks == 0
    assert experienced_metrics.repeated_error_frequency == 0.0

    # Verify benchmark metrics were persisted to database
    stored_benchmarks = b_repo.get_metrics(manifest.profile_id)
    assert len(stored_benchmarks) >= 2
