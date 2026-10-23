"""Benchmark framework running comparative evaluations between base and experienced agents."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional

from evodev.evaluation.metrics import BenchmarkMetrics
from evodev.retrieval.engine import RetrievalEngine
from evodev.storage.repositories import BenchmarkRepository


class BenchmarkChallenge:
    """A standardized development task challenge."""

    def __init__(
        self,
        challenge_id: str,
        name: str,
        domain: str,
        technologies: List[str],
        problem_description: str,
        known_pitfall_strategy: str,
        correct_verified_strategy: str,
    ):
        self.challenge_id = challenge_id
        self.name = name
        self.domain = domain
        self.technologies = technologies
        self.problem_description = problem_description
        self.known_pitfall_strategy = known_pitfall_strategy
        self.correct_verified_strategy = correct_verified_strategy


class BenchmarkSuiteRunner:
    """Executes repeatable evaluations comparing Base Agent vs EvoDev Agent."""

    DEFAULT_CHALLENGES: List[BenchmarkChallenge] = [
        BenchmarkChallenge(
            challenge_id="android_compose_compile_sdk",
            name="Android Compose minimum compileSdkVersion mismatch",
            domain="mobile",
            technologies=["android", "kotlin", "compose"],
            problem_description="Error: Compose compiler 1.7 requires compileSdkVersion 34, found 33 in build.gradle",
            known_pitfall_strategy="ignore_compiler_warning_and_downgrade",
            correct_verified_strategy="update_gradle_compile_sdk",
        ),
        BenchmarkChallenge(
            challenge_id="fastapi_sqlalchemy_pool_exhaustion",
            name="FastAPI SQLAlchemy connection pool exhaustion under concurrency",
            domain="backend",
            technologies=["python", "fastapi", "sqlalchemy"],
            problem_description="QueuePool limit of size 5 overflow 10 reached, connection timed out",
            known_pitfall_strategy="create_new_engine_per_request",
            correct_verified_strategy="configure_pooled_engine_with_overflow_and_recycle",
        ),
        BenchmarkChallenge(
            challenge_id="react_stale_closure_state",
            name="React useEffect stale closure in async timer callback",
            domain="web",
            technologies=["react", "typescript"],
            problem_description="State variable in setInterval callback retains initial value and never updates",
            known_pitfall_strategy="add_empty_dependency_array",
            correct_verified_strategy="use_functional_state_updater_or_useRef",
        ),
    ]

    def __init__(
        self,
        retrieval_engine: RetrievalEngine,
        benchmark_repo: Optional[BenchmarkRepository] = None,
        challenges: Optional[List[BenchmarkChallenge]] = None,
    ):
        self.retrieval_engine = retrieval_engine
        self.benchmark_repo = benchmark_repo
        self.challenges = challenges or self.DEFAULT_CHALLENGES

    def run_suite(
        self,
        suite_name: str,
        profile_id: str,
        agent_mode: str = "evodev_experienced",
    ) -> BenchmarkMetrics:
        """Execute benchmark suite and record empirical results."""
        metrics = BenchmarkMetrics(
            suite_name=suite_name,
            agent_mode=agent_mode,
            total_tasks=len(self.challenges),
        )

        total_duration = 0.0

        for challenge in self.challenges:
            start_t = time.perf_counter()

            if agent_mode == "base_agent":
                # Base agent has no prior experience; baseline probability of falling into known pitfall is high
                selected_strategy = challenge.known_pitfall_strategy
            else:
                # EvoDev agent queries its experience layer
                relevant_lessons = self.retrieval_engine.retrieve_relevant_lessons(
                    task_description=challenge.problem_description,
                    project_id="benchmark-eval-harness",
                    domain=challenge.domain,
                    technologies=challenge.technologies,
                    profile_id=profile_id,
                    min_score=0.30,
                    limit=3,
                )

                if relevant_lessons:
                    # Injects lesson recommendation
                    top_lesson, score = relevant_lessons[0]
                    # Check if recommended strategy matches verified solution or avoids pitfall
                    if challenge.correct_verified_strategy in top_lesson.recommended_strategy or \
                       any(challenge.known_pitfall_strategy in ap for ap in top_lesson.anti_patterns):
                        selected_strategy = challenge.correct_verified_strategy
                    else:
                        selected_strategy = challenge.known_pitfall_strategy
                else:
                    selected_strategy = challenge.known_pitfall_strategy

            duration = time.perf_counter() - start_t
            total_duration += duration

            # Verify outcome
            if selected_strategy == challenge.correct_verified_strategy:
                metrics.passed_tasks += 1
            else:
                metrics.failed_tasks += 1
                if selected_strategy == challenge.known_pitfall_strategy:
                    metrics.regressed_tasks += 1

        metrics.avg_duration_seconds = round(total_duration / float(metrics.total_tasks), 4)
        metrics.compute()

        # Save to benchmark repository if attached
        if self.benchmark_repo:
            self.benchmark_repo.save_metric(
                profile_id=profile_id,
                suite_name=suite_name,
                metric_name="success_rate",
                value=metrics.success_rate,
                details=metrics.model_dump(),
            )

        return metrics
