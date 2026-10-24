"""Self-improving skill engine coordinating creation, versioning, evaluation, and promotion."""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from evodev.models.experience import KnowledgeScope
from evodev.models.skills import (
    ProcedureStep,
    Skill,
    SkillEvaluation,
    SkillPrerequisite,
    SkillStatus,
    SkillVersion,
)
from evodev.skills.evaluator import SkillEvaluator
from evodev.storage.repositories import ProfileRepository, SkillRepository

logger = logging.getLogger(__name__)


class SkillPromotionError(ValueError):
    """Raised when a skill version fails to meet promotion criteria."""
    pass


class UntrustedScriptError(ValueError):
    """Raised when an untrusted agent-generated script contains forbidden destructive commands."""
    pass


class SkillEngine:
    """Manages the full lifecycle of self-improving skills from proposal to benchmarked promotion."""

    FORBIDDEN_EXECUTION_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"format\s+[a-zA-Z]:",
        r"del\s+/[sS]\s+/[qQ]\s+C:\\",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",  # fork bomb
        r"DROP\s+DATABASE",
        r"TRUNCATE\s+TABLE",
        r"curl\s+.*\|\s*(bash|sh|powershell)",
    ]

    def __init__(
        self,
        skill_repo: SkillRepository,
        profile_repo: Optional[ProfileRepository] = None,
        evaluator: Optional[SkillEvaluator] = None,
    ):
        self.skill_repo = skill_repo
        self.profile_repo = profile_repo
        self.evaluator = evaluator or SkillEvaluator(skill_repo)

    def create_skill(
        self,
        name: str,
        description: str,
        initial_instructions: str,
        category: str = "general",
        scope: KnowledgeScope = KnowledgeScope.DOMAIN,
        profile_id: Optional[str] = None,
        prerequisites: Optional[List[SkillPrerequisite]] = None,
        procedures: Optional[List[ProcedureStep]] = None,
        validation_steps: Optional[List[str]] = None,
        expected_outcomes: Optional[List[str]] = None,
    ) -> Skill:
        """Create a new reusable skill with version 1.0.0."""
        if not profile_id:
            if self.profile_repo:
                active = self.profile_repo.get_active()
                profile_id = active.profile_id if active else "default"
            else:
                profile_id = "default"

        # Check untrusted content
        self.validate_untrusted_instructions(initial_instructions)

        skill_id = str(uuid.uuid4())
        initial_version = SkillVersion(
            id=str(uuid.uuid4()),
            skill_id=skill_id,
            version="1.0.0",
            instructions=initial_instructions,
            prerequisites=prerequisites or [],
            procedures=procedures or [],
            validation_steps=validation_steps or [],
            expected_outcomes=expected_outcomes or [],
            evaluation_summary={},
        )

        skill = Skill(
            id=skill_id,
            profile_id=profile_id,
            name=name,
            description=description,
            category=category,
            current_version="1.0.0",
            status=SkillStatus.ACTIVE,
            scope=scope,
            versions=[initial_version],
        )

        return self.skill_repo.save_skill(skill)

    def propose_version(
        self,
        skill_id: str,
        version_tag: Optional[str] = None,
        instructions: str = "",
        prerequisites: Optional[List[SkillPrerequisite]] = None,
        procedures: Optional[List[ProcedureStep]] = None,
        validation_steps: Optional[List[str]] = None,
        expected_outcomes: Optional[List[str]] = None,
        version: Optional[str] = None,
    ) -> SkillVersion:
        """Propose a new candidate version for an existing skill."""
        version_tag = version_tag or version or "1.1.0"
        skill = self.skill_repo.get_skill_by_id(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")

        self.validate_untrusted_instructions(instructions)

        new_version = SkillVersion(
            id=str(uuid.uuid4()),
            skill_id=skill_id,
            version=version_tag,
            instructions=instructions,
            prerequisites=prerequisites or [],
            procedures=procedures or [],
            validation_steps=validation_steps or [],
            expected_outcomes=expected_outcomes or [],
            evaluation_summary={},
        )

        self.skill_repo.save_version(new_version)
        skill.status = SkillStatus.EVALUATING
        self.skill_repo.save_skill(skill)
        return new_version

    def evaluate_version(
        self,
        skill_id: str,
        version_tag: str,
        test_tasks: List[Dict[str, Any]],
        executor_fn: Callable[[Dict[str, Any], SkillVersion], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Run benchmark trials for a specific skill version."""
        ver = self.skill_repo.get_version(skill_id, version_tag)
        if not ver:
            raise ValueError(f"Version {version_tag} of skill {skill_id} not found.")

        return self.evaluator.evaluate_version(ver, test_tasks, executor_fn)

    def promote_version(
        self,
        skill_id: str,
        candidate_version_tag: str,
        min_pass_rate: float = 0.75,
    ) -> Skill:
        """Promote a candidate version only if evaluation meets criteria and introduces no regressions."""
        skill = self.skill_repo.get_skill_by_id(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")

        candidate = self.skill_repo.get_version(skill_id, candidate_version_tag)
        if not candidate:
            raise ValueError(f"Candidate version not found: {candidate_version_tag}")

        cand_summary = candidate.evaluation_summary
        if not cand_summary or "pass_rate" not in cand_summary:
            raise SkillPromotionError(
                f"Candidate version {candidate_version_tag} has not been evaluated. Run evaluation first."
            )

        cand_pass_rate = float(cand_summary.get("pass_rate", 0.0))
        if cand_pass_rate < min_pass_rate:
            raise SkillPromotionError(
                f"Pass rate {cand_pass_rate * 100:.1f}% is below required promotion threshold {min_pass_rate * 100:.1f}%."
            )

        # Compare against baseline current version
        if skill.current_version != candidate_version_tag:
            current_ver = self.skill_repo.get_version(skill_id, skill.current_version)
            if current_ver and current_ver.evaluation_summary:
                current_rate = float(current_ver.evaluation_summary.get("pass_rate", 0.0))
                if cand_pass_rate < current_rate:
                    raise SkillPromotionError(
                        f"Regression detected: Candidate rate ({cand_pass_rate * 100:.1f}%) is lower than current version ({current_rate * 100:.1f}%)."
                    )

        # Successful promotion
        skill.current_version = candidate_version_tag
        skill.status = SkillStatus.PROMOTED
        skill.updated_at = datetime.now(timezone.utc)
        return self.skill_repo.save_skill(skill)

    def rollback_version(self, skill_id: str, target_version_tag: str) -> Skill:
        """Rollback skill to an earlier validated version."""
        skill = self.skill_repo.get_skill_by_id(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")

        target_ver = self.skill_repo.get_version(skill_id, target_version_tag)
        if not target_ver:
            raise ValueError(f"Target rollback version not found: {target_version_tag}")

        skill.current_version = target_version_tag
        skill.status = SkillStatus.PROMOTED
        skill.updated_at = datetime.now(timezone.utc)
        return self.skill_repo.save_skill(skill)

    rollback_skill = rollback_version

    def retrieve_skills(
        self,
        task_description: str,
        profile_id: Optional[str] = None,
        promoted_only: bool = True,
        limit: int = 3,
    ) -> List[Tuple[Skill, float]]:
        """Retrieve top skills matching incoming problem description."""
        if not profile_id:
            if self.profile_repo:
                active = self.profile_repo.get_active()
                profile_id = active.profile_id if active else "default"
            else:
                profile_id = "default"

        all_skills = self.skill_repo.list_skills(profile_id)
        terms = set(re.findall(r"\w+", task_description.lower()))
        scored: List[Tuple[Skill, float]] = []

        for s in all_skills:
            if promoted_only and s.status != SkillStatus.PROMOTED:
                continue

            text = f"{s.name} {s.description} {s.category}".lower()
            matches = sum(1 for t in terms if t in text)
            score = matches / max(1, len(terms))

            # Promoted bonus
            if s.status == SkillStatus.PROMOTED:
                score += 0.2

            if score > 0.1 or not task_description:
                scored.append((s, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def validate_untrusted_instructions(self, instructions: str) -> None:
        """Untrusted execution guard: reject commands containing forbidden destructive sequences."""
        for pattern in self.FORBIDDEN_EXECUTION_PATTERNS:
            if re.search(pattern, instructions, re.IGNORECASE):
                raise UntrustedScriptError(
                    f"Untrusted script rejected: contains dangerous pattern '{pattern}'"
                )
