"""Model and provider router matching task requirements, benchmarks, cost, and latency."""

from typing import Any, Dict, List, Optional

from evodev.models.routing import LatencyTier, ModelCapability, RoutingDecision


class ModelRouter:
    """Routes EvoDev-managed automated tasks to the most suitable provider and model."""

    DEFAULT_CAPABILITIES = [
        ModelCapability(
            provider="anthropic",
            model_name="claude-3-5-sonnet",
            context_window_tokens=200000,
            supports_tools=True,
            supports_vision=True,
            latency_tier=LatencyTier.MEDIUM,
            cost_per_million_input=3.0,
            cost_per_million_output=15.0,
            benchmark_specialties=["refactor", "code_review", "architecture", "android"],
        ),
        ModelCapability(
            provider="openai",
            model_name="gpt-4o",
            context_window_tokens=128000,
            supports_tools=True,
            supports_vision=True,
            latency_tier=LatencyTier.FAST,
            cost_per_million_input=2.5,
            cost_per_million_output=10.0,
            benchmark_specialties=["debug", "test_engineering", "general"],
        ),
        ModelCapability(
            provider="google",
            model_name="gemini-1.5-pro",
            context_window_tokens=1000000,
            supports_tools=True,
            supports_vision=True,
            latency_tier=LatencyTier.MEDIUM,
            cost_per_million_input=1.25,
            cost_per_million_output=5.0,
            benchmark_specialties=["large_codebase", "documentation", "analysis"],
        ),
        ModelCapability(
            provider="hermes",
            model_name="hermes-3-llama-3.1-70b",
            context_window_tokens=128000,
            supports_tools=True,
            supports_vision=False,
            latency_tier=LatencyTier.FAST,
            cost_per_million_input=0.9,
            cost_per_million_output=1.8,
            benchmark_specialties=["tool_calling", "agent_delegation", "open_weights"],
        ),
        ModelCapability(
            provider="local_ollama",
            model_name="qwen2.5-coder:32b",
            context_window_tokens=64000,
            supports_tools=True,
            supports_vision=False,
            latency_tier=LatencyTier.FAST,
            cost_per_million_input=0.0,
            cost_per_million_output=0.0,
            benchmark_specialties=["local_privacy", "offline", "unit_tests"],
        ),
    ]

    def __init__(self, capabilities: Optional[List[ModelCapability]] = None):
        self.capabilities: List[ModelCapability] = capabilities or list(self.DEFAULT_CAPABILITIES)

    def register_capability(self, cap: ModelCapability) -> None:
        """Register or override a model capability."""
        self.capabilities = [c for c in self.capabilities if not (c.provider == cap.provider and c.model_name == cap.model_name)]
        self.capabilities.append(cap)

    def route_task(
        self,
        task_category: str,
        required_context_tokens: int = 4000,
        requires_tools: bool = True,
        requires_vision: bool = False,
        preferred_latency: Optional[LatencyTier] = None,
        latency_preference: Optional[LatencyTier] = None,
        allowed_providers: Optional[List[str]] = None,
        max_cost_budget: Optional[float] = None,
        zero_cost_only: bool = False,
        required_capability: Optional[Any] = None,
    ) -> RoutingDecision:
        """Evaluate registered models and select the optimal model based on constraints and specialties."""
        if zero_cost_only:
            max_cost_budget = 0.0
        if latency_preference is not None:
            preferred_latency = latency_preference

        norm_providers = None
        if allowed_providers:
            norm_providers = set()
            for p in allowed_providers:
                p_l = p.lower()
                norm_providers.add(p_l)
                if p_l == "gemini":
                    norm_providers.add("google")
                elif p_l in ("ollama", "local"):
                    norm_providers.add("local_ollama")

        candidates: List[ModelCapability] = []

        for cap in self.capabilities:
            # 1. Provider restriction filter
            if norm_providers and not any(np in cap.provider.lower() for np in norm_providers):
                continue

            # 2. Context window constraint
            if cap.context_window_tokens < required_context_tokens:
                continue

            # 3. Tool capability constraint
            if requires_tools and not cap.supports_tools:
                continue

            # 4. Vision constraint
            if requires_vision and not cap.supports_vision:
                continue

            # 5. Cost budget constraint
            if max_cost_budget is not None and cap.cost_per_million_input > max_cost_budget:
                continue

            candidates.append(cap)

        if not candidates:
            # Fallback to local offline model if all filtered out
            local = next((c for c in self.capabilities if c.provider == "local_ollama"), self.capabilities[0])
            return RoutingDecision(
                selected_provider=local.provider,
                selected_model=local.model_name,
                rationale="Fallback: No models met all explicit constraints; routed to local/default model.",
                estimated_cost=0.0,
                is_delegated=True,
                latency_tier=local.latency_tier,
            )

        # Score candidates
        def _score(c: ModelCapability) -> float:
            score = 1.0
            # Specialty match
            if task_category.lower() in [s.lower() for s in c.benchmark_specialties]:
                score += 3.0
            # Latency preference
            if preferred_latency and c.latency_tier == preferred_latency:
                score += 1.5
            # Cost efficiency bonus (lower cost gets slight boost)
            if c.cost_per_million_input == 0.0:
                score += 1.0  # Zero-cost local bonus
            else:
                score += max(0.0, 1.0 - (c.cost_per_million_input / 10.0))
            return score

        candidates.sort(key=_score, reverse=True)
        winner = candidates[0]

        rationale = f"Matched category '{task_category}' with specialty bonus on {winner.provider}/{winner.model_name}."
        if winner.cost_per_million_input == 0.0:
            rationale += " Local zero-cost privacy preservation."

        return RoutingDecision(
            selected_provider=winner.provider,
            selected_model=winner.model_name,
            rationale=rationale,
            estimated_cost=round((required_context_tokens / 1_000_000) * winner.cost_per_million_input, 6),
            is_delegated=True,
            latency_tier=winner.latency_tier,
        )
