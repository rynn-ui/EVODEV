"""Collector service managing active sessions, event routing, and experience record construction."""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import uuid

from evodev.collector.normalizer import EventNormalizer
from evodev.models.events import (
    ErrorObservedEvent,
    EventType,
    NormalizedEvent,
    TaskFinishedEvent,
    TaskStartedEvent,
    TestExecutedEvent,
    ToolInvokedEvent,
    ToolResultEvent,
    UserFeedbackEvent,
    VerificationRecordedEvent,
)
from evodev.models.experience import (
    ExperienceRecord,
    VerificationEvidence,
)
from evodev.storage.repositories import (
    EventRepository,
    ExperienceRepository,
    ProfileRepository,
)


class SessionState:
    """In-memory state accumulator for an in-flight developer task."""

    def __init__(self, session_id: str, task_id: str, project_id: str):
        self.session_id = session_id
        self.task_id = task_id
        self.project_id = project_id
        self.domain = "general"
        self.languages: List[str] = []
        self.frameworks: List[str] = []
        self.task_description = ""
        self.errors: List[str] = []
        self.tool_invocations: List[Dict[str, Any]] = []
        self.tests: List[TestExecutedEvent] = []
        self.verification: Optional[VerificationEvidence] = None
        self.user_feedback: Optional[str] = None
        self.changed_files: List[str] = []
        self.start_time: datetime = datetime.now(timezone.utc)


class CollectorService:
    """Central event ingestion pipeline and experience session coordinator."""

    def __init__(
        self,
        event_repo: EventRepository,
        experience_repo: ExperienceRepository,
        profile_repo: ProfileRepository,
        normalizer: Optional[EventNormalizer] = None,
        on_task_finished_callback: Optional[Callable[[ExperienceRecord], None]] = None,
    ):
        self.event_repo = event_repo
        self.experience_repo = experience_repo
        self.profile_repo = profile_repo
        self.normalizer = normalizer or EventNormalizer()
        self.on_task_finished = on_task_finished_callback
        self._active_sessions: Dict[str, SessionState] = {}

    def ingest_raw_event(self, raw_data: Dict[str, Any]) -> NormalizedEvent:
        """Normalize raw payload, persist event, and update session state."""
        event = self.normalizer.normalize(raw_data)
        return self.ingest_event(event)

    def ingest_event(self, event: NormalizedEvent) -> NormalizedEvent:
        """Route normalized event to storage and update internal session accumulator."""
        # 1. Persist raw normalized event for audit/replay
        self.event_repo.save(event)

        # 2. Update active session buffer
        session = self._get_or_create_session(event.session_id, event.task_id, event.project_id)

        if isinstance(event, TaskStartedEvent):
            session.task_description = event.task_description
            session.domain = event.domain or "general"
            session.languages = event.languages
            session.frameworks = event.frameworks

        elif isinstance(event, ToolInvokedEvent):
            session.tool_invocations.append({
                "tool_name": event.tool_name,
                "call_id": event.call_id,
                "arguments": event.arguments,
                "timestamp": event.timestamp.isoformat(),
            })

        elif isinstance(event, ToolResultEvent):
            if event.error or (event.exit_code != 0 and event.stderr):
                err_msg = event.error or event.stderr or f"Tool exit {event.exit_code}"
                if err_msg not in session.errors:
                    session.errors.append(err_msg)

        elif isinstance(event, ErrorObservedEvent):
            full_err = f"{event.error_type}: {event.error_message}"
            if full_err not in session.errors:
                session.errors.append(full_err)

        elif isinstance(event, TestExecutedEvent):
            session.tests.append(event)
            passed = event.failed_tests == 0 and event.total_tests > 0
            session.verification = VerificationEvidence(
                verification_type="test",
                passed=passed,
                confidence_score=1.0 if passed else 0.0,
                total_tests=event.total_tests,
                passed_tests=event.passed_tests,
                failed_tests=event.failed_tests,
                evidence_snippet=event.failures_summary if not passed else "All tests passed",
            )

        elif isinstance(event, VerificationRecordedEvent):
            session.verification = VerificationEvidence(
                verification_type=event.verification_type,
                passed=event.passed,
                confidence_score=event.score,
                evidence_snippet=event.details,
            )

        elif isinstance(event, UserFeedbackEvent):
            session.user_feedback = event.feedback_text
            if event.rating == "positive" and not session.verification:
                session.verification = VerificationEvidence(
                    verification_type="human",
                    passed=True,
                    confidence_score=0.9,
                    human_confirmed=True,
                )

        elif isinstance(event, TaskFinishedEvent):
            session.changed_files = event.changed_files
            self._finalize_task(session, event)

        return event

    def _get_or_create_session(
        self, session_id: str, task_id: str, project_id: str
    ) -> SessionState:
        """Fetch or initialize session accumulator."""
        key = f"{session_id}:{task_id}"
        if key not in self._active_sessions:
            self._active_sessions[key] = SessionState(session_id, task_id, project_id)
        return self._active_sessions[key]

    def _finalize_task(self, session: SessionState, finish_event: TaskFinishedEvent) -> None:
        """Synthesize ExperienceRecord, persist it, and invoke callback for learning engine."""
        active_profile = self.profile_repo.get_active()
        profile_id = active_profile.profile_id if active_profile else "default"

        # Extract attempted strategy names from tool invocations
        strategies = list({t["tool_name"] for t in session.tool_invocations})

        record = ExperienceRecord(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            session_id=session.session_id,
            task_id=session.task_id,
            project_id=session.project_id,
            domain=session.domain,
            languages=session.languages,
            frameworks=session.frameworks,
            initial_problem=session.task_description or "Unspecified development task",
            strategies_attempted=strategies,
            tool_invocations_summary=session.tool_invocations,
            errors_observed=session.errors,
            file_changes=session.changed_files,
            verification=session.verification,
            outcome=finish_event.outcome,
            user_feedback=session.user_feedback,
            created_at=datetime.now(timezone.utc),
        )

        # 1. Save experience record
        self.experience_repo.save(record)

        # 2. Dispatch to downstream learning engine if configured
        if self.on_task_finished:
            try:
                self.on_task_finished(record)
            except Exception:
                pass

        # 3. Clean up active session
        key = f"{session.session_id}:{session.task_id}"
        self._active_sessions.pop(key, None)
