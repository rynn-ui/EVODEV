"""Metrics calculation for empirical benchmark comparisons."""

from pydantic import BaseModel, Field


class BenchmarkMetrics(BaseModel):
    """Evaluation summary metrics comparing task performance."""

    suite_name: str
    agent_mode: str  # "base_agent", "evodev_experienced", "imported_profile"
    total_tasks: int = 0
    passed_tasks: int = 0
    failed_tasks: int = 0
    regressed_tasks: int = 0
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    regression_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    repeated_error_frequency: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_duration_seconds: float = 0.0
    evaluation_coverage: float = Field(default=1.0, ge=0.0, le=1.0)

    def compute(self) -> None:
        """Calculate rates from raw counts."""
        if self.total_tasks > 0:
            self.success_rate = round(self.passed_tasks / float(self.total_tasks), 3)
            self.regression_rate = round(self.regressed_tasks / float(self.total_tasks), 3)
            # Repeated error frequency: proportion of failed tasks that repeated known anti-patterns
            self.repeated_error_frequency = round(self.failed_tasks / float(self.total_tasks), 3)
        else:
            self.success_rate = 0.0
            self.regression_rate = 0.0
            self.repeated_error_frequency = 0.0
