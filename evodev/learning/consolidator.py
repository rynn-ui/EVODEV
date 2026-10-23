"""Experience consolidator: Deduplication, provenance merging, promotion, and conflict detection."""

from datetime import datetime, timezone
import re
from typing import List, Optional, Tuple

from evodev.config import EvoDevConfig, load_config
from evodev.models.experience import KnowledgeScope, Lesson
from evodev.storage.repositories import LessonRepository


class ExperienceConsolidator:
    """Manages lesson lifecycle: merging provenance, promoting scopes, and resolving conflicts."""

    def __init__(self, lesson_repo: LessonRepository, config: Optional[EvoDevConfig] = None):
        self.lesson_repo = lesson_repo
        self.config = config or load_config()

    def consolidate_lesson(self, new_lesson: Lesson) -> Lesson:
        """Consolidate a new candidate lesson with existing knowledge base."""
        existing_lessons = self.lesson_repo.list_by_profile(new_lesson.profile_id, active_only=False)

        # 1. First check for contradictions / conflicts with existing lessons
        conflicts = self._find_conflicts(existing_lessons, new_lesson)
        for old_lesson in conflicts:
            self._resolve_conflict(old_lesson, new_lesson)

        # 2. Search for non-contradictory duplicate lesson to merge provenance
        for existing in existing_lessons:
            if existing.active and self._is_duplicate(existing, new_lesson):
                # Ensure they don't have conflicting advice
                rec_new = new_lesson.recommended_strategy.lower()
                rec_old = existing.recommended_strategy.lower()
                is_conflicting = any(rec_new in ap.lower() for ap in existing.anti_patterns) or \
                                 any(rec_old in ap.lower() for ap in new_lesson.anti_patterns)
                if not is_conflicting:
                    return self._merge_provenance(existing, new_lesson)

        # 3. Check for scope promotion
        self._check_scope_promotion(new_lesson)

        # 4. Save consolidated lesson
        self.lesson_repo.save(new_lesson)
        return new_lesson

    def _is_duplicate(self, l1: Lesson, l2: Lesson) -> bool:
        """Check if two lessons address the same problem trigger and recommendation."""
        # Check title similarity or trigger overlap
        t1 = set(re.findall(r"\w{4,}", l1.trigger_pattern.lower()))
        t2 = set(re.findall(r"\w{4,}", l2.trigger_pattern.lower()))
        if not t1 or not t2:
            return False

        overlap = len(t1.intersection(t2)) / float(max(len(t1), len(t2)))
        return overlap >= 0.70

    def _merge_provenance(self, existing: Lesson, new_lesson: Lesson) -> Lesson:
        """Merge observation lineage and boost confidence for verified recurrence."""
        # Add task IDs
        for tid in new_lesson.provenance.origin_task_ids:
            if tid not in existing.provenance.origin_task_ids:
                existing.provenance.origin_task_ids.append(tid)

        # Add project IDs
        for pid in new_lesson.provenance.origin_project_ids:
            if pid not in existing.provenance.origin_project_ids:
                existing.provenance.origin_project_ids.append(pid)

        existing.provenance.verification_count += new_lesson.provenance.verification_count
        existing.provenance.last_verified_at = datetime.now(timezone.utc)

        # Append evidence
        existing.evidence.extend(new_lesson.evidence)

        # Boost confidence with each independent verification (up to 0.98)
        boost = 0.05 * len(existing.provenance.origin_project_ids)
        existing.confidence = min(0.98, existing.confidence + boost)
        existing.updated_at = datetime.now(timezone.utc)

        # Check scope promotion after provenance merge
        self._check_scope_promotion(existing)

        self.lesson_repo.save(existing)
        return existing

    def _check_scope_promotion(self, lesson: Lesson) -> None:
        """Promote lesson scope when verified across multiple independent projects."""
        distinct_projects = set(lesson.provenance.origin_project_ids)
        if len(distinct_projects) >= self.config.promotion_min_occurrences:
            if lesson.scope == KnowledgeScope.PROJECT:
                # If tied to frameworks, promote to TECHNOLOGY, otherwise DOMAIN/GLOBAL
                if lesson.context_conditions.get("frameworks") or lesson.context_conditions.get("languages"):
                    lesson.scope = KnowledgeScope.TECHNOLOGY
                elif lesson.context_conditions.get("domain") and lesson.context_conditions["domain"] != "general":
                    lesson.scope = KnowledgeScope.DOMAIN
                else:
                    lesson.scope = KnowledgeScope.GLOBAL

    def _find_conflicts(self, existing_lessons: List[Lesson], new_lesson: Lesson) -> List[Lesson]:
        """Detect existing lessons that prescribe contradictory strategies for the same trigger."""
        conflicts = []
        t2 = set(re.findall(r"\w{4,}", new_lesson.trigger_pattern.lower()))

        for existing in existing_lessons:
            if not existing.active:
                continue
            t1 = set(re.findall(r"\w{4,}", existing.trigger_pattern.lower()))
            if not t1 or not t2:
                continue

            overlap = len(t1.intersection(t2)) / float(max(len(t1), len(t2)))
            if overlap >= 0.60:
                # Check if recommendation of one is in anti_patterns of the other
                rec_new = new_lesson.recommended_strategy.lower()
                rec_old = existing.recommended_strategy.lower()

                if any(rec_new in ap.lower() for ap in existing.anti_patterns) or \
                   any(rec_old in ap.lower() for ap in new_lesson.anti_patterns):
                    conflicts.append(existing)

        return conflicts

    def _resolve_conflict(self, old_lesson: Lesson, new_lesson: Lesson) -> None:
        """Resolve contradiction by comparing evidence and recency."""
        # If new lesson has higher confidence or newer verified evidence, deactivate older lesson
        if new_lesson.confidence >= old_lesson.confidence:
            old_lesson.active = False
            old_lesson.confidence = max(0.1, old_lesson.confidence - 0.3)
            old_lesson.updated_at = datetime.now(timezone.utc)
            self.lesson_repo.save(old_lesson)
        else:
            # Demote new lesson confidence
            new_lesson.confidence = max(0.2, new_lesson.confidence - 0.2)
