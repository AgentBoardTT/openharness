"""Evaluation report generator."""

from __future__ import annotations

from harness.eval.metrics import MetricsCalculator, MetricsSummary
from harness.eval.types import EvalResults


class ReportGenerator:
    """Generate markdown evaluation reports."""

    def __init__(self) -> None:
        self._calculator = MetricsCalculator()

    def generate(self, results: EvalResults) -> str:
        """Generate a markdown report from evaluation results."""
        summary = self._calculator.calculate(results)
        return self._render_markdown(results, summary)

    def _render_markdown(self, results: EvalResults, summary: MetricsSummary) -> str:
        """Render metrics into a markdown report."""
        lines: list[str] = []

        # Header
        lines.append(f"# Evaluation Report: {results.benchmark}")
        lines.append("")
        lines.append(f"**Provider:** {results.provider}")
        lines.append(f"**Model:** {results.model}")
        lines.append(f"**Split:** {results.split}")
        lines.append(f"**Tasks:** {summary.total_tasks}")
        if results.started_at:
            lines.append(f"**Date:** {results.started_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        # Primary metrics
        lines.append("## Results")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        resolved = f"{summary.resolved_count}/{summary.total_tasks}"
        lines.append(f"| Resolved | {resolved} ({summary.resolved_rate:.1f}%) |")
        lines.append(f"| Avg Tokens/Task | {summary.avg_tokens_per_task:,.0f} |")
        lines.append(f"| Avg Cost/Task | ${summary.avg_cost_per_task:.4f} |")
        lines.append(f"| Cost/Resolved Task | ${summary.cost_per_resolved:.4f} |")
        lines.append(f"| Avg Turns/Task | {summary.avg_turns_per_task:.1f} |")
        lines.append(f"| Avg Tool Calls/Task | {summary.avg_tool_calls_per_task:.1f} |")
        lines.append(f"| Avg Duration | {summary.avg_duration_seconds:.1f}s |")
        lines.append("")

        # Quality metrics
        lines.append("## Quality")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Error Rate | {summary.error_rate:.1f}% |")
        lines.append(f"| Timeout Rate | {summary.timeout_rate:.1f}% |")
        if summary.file_localization_rate > 0:
            lines.append(f"| File Localization | {summary.file_localization_rate:.1f}% |")
        lines.append("")

        # Failure breakdown
        if summary.failure_categories:
            lines.append("## Failure Breakdown")
            lines.append("")
            lines.append("| Category | Count |")
            lines.append("|----------|-------|")
            for cat, count in sorted(
                summary.failure_categories.items(), key=lambda x: -x[1],
            ):
                lines.append(f"| {cat} | {count} |")
            lines.append("")

        # Per-task details (first 20)
        failed = [r for r in results.results if not r.resolved]
        if failed:
            lines.append("## Failed Tasks")
            lines.append("")
            for r in failed[:20]:
                errors_str = "; ".join(r.errors[:2]) if r.errors else "no errors logged"
                lines.append(f"- **{r.task_id}**: {errors_str}")
            if len(failed) > 20:
                lines.append(f"- ... and {len(failed) - 20} more")
            lines.append("")

        return "\n".join(lines)

    def generate_comparison(
        self, results_a: EvalResults, results_b: EvalResults,
    ) -> str:
        """Generate a comparison report between two evaluation runs."""
        summary_a = self._calculator.calculate(results_a)
        summary_b = self._calculator.calculate(results_b)

        lines: list[str] = []
        lines.append("# Evaluation Comparison")
        lines.append("")
        lines.append("| Metric | A | B | Delta |")
        lines.append("|--------|---|---|-------|")

        def _row(name: str, a: float, b: float, fmt: str = ".1f", unit: str = "") -> str:
            delta = b - a
            sign = "+" if delta >= 0 else ""
            return f"| {name} | {a:{fmt}}{unit} | {b:{fmt}}{unit} | {sign}{delta:{fmt}}{unit} |"

        a_id = f"{results_a.provider}/{results_a.model}"
        b_id = f"{results_b.provider}/{results_b.model}"
        lines.append(f"| Provider/Model | {a_id} | {b_id} | - |")
        lines.append(_row(
            "Resolved %", summary_a.resolved_rate,
            summary_b.resolved_rate, ".1f", "%",
        ))
        lines.append(_row(
            "Avg Tokens", summary_a.avg_tokens_per_task,
            summary_b.avg_tokens_per_task, ",.0f",
        ))
        lines.append(_row(
            "Avg Cost", summary_a.avg_cost_per_task,
            summary_b.avg_cost_per_task, ".4f", "$",
        ))
        lines.append(_row(
            "Avg Turns", summary_a.avg_turns_per_task,
            summary_b.avg_turns_per_task, ".1f",
        ))
        lines.append(_row(
            "Error Rate", summary_a.error_rate,
            summary_b.error_rate, ".1f", "%",
        ))
        lines.append("")

        return "\n".join(lines)
