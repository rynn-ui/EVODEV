"""Unit tests for EvoDev core data models."""

from datetime import datetime, timezone
import pytest

from evodev.models.events import (
    EventType,
    TaskStartedEvent,
    ToolInvokedEvent,
    ToolResultEvent,
    ErrorObservedEvent,
    TestExecutedEvent,
    TaskFinishedEvent,
)
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
from evodev.models.profile import ProfileManifest, ProfilePackage, ProfileStats


def test_task_started_event():
    event = TaskStartedEvent(
        session_id="s1",
        task_id="t1",
        project_id="p1",
        task_description="Fix null pointer exception in AuthManager",
        domain="mobile",
        languages=["kotlin"],
        frameworks=["android"],
    )
    assert event.event_type == EventType.TASK_STARTED
    assert event.domain == "mobile"
    assert "kotlin" in event.languages


def test_strategy_record_bayesian_update():
    strat = StrategyRecord(
        profile_id="default",
        name="retry_with_backoff",
        category="network",
    )
    # Default score (0 attempts) -> 0.5
    assert strat.update_score() == 0.5

    # 1 success -> (1 + 1) / (1 + 2) = 2/3 = ~0.666
    strat.attempts_count = 1
    strat.success_count = 1
    score = strat.update_score()
    assert 0.65 < score < 0.70

    # 3 successes, 0 failures -> (3 + 1) / (3 + 2) = 4/5 = 0.8
    strat.attempts_count = 3
    strat.success_count = 3
    score = strat.update_score()
    assert abs(score - 0.8) < 0.05

    # 1 regression -> penalty should reduce score significantly
    strat.regression_count = 1
    penalized_score = strat.update_score()
    assert penalized_score < score


def test_lesson_model():
    lesson = Lesson(
        profile_id="p-android",
        title="Compose mutableStateOf require remember block",
        trigger_pattern=r"Reading a state that was created with mutableStateOf",
        context_conditions={"domain": "mobile", "languages": ["kotlin"], "frameworks": ["compose"]},
        recommended_strategy="Wrap mutableStateOf inside remember { ... } to preserve state across recompositions",
        anti_patterns=["Creating naked mutableStateOf in composable function body"],
        confidence=0.92,
        epistemic_type=EpistemicType.VERIFIED_FACT,
        scope=KnowledgeScope.TECHNOLOGY,
        evidence=[
            VerificationEvidence(
                verification_type="test",
                passed=True,
                total_tests=5,
                passed_tests=5,
                failed_tests=0,
            )
        ],
    )
    assert lesson.confidence == 0.92
    assert lesson.epistemic_type == EpistemicType.VERIFIED_FACT
    assert lesson.scope == KnowledgeScope.TECHNOLOGY
    assert len(lesson.evidence) == 1
    assert lesson.evidence[0].passed is True


def test_profile_package_serialization():
    manifest = ProfileManifest(
        name="AndroidExpert.vxp",
        version="1.0.0",
        description="Android production patterns and fixes",
        domains=["mobile"],
        technologies=["android", "kotlin", "compose"],
    )
    pkg = ProfilePackage(
        manifest=manifest,
        lessons=[],
        strategies=[],
        preferences={"test_runner": "gradle"},
    )
    json_str = pkg.model_dump_json()
    assert "AndroidExpert.vxp" in json_str

    deserialized = ProfilePackage.model_validate_json(json_str)
    assert deserialized.manifest.name == "AndroidExpert.vxp"
    assert deserialized.preferences["test_runner"] == "gradle"
