"""Skill evaluation engine for running repeatable test cases and measuring regressions."""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional

from evodev.models.skills import SkillEvaluation, SkillVersion
from evodev.storage.repositories import SkillRepository

logger = logging.getLogger(__name__)


class EvaluationRunResult(dict):
    """Result object supporting both dict and attribute access."""

    @property
    def passed(self) -> bool:
        return bool(self.get("passed", 0) > 0 and self.get("failed", 0) == 0)

    @property
    def score(self) -> float:
        return float(self.get("pass_rate", 0.0))

    @property
    def pass_rate(self) -> float:
        return float(self.get("pass_rate", 0.0))

    @property
    def benchmark_name(self) -> str:
        return str(self.get("benchmark_name", "StandardSkillBenchmark"))

    def __getattr__(self, name: str) -> Any:
        if name in self:
            return self[name]
        raise AttributeError(name)


class SkillEvaluator:
    """Runs controlled evaluation trials against skill versions and computes comparative metrics."""

    def __init__(self, skill_repo: SkillRepository):
        self.skill_repo = skill_repo

    def evaluate_version(
        self,
        skill_version: Optional[SkillVersion] = None,
        test_tasks: Optional[List[Dict[str, Any]]] = None,
        executor_fn: Optional[Callable[[Dict[str, Any], SkillVersion], Dict[str, Any]]] = None,
        skill_id: Optional[str] = None,
        version: Optional[str] = None,
        trials: Optional[List[Any]] = None,
    ) -> EvaluationRunResult:
        """Execute a batch of standardized evaluation tasks against a skill version."""
        # Handle positional evaluate_version(skill_id, version, trials)
        if isinstance(skill_version, str):
            if isinstance(test_tasks, str):
                version = test_tasks
                if executor_fn is not None and isinstance(executor_fn, list):
                    trials = executor_fn
                    executor_fn = None
                test_tasks = None
            skill_id = skill_version
            skill_version = None

        if skill_version is None:
            if not skill_id or not version:
                raise ValueError("Either skill_version or (skill_id, version) must be provided.")
            skill_version = self.skill_repo.get_version(skill_id, version)
            if not skill_version:
                raise ValueError(f"Version '{version}' for skill '{skill_id}' not found.")

        if trials is not None:
            test_tasks = []
            for idx, tr in enumerate(trials):
                if isinstance(tr, (list, tuple)):
                    p = bool(tr[0])
                    sc = float(tr[1]) if len(tr) > 1 else (1.0 if p else 0.0)
                    nt = str(tr[2]) if len(tr) > 2 else ""
                else:
                    p = bool(tr)
                    sc = 1.0 if p else 0.0
                    nt = ""
                test_tasks.append({"id": f"trial_{idx+1}", "passed": p, "score": sc, "notes": nt})
            executor_fn = lambda task, ver: {"passed": task["passed"], "evidence": {"score": task["score"], "notes": task["notes"]}}
        elif test_tasks is None:
            test_tasks = [{"id": "default_trial", "passed": True}]

        if executor_fn is None:
            executor_fn = lambda task, ver: {"passed": task.get("passed", True), "evidence": {}}

        passed_count = 0
        failed_count = 0
        evaluations: List[SkillEvaluation] = []

        for task in test_tasks:
            task_id = task.get("id", str(len(evaluations) + 1))
            benchmark_id = task.get("benchmark_id", "skill_benchmark")

            try:
                res = executor_fn(task, skill_version)
                is_passed = bool(res.get("passed", False))
                evidence = res.get("evidence", {})
            except Exception as exc:
                logger.error(f"Error evaluating task {task_id}: {exc}")
                is_passed = False
                evidence = {"error": str(exc)}

            if is_passed:
                passed_count += 1
            else:
                failed_count += 1

            eval_record = SkillEvaluation(
                skill_version_id=skill_version.id,
                task_id=task_id,
                benchmark_id=benchmark_id,
                passed=is_passed,
                evidence=evidence,
                evaluated_at=datetime.now(timezone.utc),
            )
            self.skill_repo.save_evaluation(eval_record)
            evaluations.append(eval_record)

        total = len(test_tasks)
        pass_rate = (passed_count / total) if total > 0 else 0.0

        summary = EvaluationRunResult({
            "total_trials": total,
            "passed": passed_count,
            "failed": failed_count,
            "pass_rate": round(pass_rate, 4),
            "benchmark_name": "StandardSkillBenchmark",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        })

        # Update evaluation summary on the version
        skill_version.evaluation_summary = dict(summary)
        self.skill_repo.save_version(skill_version)

        return summary
