"""Model and provider routing data models."""

from enum import Enum
from typing import ClassVar, Dict, List, Optional
from pydantic import BaseModel, Field


class LatencyTier(str, Enum):
    """Expected roundtrip latency tier for a model."""

    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    LOW = "fast"
    BALANCED = "medium"
    THOROUGH = "slow"


class ModelCapability(BaseModel):
    """Declared capabilities, token limits, and unit costs of a model provider."""

    provider: str = Field(description="Provider name (e.g. openai, anthropic, google, local_ollama, hermes)")
    model_name: str = Field(description="Provider model identifier (e.g. claude-3-5-sonnet, gpt-4o, hermes-3)")
    context_window_tokens: int = Field(default=128000)
    supports_tools: bool = Field(default=True)
    supports_vision: bool = Field(default=False)
    latency_tier: LatencyTier = Field(default=LatencyTier.MEDIUM)
    cost_per_million_input: float = Field(default=0.0)
    cost_per_million_output: float = Field(default=0.0)
    benchmark_specialties: List[str] = Field(default_factory=list, description="Categories where model excels")

    # Capability constants
    CODE_GENERATION: ClassVar[str] = "code_generation"
    ANALYSIS: ClassVar[str] = "analysis"
    SECURITY_AUDIT: ClassVar[str] = "security_audit"
    CODE_REVIEW: ClassVar[str] = "code_review"
    DEBUGGING: ClassVar[str] = "debugging"


class RoutingDecision(BaseModel):
    """The result of an automated model/provider selection for an EvoDev-managed task."""

    selected_provider: str
    selected_model: str
    rationale: str
    estimated_cost: float = 0.0
    is_delegated: bool = True
    latency_tier: Optional[LatencyTier] = None

    @property
    def provider(self) -> str:
        return self.selected_provider

    @property
    def model_id(self) -> str:
        return self.selected_model

    @property
    def estimated_cost_usd(self) -> float:
        return self.estimated_cost
