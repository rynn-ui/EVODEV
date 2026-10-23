"""Generic adapter interface for third-party AI coding agents and IDEs."""

from typing import Any, Dict, List, Optional

from evodev.collector.collector_service import CollectorService
from evodev.connectors.base import BaseAgentConnector
from evodev.retrieval.context_assembler import ContextAssembler
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.repositories import LessonRepository, ProfileRepository


class GenericAdapter(BaseAgentConnector):
    """Universal adapter supporting REST or IPC communication with any IDE or agent."""

    def __init__(
        self,
        collector: CollectorService,
        lesson_repo: LessonRepository,
        profile_repo: ProfileRepository,
    ):
        self.collector = collector
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.engine = RetrievalEngine(lesson_repo, profile_repo)
        self.assembler = ContextAssembler()

    def get_name(self) -> str:
        return "GenericAdapter"

    def is_available(self) -> bool:
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.get_name(),
            "available": True,
            "interfaces": ["REST", "JSON-IPC", "CLI"],
        }

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def assemble_context(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
    ) -> str:
        scored = self.engine.retrieve_relevant_lessons(
            task_description=task_description,
            project_id=project_id,
            domain=domain,
            technologies=technologies,
        )
        active_p = self.profile_repo.get_active()
        p_name = active_p.name if active_p else "Default"
        return self.assembler.assemble(scored, profile_name=p_name)

    def query_context(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return structured lessons and raw score data."""
        scored = self.engine.retrieve_relevant_lessons(
            task_description=task_description,
            project_id=project_id,
            domain=domain,
            technologies=technologies,
        )
        active_p = self.profile_repo.get_active()
        p_name = active_p.name if active_p else "Default"

        return {
            "profile_name": p_name,
            "formatted_advisory": self.assembler.assemble(scored, profile_name=p_name),
            "lessons": [
                {
                    "title": l.title,
                    "score": round(score, 3),
                    "scope": l.scope.value,
                    "recommendation": l.recommended_strategy,
                    "anti_patterns": l.anti_patterns,
                    "confidence": l.confidence,
                }
                for l, score in scored
            ],
        }

    def send_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest raw event from an external agent or hook."""
        normalized = self.collector.ingest_raw_event(raw_event)
        return {"status": "ok", "event_id": normalized.id, "event_type": normalized.event_type.value}
