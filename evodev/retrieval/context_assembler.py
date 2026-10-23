"""Context assembler formatting retrieved lessons into high-signal agent prompt context."""

from typing import List, Optional, Tuple

from evodev.models.experience import Lesson


class ContextAssembler:
    """Formats retrieved lessons into clean, structured Markdown for agent injection."""

    def __init__(self, max_context_chars: int = 2000):
        self.max_context_chars = max_context_chars

    def assemble(
        self,
        scored_lessons: List[Tuple[Lesson, float]],
        profile_name: str = "Active Profile",
    ) -> str:
        """Convert a list of (Lesson, score) pairs into an advisory block."""
        if not scored_lessons:
            return ""

        sections: List[str] = [
            f"### [EvoDev Verified Experience Advisory | Profile: {profile_name}]",
            "> Historical engineering context based on empirical development outcomes. Verify applicability before modifying code.\n",
        ]

        for idx, (lesson, score) in enumerate(scored_lessons, 1):
            project_count = len(lesson.provenance.origin_project_ids)
            scope_badge = lesson.scope.value.upper()
            epistemic_badge = lesson.epistemic_type.value.replace("_", " ").upper()

            entry = [
                f"**Lesson {idx}: {lesson.title}** (Relevance: {score:.0%}, Scope: `{scope_badge}`, Evidence: {epistemic_badge})",
                f"- **Verified History**: Successfully validated across {project_count} project(s), {lesson.provenance.verification_count} verified run(s).",
                f"- **Recommended Strategy**: {lesson.recommended_strategy}",
            ]

            if lesson.anti_patterns:
                entry.append(f"- **Anti-Patterns to Avoid**: {'; '.join(lesson.anti_patterns[:2])}")

            sections.append("\n".join(entry) + "\n")

        full_text = "\n".join(sections).strip()
        if len(full_text) > self.max_context_chars:
            full_text = full_text[: self.max_context_chars] + "\n... [Context Truncated]"

        return full_text
