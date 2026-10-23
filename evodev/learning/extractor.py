"""Lesson extractor: Distills reusable lessons from verified development workflows."""

from datetime import datetime, timezone
import re
from typing import List, Optional
import uuid

from evodev.config import EvoDevConfig, load_config
from evodev.models.experience import (
    EpistemicType,
    ExperienceRecord,
    KnowledgeScope,
    Lesson,
    Provenance,
    VerificationEvidence,
)
from evodev.security.redactor import SecretRedactor
from evodev.security.validator import ProfileValidator


class LessonExtractor:
    """Extracts candidate lessons and anti-patterns with verification evidence."""

    def __init__(self, config: Optional[EvoDevConfig] = None):
        self.config = config or load_config()
        self.validator = ProfileValidator(self.config)
        self.redactor = SecretRedactor()

    def extract_lessons(self, record: ExperienceRecord) -> List[Lesson]:
        """Examine an ExperienceRecord and extract verified lessons or anti-patterns."""
        # Verification Gate: The absence of an error is NOT proof of success.
        has_positive_evidence = (
            record.verification is not None and record.verification.passed is True
        ) or (
            record.outcome == "success" and record.user_feedback is not None
        )

        if not has_positive_evidence:
            # We do NOT extract positive reusable lessons from unverified or failing tasks
            return []

        lessons: List[Lesson] = []

        # Determine appropriate scope
        scope = self._infer_scope(record)

        # Determine epistemic type
        epistemic_type = self._infer_epistemic_type(record)

        # Extract failed strategies as anti-patterns
        anti_patterns = self._extract_anti_patterns(record)

        # Generate generalized title and recommendation
        title, recommendation, trigger = self._distill_recommendation(record)

        # Cleanse and sanitize
        title = self.validator.sanitize_lesson_text(title)
        recommendation = self.validator.sanitize_lesson_text(recommendation)
        trigger = self.validator.sanitize_lesson_text(trigger)

        # Build Provenance
        provenance = Provenance(
            origin_task_ids=[record.task_id],
            origin_project_ids=[record.project_id],
            first_observed_at=record.created_at,
            last_verified_at=record.created_at,
            verification_count=1,
            failure_count=0,
            regression_count=0,
        )

        evidence_list = []
        if record.verification:
            evidence_list.append(record.verification)

        lesson = Lesson(
            id=str(uuid.uuid4()),
            profile_id=record.profile_id,
            title=title,
            trigger_pattern=trigger,
            context_conditions={
                "domain": record.domain,
                "languages": record.languages,
                "frameworks": record.frameworks,
            },
            recommended_strategy=recommendation,
            anti_patterns=anti_patterns,
            confidence=0.85 if record.verification and record.verification.total_tests > 0 else 0.75,
            epistemic_type=epistemic_type,
            scope=scope,
            provenance=provenance,
            evidence=evidence_list,
            active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        lessons.append(lesson)
        return lessons

    def _infer_scope(self, record: ExperienceRecord) -> KnowledgeScope:
        """Infer scope: Global, Domain, Technology, Preferences, or Project."""
        if record.user_feedback and any(w in record.user_feedback.lower() for w in ["always", "never", "prefer", "style"]):
            return KnowledgeScope.PREFERENCES

        # If language or framework is explicitly specified and no project-unique path is required
        if record.frameworks or record.languages:
            return KnowledgeScope.TECHNOLOGY

        if record.domain and record.domain != "general":
            return KnowledgeScope.DOMAIN

        # Fallback to project scope until multiple independent occurrences promote it
        return KnowledgeScope.PROJECT

    def _infer_epistemic_type(self, record: ExperienceRecord) -> EpistemicType:
        """Determine whether lesson represents a verified fact, user preference, or inferred lesson."""
        if record.user_feedback:
            return EpistemicType.USER_PREFERENCE

        if record.verification and record.verification.compiler_exit_code == 0:
            return EpistemicType.VERIFIED_FACT

        return EpistemicType.INFERRED_LESSON

    def _extract_anti_patterns(self, record: ExperienceRecord) -> List[str]:
        """Identify strategies or actions that resulted in errors before final resolution."""
        anti_patterns = []
        for error in record.errors_observed:
            clean_err = self._sanitize_paths(self.redactor.redact_text(error))
            if clean_err and clean_err not in anti_patterns:
                anti_patterns.append(f"Avoid triggering: {clean_err[:120]}")
        return anti_patterns

    def _distill_recommendation(self, record: ExperienceRecord) -> tuple[str, str, str]:
        """Distill title, actionable recommendation, and trigger pattern."""
        initial_prob = self._sanitize_paths(self.redactor.redact_text(record.initial_problem))
        title = f"Resolve: {initial_prob[:60]}"

        # Successful strategy summary
        successful_strategies = record.strategies_attempted
        strat_desc = ", ".join(successful_strategies) if successful_strategies else "standard fix"

        rec = f"When encountering '{initial_prob[:80]}', apply verified strategy: {strat_desc}."
        if record.file_changes:
            # Exclude private, test, and key files from recommended files
            safe_files = [
                f for f in record.file_changes
                if not any(ign in f.lower() for ign in ["secret", "key", "password", "token", ".env"])
            ]
            if safe_files:
                clean_files = [self._sanitize_paths(f) for f in safe_files]
                rec += f" Target configuration/source files: {', '.join(clean_files[:3])}."

        # Trigger pattern uses key terms from the problem
        trigger_terms = re.findall(r"\b[A-Za-z0-9_-]{4,}\b", initial_prob)
        trigger = " ".join(trigger_terms[:8]) if trigger_terms else initial_prob[:50]

        return title, rec, trigger

    @staticmethod
    def _sanitize_paths(text: str) -> str:
        """Strip user-specific absolute home directories from paths to ensure portability."""
        if not text:
            return ""
        # Strip Windows/Unix home directory prefixes
        text = re.sub(r"(?:[A-Za-z]:)?[/\\]Users[/\\][^/\\]+[/\\]", "", text)
        text = re.sub(r"/home/[^/]+/", "", text)
        return text.strip()
