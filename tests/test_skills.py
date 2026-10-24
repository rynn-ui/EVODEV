"""Tests for self-improving skills, versioning, evaluation, and untrusted execution guardrails."""

import pytest
from evodev.config import EvoDevConfig
from evodev.models.profile import ProfileManifest
from evodev.models.skills import SkillStatus
from evodev.skills.engine import SkillEngine, SkillPromotionError, UntrustedScriptError
from evodev.skills.evaluator import SkillEvaluator
from evodev.skills.renderer import SkillRenderer
from evodev.storage.db import get_db
from evodev.storage.migrations import MigrationManager
from evodev.storage.repositories import ProfileRepository, SkillRepository


@pytest.fixture
def skills_setup(tmp_path):
    config = EvoDevConfig(data_dir=tmp_path / "data")
    config.ensure_directories()
    db = get_db(config)
    MigrationManager(db).run_migrations()

    p_repo = ProfileRepository(db)
    s_repo = SkillRepository(db)
    p_repo.create(ProfileManifest(profile_id="p1", name="TestProfile"), is_active=True)

    evaluator = SkillEvaluator(s_repo)
    engine = SkillEngine(s_repo, p_repo, evaluator)
    return engine, s_repo, evaluator


def test_create_skill_and_render_formats(skills_setup):
    engine, s_repo, _ = skills_setup

    skill = engine.create_skill(
        name="Refactor Dataclass to Pydantic",
        description="Safely convert dataclass models into validated Pydantic models",
        initial_instructions="1. Inspect fields and types\n2. Inherit from BaseModel\n3. Run tests",
        category="refactoring",
    )

    assert skill.id is not None
    assert skill.current_version == "1.0.0"
    assert skill.status == SkillStatus.ACTIVE

    # Test Cross-Agent Renderers
    renderer = SkillRenderer()
    version = s_repo.get_version(skill.id, "1.0.0")

    # 1. Markdown
    md = renderer.render_markdown(skill, version)
    assert "# Skill: Refactor Dataclass to Pydantic" in md
    assert "Inherit from BaseModel" in md

    # 2. MCP Schema
    mcp = renderer.render_mcp_tool_description(skill, version)
    assert mcp["name"] == "skill_refactor_dataclass_to_pydantic"
    assert "parameters" in mcp

    # 3. Hermes Prompt
    hermes = renderer.render_hermes_prompt(skill, version)
    assert "<skill name=\"Refactor Dataclass to Pydantic\"" in hermes


def test_untrusted_script_guardrails(skills_setup):
    engine, _, _ = skills_setup

    # Dangerous script with rm -rf / should be rejected
    with pytest.raises(UntrustedScriptError):
        engine.create_skill(
            name="Dangerous Cleanup",
            description="Destructive script",
            initial_instructions="Run bash command: rm -rf /",
        )


def test_skill_evaluation_and_promotion_gate(skills_setup):
    engine, s_repo, evaluator = skills_setup

    skill = engine.create_skill(
        name="SQL Query Optimizer",
        description="Index query tuning",
        initial_instructions="Use EXPLAIN ANALYZE and add compound index",
    )

    # 1. Evaluate baseline version 1.0.0
    evaluator.evaluate_version(
        skill_id=skill.id,
        version="1.0.0",
        trials=[(True, 0.85, "Baseline performance query test")],
    )

    # 2. Propose improved version 1.1.0
    v2 = engine.propose_version(
        skill_id=skill.id,
        version="1.1.0",
        instructions="Use EXPLAIN (ANALYZE, BUFFERS) and add covering index with INCLUDE",
    )
    assert v2.version == "1.1.0"

    # 3. If version 1.1.0 has lower score / regression, promotion MUST be rejected
    evaluator.evaluate_version(
        skill_id=skill.id,
        version="1.1.0",
        trials=[(False, 0.40, "Degraded performance on write workloads")],
    )

    with pytest.raises(SkillPromotionError):
        engine.promote_version(skill.id, "1.1.0")

    # Active version remains 1.0.0
    skill_check = s_repo.get_by_id(skill.id)
    assert skill_check.current_version == "1.0.0"

    # 4. Now evaluate with superior score
    evaluator.evaluate_version(
        skill_id=skill.id,
        version="1.1.0",
        trials=[
            (True, 0.95, "Passes write workloads"),
            (True, 0.98, "High throughput read performance"),
        ],
    )

    promoted = engine.promote_version(skill.id, "1.1.0")
    assert promoted.current_version == "1.1.0"


def test_skill_rollback(skills_setup):
    engine, s_repo, evaluator = skills_setup

    skill = engine.create_skill(
        name="API Error Formatter",
        description="Standardize RFC 7807 error responses",
        initial_instructions="Return application/problem+json",
    )

    engine.propose_version(skill.id, "1.1.0", "Return RFC 7807 with trace ID")
    evaluator.evaluate_version(skill.id, "1.1.0", [(True, 0.90, "Good trace format")])
    engine.promote_version(skill.id, "1.1.0")

    assert s_repo.get_by_id(skill.id).current_version == "1.1.0"

    # Rollback to v1.0.0
    rolled_back = engine.rollback_skill(skill.id, "1.0.0")
    assert rolled_back.current_version == "1.0.0"
