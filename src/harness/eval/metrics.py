"""Metrics calculator for evaluation results."""

from __future__ import annotations

from dataclasses import dataclass, field

from harness.eval.types import EvalResults, TaskResult


@dataclass(slots=True)
class MetricsSummary:
    """Aggregated metrics from evaluation results."""

    # Primary
    resolved_rate: float = 0.0
    total_tasks: int = 0
    resolved_count: int = 0

    # Efficiency
    avg_tokens_per_task: float = 0.0
    avg_cost_per_task: float = 0.0
    cost_per_resolved: float = 0.0
    avg_turns_per_task: float = 0.0
    avg_tool_calls_per_task: float = 0.0
    avg_duration_seconds: float = 0.0

    # Quality
    file_localization_rate: float = 0.0
    error_rate: float = 0.0
    timeout_rate: float = 0.0

    # Failure breakdown
    failure_categories: dict[str, int] = field(default_factory=dict)


class MetricsCalculator:
    """Calculate evaluation metrics from results."""

    def calculate(self, results: EvalResults) -> MetricsSummary:
        """Calculate all metrics from evaluation results."""
        if not results.results:
            return MetricsSummary()

        task_results = results.results
        n = len(task_results)
        resolved = [r for r in task_results if r.resolved]

        summary = MetricsSummary(
            total_tasks=n,
            resolved_count=len(resolved),
            resolved_rate=results.resolved_rate,
            avg_tokens_per_task=results.total_tokens / n,
            avg_cost_per_task=results.total_cost / n,
            cost_per_resolved=(
                results.total_cost / len(resolved) if resolved else float("inf")
            ),
            avg_turns_per_task=results.avg_turns,
            avg_tool_calls_per_task=results.avg_tool_calls,
            avg_duration_seconds=results.avg_duration,
            file_localization_rate=self._file_localization_rate(task_results),
            error_rate=self._error_rate(task_results),
            timeout_rate=self._timeout_rate(task_results),
            failure_categories=self._failure_breakdown(task_results),
        )

        return summary

    def _file_localization_rate(self, results: list[TaskResult]) -> float:
        """Percentage of tasks where agent edited the right files."""
        if not results:
            return 0.0
        tasks_with_expected = [r for r in results if r.expected_files]
        if not tasks_with_expected:
            return 0.0
        correct = sum(
            1 for r in tasks_with_expected
            if set(r.modified_files) == set(r.expected_files)
        )
        return (correct / len(tasks_with_expected)) * 100

    def _error_rate(self, results: list[TaskResult]) -> float:
        """Percentage of tasks that had errors."""
        if not results:
            return 0.0
        with_errors = sum(1 for r in results if r.errors)
        return (with_errors / len(results)) * 100

    def _timeout_rate(self, results: list[TaskResult]) -> float:
        """Percentage of tasks that likely timed out (duration > 5min)."""
        if not results:
            return 0.0
        timed_out = sum(1 for r in results if r.duration_seconds > 300)
        return (timed_out / len(results)) * 100

    def _failure_breakdown(self, results: list[TaskResult]) -> dict[str, int]:
        """Count failures by category."""
        counts: dict[str, int] = {}
        for r in results:
            if not r.resolved and r.failure_category:
                cat = r.failure_category.value
                counts[cat] = counts.get(cat, 0) + 1
        return counts
