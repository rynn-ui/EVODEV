"""Memory manager providing categorized persistent recall, deduplication, and scope isolation."""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from evodev.models.experience import EpistemicType, KnowledgeScope, Provenance, VerificationEvidence
from evodev.models.memory import MemoryCategory, MemoryItem
from evodev.security.redactor import SecretRedactor
from evodev.storage.repositories import LessonRepository, MemoryRepository, ProfileRepository

logger = logging.getLogger(__name__)


class ScopeViolationError(ValueError):
    """Raised when an attempt is made to persist or expose private memories improperly."""
    pass


class MemoryManager:
    """Manages categorized persistent memory, intelligent recall, consolidation, and redaction."""

    def __init__(
        self,
        memory_repo: MemoryRepository,
        lesson_repo: Optional[LessonRepository] = None,
        profile_repo: Optional[ProfileRepository] = None,
        redactor: Optional[SecretRedactor] = None,
    ):
        self.memory_repo = memory_repo
        self.lesson_repo = lesson_repo
        self.profile_repo = profile_repo
        self.redactor = redactor or SecretRedactor()

    def record_memory(
        self,
        category: MemoryCategory,
        title: str,
        content: Dict[str, Any],
        scope: Optional[KnowledgeScope] = None,
        project_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        confidence: float = 1.0,
        epistemic_type: EpistemicType = EpistemicType.VERIFIED_FACT,
        evidence: Optional[List[VerificationEvidence]] = None,
    ) -> MemoryItem:
        """Create, sanitize, and persist a categorized memory item with scope validation."""
        # 1. Resolve active profile if not specified
        if not profile_id:
            if self.profile_repo:
                active = self.profile_repo.get_active()
                profile_id = active.profile_id if active else "default"
            else:
                profile_id = "default"

        # 2. Scope Validation and Resolution
        if category == MemoryCategory.PROJECT_PRIVATE:
            if not project_id:
                raise ScopeViolationError(
                    "Project-scoped or project_private memory requires an explicit project_id."
                )
            resolved_scope = scope or KnowledgeScope.PROJECT
        else:
            if scope == KnowledgeScope.PROJECT and not project_id:
                raise ScopeViolationError(
                    "Project-scoped or project_private memory requires an explicit project_id."
                )
            resolved_scope = scope or (KnowledgeScope.PROJECT if project_id else KnowledgeScope.GLOBAL)

        # 3. Secret Redaction
        redacted_title = self.redactor.redact_text(title)
        redacted_content = self.redactor.redact_dict(content)

        # 4. Create MemoryItem
        item = MemoryItem(
            profile_id=profile_id,
            category=category,
            title=redacted_title,
            content=redacted_content,
            scope=resolved_scope,
            project_id=project_id,
            confidence=confidence,
            epistemic_type=epistemic_type,
            provenance=Provenance(origin_project_ids=[project_id] if project_id else []),
            evidence=evidence or [],
            is_active=True,
        )

        # 5. Check duplicate or update existing
        existing_items = self.memory_repo.list_by_profile(profile_id, category=category, active_only=True)
        for existing in existing_items:
            if existing.title.strip().lower() == redacted_title.strip().lower():
                # Merge provenance and update confidence
                existing.provenance.verification_count += 1
                existing.provenance.last_verified_at = datetime.now(timezone.utc)
                if project_id and project_id not in existing.provenance.origin_project_ids:
                    existing.provenance.origin_project_ids.append(project_id)
                existing.content.update(redacted_content)
                existing.confidence = min(1.0, existing.confidence + 0.05)
                existing.updated_at = datetime.now(timezone.utc)
                return self.memory_repo.save(existing)

        return self.memory_repo.save(item)

    def retrieve_context(
        self,
        query: str,
        project_id: str,
        profile_id: Optional[str] = None,
        categories: Optional[List[MemoryCategory]] = None,
        limit: int = 5,
    ) -> List[MemoryItem]:
        """Intelligent recall of relevant memories matching query with strict scope isolation."""
        if not profile_id:
            if self.profile_repo:
                active = self.profile_repo.get_active()
                profile_id = active.profile_id if active else "default"
            else:
                profile_id = "default"

        # Fetch candidate active memories for this profile
        all_candidates: List[MemoryItem] = []
        if categories:
            for cat in categories:
                all_candidates.extend(self.memory_repo.list_by_profile(profile_id, category=cat, active_only=True))
        else:
            all_candidates = self.memory_repo.list_by_profile(profile_id, active_only=True)

        scored: List[tuple[MemoryItem, float]] = []
        terms = set(re.findall(r"\w+", query.lower()))

        for item in all_candidates:
            # Scope Isolation:
            # 1. Project private or project-scoped memory from another project must NEVER be returned
            if item.scope == KnowledgeScope.PROJECT or item.category == MemoryCategory.PROJECT_PRIVATE:
                if item.project_id and item.project_id != project_id:
                    continue

            # Calculate textual match score
            content_str = json.dumps(item.content).lower()
            title_str = item.title.lower()
            matches = sum(1 for t in terms if t in title_str or t in content_str)
            base_score = matches / max(1, len(terms))

            # Preference and Architecture bonus for relevance
            if item.category in (MemoryCategory.PREFERENCES, MemoryCategory.ARCHITECTURE):
                base_score += 0.2

            # Confidence weighting
            final_score = base_score * item.confidence
            if final_score > 0.05 or not query:
                scored.append((item, final_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in scored[:limit]]

    def detect_contradictions(self, memory: MemoryItem) -> List[str]:
        """Detect potential contradictions against lessons and existing active memories."""
        contradictions: List[str] = []
        title_lower = memory.title.lower()
        content_str = json.dumps(memory.content).lower()

        # Check against existing lessons in profile
        if self.lesson_repo:
            lessons = self.lesson_repo.list_by_profile(memory.profile_id, active_only=True)
            for l in lessons:
                # If memory is anti-pattern and lesson prescribes it as recommended strategy:
                if memory.category == MemoryCategory.ANTI_PATTERNS:
                    if l.recommended_strategy.lower() in content_str or l.title.lower() in title_lower:
                        contradictions.append(
                            f"Contradiction: Anti-pattern '{memory.title}' conflicts with recommended lesson '{l.title}' (ID: {l.id})"
                        )
                # If memory is lesson/guideline and lesson marks it as anti-pattern:
                elif memory.category in (MemoryCategory.LESSONS, MemoryCategory.PREFERENCES):
                    for ap in l.anti_patterns:
                        if ap.lower() in content_str or ap.lower() in title_lower:
                            contradictions.append(
                                f"Contradiction: Guideline '{memory.title}' is flagged as anti-pattern in lesson '{l.title}'"
                            )

        # Check against existing memories
        existing_memories = self.memory_repo.list_by_profile(memory.profile_id, active_only=True)
        for em in existing_memories:
            if em.id == memory.id:
                continue
            if em.category != memory.category:
                # Opposite categories
                if {em.category, memory.category} == {MemoryCategory.PREFERENCES, MemoryCategory.ANTI_PATTERNS}:
                    if em.title.lower() == memory.title.lower():
                        contradictions.append(
                            f"Contradiction: Item '{memory.title}' exists as both {em.category.value} and {memory.category.value}"
                        )
        return contradictions

    def consolidate_duplicates(self, profile_id: str) -> int:
        """Find and consolidate duplicate active memories within the profile."""
        all_memories = self.memory_repo.list_by_profile(profile_id, active_only=True)
        seen: Dict[tuple[str, str], MemoryItem] = {}
        merged_count = 0

        for mem in all_memories:
            key = (mem.category.value, mem.title.strip().lower())
            if key in seen:
                primary = seen[key]
                primary.provenance.verification_count += mem.provenance.verification_count
                primary.provenance.failure_count += mem.provenance.failure_count
                for p_id in mem.provenance.origin_project_ids:
                    if p_id not in primary.provenance.origin_project_ids:
                        primary.provenance.origin_project_ids.append(p_id)
                primary.content.update(mem.content)
                primary.confidence = min(1.0, max(primary.confidence, mem.confidence) + 0.05)
                primary.updated_at = datetime.now(timezone.utc)
                self.memory_repo.save(primary)

                # Deactivate duplicate
                mem.is_active = False
                self.memory_repo.save(mem)
                merged_count += 1
            else:
                seen[key] = mem

        return merged_count

    def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> Optional[MemoryItem]:
        """User manual update or correction of a stored memory item."""
        mem = self.memory_repo.get_by_id(memory_id)
        if not mem:
            return None

        if "title" in updates:
            mem.title = self.redactor.redact_text(str(updates["title"]))
        if "content" in updates and isinstance(updates["content"], dict):
            mem.content = self.redactor.redact_dict(updates["content"])
        if "confidence" in updates:
            mem.confidence = float(updates["confidence"])
        if "is_active" in updates:
            mem.is_active = bool(updates["is_active"])
        if "scope" in updates:
            mem.scope = KnowledgeScope(updates["scope"])

        mem.updated_at = datetime.now(timezone.utc)
        return self.memory_repo.save(mem)

    def deactivate_memory(self, memory_id: str) -> bool:
        """Deactivate a memory item without deleting historical evidence."""
        mem = self.memory_repo.get_by_id(memory_id)
        if not mem:
            return False
        mem.is_active = False
        mem.updated_at = datetime.now(timezone.utc)
        self.memory_repo.save(mem)
        return True

    def delete_memory(self, memory_id: str) -> bool:
        """Permanently remove a memory item."""
        return self.memory_repo.delete(memory_id)
