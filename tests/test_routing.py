"""Tests for optional model and provider routing engine."""

import pytest
from evodev.models.routing import LatencyTier, ModelCapability
from evodev.routing.router import ModelRouter


def test_model_router_capability_matching():
    router = ModelRouter()

    # Code generation task requiring low latency
    dec_fast = router.route_task(
        task_category="code_generation",
        required_capability=ModelCapability.CODE_GENERATION,
        latency_preference=LatencyTier.LOW,
    )
    assert dec_fast.provider is not None
    assert dec_fast.model_id is not None
    assert dec_fast.latency_tier == LatencyTier.LOW


def test_model_router_zero_cost_local_fallback():
    router = ModelRouter()

    # Strict zero cost preference
    dec_local = router.route_task(
        task_category="code_generation",
        required_capability=ModelCapability.CODE_GENERATION,
        zero_cost_only=True,
    )
    assert dec_local.provider in ("ollama", "local", "local_ollama")
    assert dec_local.estimated_cost_usd == 0.0


def test_model_router_user_provider_restrictions():
    router = ModelRouter()

    # User restricts allowed providers to gemini only
    dec = router.route_task(
        task_category="security_review",
        required_capability=ModelCapability.SECURITY_AUDIT,
        allowed_providers=["gemini"],
    )
    assert dec.provider in ("gemini", "google")
