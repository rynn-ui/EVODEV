"""Strategy performance and outcome tracker using Bayesian smoothed success rates."""

from typing import List, Optional

from evodev.models.experience import ExperienceRecord, StrategyOutcome, StrategyRecord
from evodev.storage.repositories import StrategyRepository


class StrategyTracker:
    """Manages empirical strategy outcome metrics and ranking."""

    def __init__(self, strategy_repo: StrategyRepository):
        self.strategy_repo = strategy_repo

    def process_experience(self, record: ExperienceRecord) -> List[StrategyRecord]:
        """Update strategy metrics based on a finished ExperienceRecord."""
        updated_records = []
        profile_id = record.profile_id
        is_success = record.outcome == "success" and (
            record.verification is not None and record.verification.passed is True
        )
        is_regression = (
            record.verification is not None and record.verification.failed_tests > 0
        )

        outcome = StrategyOutcome.SUCCESS if is_success else (
            StrategyOutcome.REGRESSION if is_regression else StrategyOutcome.FAILURE
        )

        for strategy_name in record.strategies_attempted:
            strat = self.strategy_repo.record_outcome(
                profile_id=profile_id,
                name=strategy_name,
                category=record.domain,
                outcome=outcome,
            )
            updated_records.append(strat)

        return updated_records

    def get_strategy_score(self, profile_id: str, strategy_name: str) -> float:
        """Fetch current Bayesian score for a strategy."""
        strat = self.strategy_repo.get(profile_id, strategy_name)
        return strat.bayesian_score if strat else 0.5

    def list_top_strategies(self, profile_id: str, limit: int = 10) -> List[StrategyRecord]:
        """List strategies sorted by highest Bayesian score."""
        records = self.strategy_repo.list_by_profile(profile_id)
        return sorted(records, key=lambda s: s.bayesian_score, reverse=True)[:limit]
