"""Event normalizer that transforms raw agent signals into sanitized, typed EvoDev events."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

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
from evodev.security.redactor import SecretRedactor


class EventNormalizer:
    """Sanitizes and maps raw event payloads into canonical EvoDev events."""

    def __init__(self, redactor: Optional[SecretRedactor] = None):
        self.redactor = redactor or SecretRedactor()

    def normalize(self, raw_data: Dict[str, Any]) -> NormalizedEvent:
        """Parse raw event dictionary and return appropriate NormalizedEvent subclass."""
        event_type_str = raw_data.get("event_type", "").lower()
        session_id = raw_data.get("session_id", "default-session")
        task_id = raw_data.get("task_id", str(uuid.uuid4()))
        project_id = raw_data.get("project_id", "global")
        event_id = raw_data.get("id", str(uuid.uuid4()))

        # Extract timestamp
        ts = raw_data.get("timestamp")
        if isinstance(ts, str):
            try:
                timestamp = datetime.fromisoformat(ts)
            except Exception:
                timestamp = datetime.now(timezone.utc)
        elif isinstance(ts, datetime):
            timestamp = ts
        else:
            timestamp = datetime.now(timezone.utc)

        # 1. TASK_STARTED
        if event_type_str == EventType.TASK_STARTED.value:
            return TaskStartedEvent(
                id=event_id,
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                timestamp=timestamp,
                task_description=self.redactor.redact_text(raw_data.get("task_description", "")),
                domain=raw_data.get("domain", "general"),
                languages=raw_data.get("languages", []),
                frameworks=raw_data.get("frameworks", []),
                git_branch=raw_data.get("git_branch"),
                git_commit=raw_data.get("git_commit"),
            )

        # 2. TOOL_INVOKED
        elif event_type_str == EventType.TOOL_INVOKED.value:
            raw_args = raw_data.get("arguments", {})
            return ToolInvokedEvent(
                id=event_id,
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                timestamp=timestamp,
                tool_name=raw_data.get("tool_name", "unknown_tool"),
                call_id=raw_data.get("call_id"),
                arguments=self.redactor.redact_data(raw_args),
            )

        # 3. TOOL_RESULT
        elif event_type_str == EventType.TOOL_RESULT.value:
            stdout = raw_data.get("stdout")
            stderr = raw_data.get("stderr")
            error = raw_data.get("error")
            return ToolResultEvent(
                id=event_id,
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                timestamp=timestamp,
                tool_name=raw_data.get("tool_name", "unknown_tool"),
                call_id=raw_data.get("call_id"),
                exit_code=raw_data.get("exit_code", 0),
                stdout=self.redactor.redact_text(stdout) if stdout else None,
                stderr=self.redactor.redact_text(stderr) if stderr else None,
                error=self.redactor.redact_text(error) if error else None,
                duration_ms=raw_data.get("duration_ms"),
            )

        # 4. ERROR_OBSERVED
        elif event_type_str == EventType.ERROR_OBSERVED.value:
            return ErrorObservedEvent(
                id=event_id,
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                timestamp=timestamp,
                error_type=raw_data.get("error_type", "RuntimeError"),
                error_message=self.redactor.redact_text(raw_data.get("error_message", "")),
                stack_trace=self.redactor.redact_text(raw_data.get("stack_trace", ""))
                if raw_data.get("stack_trace")
                else None,
                file_path=raw_data.get("file_path"),
                line_number=raw_data.get("line_number"),
            )

        # 5. TEST_EXECUTED
        elif event_type_str == EventType.TEST_EXECUTED.value:
            summary = raw_data.get("failures_summary")
            return TestExecutedEvent(
                id=event_id,
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                timestamp=timestamp,
                test_command=raw_data.get("test_command", "test"),
                total_tests=raw_data.get("total_tests", 0),
                passed_tests=raw_data.get("passed_tests", 0),
                failed_tests=raw_data.get("failed_tests", 0),
                skipped_tests=raw_data.get("skipped_tests", 0),
                duration_seconds=raw_data.get("duration_seconds"),
                failures_summary=self.redactor.redact_text(summary) if summary else None,
            )

        # 6. VERIFICATION_RECORDED
        elif event_type_str == EventType.VERIFICATION_RECORDED.value:
            details = raw_data.get("details")
            return VerificationRecordedEvent(
                id=event_id,
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                timestamp=timestamp,
                verification_type=raw_data.get("verification_type", "test"),
                passed=raw_data.get("passed", True),
                score=raw_data.get("score", 1.0),
                details=self.redactor.redact_text(details) if details else None,
            )

        # 7. TASK_FINISHED
        elif event_type_str == EventType.TASK_FINISHED.value:
            summary = raw_data.get("summary")
            return TaskFinishedEvent(
                id=event_id,
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                timestamp=timestamp,
                outcome=raw_data.get("outcome", "success"),
                duration_ms=raw_data.get("duration_ms"),
                changed_files=raw_data.get("changed_files", []),
                summary=self.redactor.redact_text(summary) if summary else None,
            )

        # 8. USER_FEEDBACK
        elif event_type_str == EventType.USER_FEEDBACK.value:
            fb = raw_data.get("feedback_text")
            return UserFeedbackEvent(
                id=event_id,
                session_id=session_id,
                task_id=task_id,
                project_id=project_id,
                timestamp=timestamp,
                rating=raw_data.get("rating", "positive"),
                feedback_text=self.redactor.redact_text(fb) if fb else None,
                correction_applied=raw_data.get("correction_applied", False),
            )

        # Fallback to generic NormalizedEvent
        return NormalizedEvent(
            id=event_id,
            session_id=session_id,
            task_id=task_id,
            project_id=project_id,
            event_type=EventType.TASK_STARTED,
            timestamp=timestamp,
            metadata=self.redactor.redact_data(raw_data),
        )
