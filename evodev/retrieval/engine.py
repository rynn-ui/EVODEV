"""Retrieval engine for querying and ranking accumulated lessons for an active task."""

from typing import List, Optional, Tuple

from evodev.models.experience import Lesson
from evodev.retrieval.ranker import MultiFactorRanker
from evodev.storage.repositories import LessonRepository, ProfileRepository


class RetrievalEngine:
    """Queries candidate lessons from active profile and ranks them by task relevance."""

    def __init__(
        self,
        lesson_repo: LessonRepository,
        profile_repo: ProfileRepository,
        ranker: Optional[MultiFactorRanker] = None,
    ):
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.ranker = ranker or MultiFactorRanker()

    def retrieve_relevant_lessons(
        self,
        task_description: str,
        project_id: str,
        domain: str = "general",
        technologies: Optional[List[str]] = None,
        profile_id: Optional[str] = None,
        min_score: float = 0.35,
        limit: int = 5,
    ) -> List[Tuple[Lesson, float]]:
        """Retrieve top-K ranked lessons meeting minimum score threshold."""
        # Resolve active profile if not passed explicitly
        if not profile_id:
            active_manifest = self.profile_repo.get_active()
            profile_id = active_manifest.profile_id if active_manifest else "default"

        all_lessons = self.lesson_repo.list_by_profile(profile_id, active_only=True)
        scored_lessons: List[Tuple[Lesson, float]] = []

        for lesson in all_lessons:
            score = self.ranker.calculate_score(
                lesson=lesson,
                target_project_id=project_id,
                target_task_description=task_description,
                target_domain=domain,
                target_technologies=technologies,
            )
            # If excluded by privacy guard (score < 0) or below threshold, omit
            if score >= min_score:
                scored_lessons.append((lesson, score))

        # Sort descending by score
        scored_lessons.sort(key=lambda x: x[1], reverse=True)
        return scored_lessons[:limit]
