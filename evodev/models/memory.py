"""Persistent memory models representing categorized, scoped engineering knowledge."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from evodev.models.experience import EpistemicType, KnowledgeScope, Provenance, VerificationEvidence


class MemoryCategory(str, Enum):
    """Clearly separated memory categories for intelligent recall and scoping."""

    PREFERENCES = "preferences"  # Developer preferences, styling, conventions
    ARCHITECTURE = "architecture"  # Project architecture, patterns, decisions
    LESSONS = "lessons"  # Verified technical lessons
    ANTI_PATTERNS = "anti_patterns"  # Proven failure approaches & traps
    TASK_SUMMARIES = "task_summaries"  # Observable session & task summaries
    SKILLS = "skills"  # Reusable procedures and workflow skills
    GENERAL = "general"  # Cross-project general engineering knowledge
    PROJECT_PRIVATE = "project_private"  # Strictly repository-private secrets/credentials/details


class MemoryItem(BaseModel):
    """An inspectable, portable, categorized unit of persistent memory."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile_id: str = Field(default="default", description="Associated experience profile")
    category: MemoryCategory = Field(description="Memory category partition")
    title: str = Field(description="Summary title of the memory")
    content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value memory payload (e.g. text, guidelines, schema, rules)",
    )
    scope: KnowledgeScope = Field(default=KnowledgeScope.PROJECT)
    project_id: Optional[str] = Field(default=None, description="Optional specific repository binding")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    epistemic_type: EpistemicType = Field(default=EpistemicType.VERIFIED_FACT)
    provenance: Provenance = Field(default_factory=Provenance)
    evidence: List[VerificationEvidence] = Field(default_factory=list)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def text_summary(self) -> str:
        """Helper to get a flat textual summary from content."""
        if "text" in self.content:
            return str(self.content["text"])
        if "description" in self.content:
            return str(self.content["description"])
        return str(self.content)
