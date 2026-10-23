"""Multi-factor relevance ranker with strict cross-project data isolation."""

from datetime import datetime, timezone
import re
from typing import List, Optional, Tuple

from evodev.models.experience import KnowledgeScope, Lesson


class MultiFactorRanker:
    """Scores candidate lessons against incoming task context across 6 dimensions."""

    def __init__(
        self,
        weight_scope: float = 0.25,
        weight_tech: float = 0.25,
        weight_domain: float = 0.15,
        weight_problem: float = 0.25,
        weight_confidence: float = 0.10,
    ):
        self.w_scope = weight_scope
        self.w_tech = weight_tech
        self.w_domain = weight_domain
        self.w_problem = weight_problem
        self.w_confidence = weight_confidence

    def calculate_score(
        self,
        lesson: Lesson,
        target_project_id: str,
        target_task_description: str,
        target_domain: str = "general",
        target_technologies: Optional[List[str]] = None,
    ) -> float:
        """Calculate normalized relevance score (0.0 to 1.0) or -1.0 if strictly excluded."""
        target_technologies = target_technologies or []

        # 1. Strict Privacy & Scope Isolation Guard:
        # A project-specific lesson must NEVER leak to an unrelated project.
        if lesson.scope == KnowledgeScope.PROJECT:
            if target_project_id not in lesson.provenance.origin_project_ids:
                return -1.0  # Absolute exclusion

        # Scope Match Factor
        s_scope = self._score_scope(lesson.scope)

        # Technology Match Factor (Jaccard similarity)
        s_tech, has_tech_mismatch = self._score_tech(lesson.context_conditions, target_technologies)

        # Domain Match Factor
        lesson_domain = lesson.context_conditions.get("domain", "general")
        has_domain_mismatch = False
        if lesson_domain == target_domain and target_domain != "general":
            s_domain = 1.0
        elif target_domain != "general" and lesson_domain != "general" and lesson_domain != target_domain:
            s_domain = 0.0
            has_domain_mismatch = True
        else:
            s_domain = 0.3

        # Problem Keyword Overlap Factor
        s_problem = self._score_problem_overlap(lesson.trigger_pattern, target_task_description)

        # Confidence Factor
        s_confidence = lesson.confidence

        # Combined weighted score
        raw_score = (
            self.w_scope * s_scope
            + self.w_tech * s_tech
            + self.w_domain * s_domain
            + self.w_problem * s_problem
            + self.w_confidence * s_confidence
        )

        # Severe penalty if both domain AND technology are completely incompatible
        if has_domain_mismatch and has_tech_mismatch:
            raw_score -= 0.30

        # Recency decay (slight dampening for lessons older than 90 days)
        age_days = (datetime.now(timezone.utc) - lesson.updated_at).days
        decay = max(0.85, 1.0 - (age_days * 0.001))

        return max(0.0, min(1.0, raw_score * decay))

    @staticmethod
    def _score_scope(scope: KnowledgeScope) -> float:
        if scope == KnowledgeScope.PREFERENCES:
            return 1.0
        elif scope == KnowledgeScope.TECHNOLOGY:
            return 0.95
        elif scope == KnowledgeScope.DOMAIN:
            return 0.85
        elif scope == KnowledgeScope.GLOBAL:
            return 0.80
        elif scope == KnowledgeScope.PROJECT:
            return 0.90
        return 0.50

    @staticmethod
    def _score_tech(context: dict, target_techs: List[str]) -> Tuple[float, bool]:
        if not target_techs:
            return 0.5, False  # Neutral if target techs unspecified

        lesson_techs = set()
        for t in context.get("languages", []):
            lesson_techs.add(t.lower())
        for t in context.get("frameworks", []):
            lesson_techs.add(t.lower())

        if not lesson_techs:
            return 0.3, False

        target_set = {t.lower() for t in target_techs}
        intersection = lesson_techs.intersection(target_set)
        if not intersection:
            return 0.0, True

        return len(intersection) / float(len(lesson_techs.union(target_set))), False

    @staticmethod
    def _score_problem_overlap(trigger_pattern: str, task_description: str) -> float:
        words_trigger = set(re.findall(r"\b\w{4,}\b", trigger_pattern.lower()))
        words_task = set(re.findall(r"\b\w{4,}\b", task_description.lower()))

        if not words_trigger or not words_task:
            return 0.2

        intersection = words_trigger.intersection(words_task)
        if not intersection:
            return 0.05

        return min(1.0, len(intersection) / float(min(len(words_trigger), 5)))
