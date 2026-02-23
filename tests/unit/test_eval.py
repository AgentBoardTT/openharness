"""Tests for harness.eval — types, metrics, report generation, bench runners."""

from __future__ import annotations

from datetime import datetime

from harness.eval.harness_bench import HARNESS_BENCH_TASKS, HarnessBenchRunner
from harness.eval.metrics import MetricsCalculator
from harness.eval.report import ReportGenerator
from harness.eval.types import (
    BenchmarkTask,
    EvalConfig,
    EvalResults,
    FailureCategory,
    TaskResult,
)

# ---- Eval Types ----


class TestEvalTypes:
    def test_task_result_defaults(self):
        r = TaskResult(task_id="t1")
        assert r.task_id == "t1"
        assert r.resolved is False
        assert r.tokens_used == 0
        assert r.errors == []

    def test_task_result_with_values(self):
        r = TaskResult(
            task_id="t2",
            resolved=True,
            tokens_used=5000,
            cost=0.05,
            turns=3,
            tool_calls=7,
            duration_seconds=12.5,
        )
        assert r.resolved is True
        assert r.cost == 0.05

    def test_failure_category_enum(self):
        assert FailureCategory.WRONG_FILE.value == "wrong_file"
        assert FailureCategory.TIMEOUT.value == "timeout"
        assert len(FailureCategory) == 11

    def test_eval_config_defaults(self):
        cfg = EvalConfig()
        assert cfg.provider == "anthropic"
        assert cfg.max_turns == 100
        assert cfg.permission_mode == "bypass"
        assert "Read" in cfg.tools

    def test_benchmark_task(self):
        task = BenchmarkTask(
            id="bt1",
            description="Fix a bug",
            repo="foo/bar",
            category="bugfix",
        )
        assert task.id == "bt1"
        assert task.category == "bugfix"


class TestEvalResults:
    def _make_results(self, resolved_flags: list[bool]) -> EvalResults:
        results = EvalResults(
            benchmark="test",
            split="default",
            provider="mock",
            model="mock-model",
        )
        for i, resolved in enumerate(resolved_flags):
            results.results.append(TaskResult(
                task_id=f"t{i}",
                resolved=resolved,
                tokens_used=1000,
                cost=0.01,
                turns=2,
                tool_calls=4,
                duration_seconds=10.0,
            ))
        return results

    def test_resolved_rate(self):
        results = self._make_results([True, True, False, True, False])
        assert results.resolved_rate == 60.0

    def test_resolved_count(self):
        results = self._make_results([True, False, True])
        assert results.resolved_count == 2
        assert results.total_tasks == 3

    def test_total_tokens(self):
        results = self._make_results([True, True])
        assert results.total_tokens == 2000

    def test_total_cost(self):
        results = self._make_results([True, True, True])
        assert abs(results.total_cost - 0.03) < 1e-10

    def test_avg_turns(self):
        results = self._make_results([True, True])
        assert results.avg_turns == 2.0

    def test_avg_tool_calls(self):
        results = self._make_results([True])
        assert results.avg_tool_calls == 4.0

    def test_avg_duration(self):
        results = self._make_results([True, False])
        assert results.avg_duration == 10.0

    def test_empty_results(self):
        results = EvalResults(
            benchmark="test", split="default", provider="x", model="y",
        )
        assert results.resolved_rate == 0.0
        assert results.total_tasks == 0
        assert results.avg_turns == 0.0


# ---- Metrics Calculator ----


class TestMetricsCalculator:
    def _make_results(self) -> EvalResults:
        results = EvalResults(
            benchmark="test", split="default", provider="mock", model="mock-model",
        )
        results.results = [
            TaskResult(task_id="t1", resolved=True, tokens_used=1000, cost=0.01,
                       turns=2, tool_calls=4, duration_seconds=10.0),
            TaskResult(task_id="t2", resolved=True, tokens_used=2000, cost=0.02,
                       turns=3, tool_calls=6, duration_seconds=15.0),
            TaskResult(task_id="t3", resolved=False, tokens_used=3000, cost=0.03,
                       turns=5, tool_calls=10, duration_seconds=20.0,
                       errors=["SomeError: failed"],
                       failure_category=FailureCategory.WRONG_EDIT),
            TaskResult(task_id="t4", resolved=False, tokens_used=500, cost=0.005,
                       turns=1, tool_calls=1, duration_seconds=350.0,
                       failure_category=FailureCategory.TIMEOUT),
        ]
        return results

    def test_calculate_basic(self):
        calc = MetricsCalculator()
        summary = calc.calculate(self._make_results())

        assert summary.total_tasks == 4
        assert summary.resolved_count == 2
        assert summary.resolved_rate == 50.0

    def test_efficiency_metrics(self):
        calc = MetricsCalculator()
        summary = calc.calculate(self._make_results())

        assert summary.avg_tokens_per_task == (1000 + 2000 + 3000 + 500) / 4
        assert abs(summary.avg_cost_per_task - (0.01 + 0.02 + 0.03 + 0.005) / 4) < 1e-10

    def test_cost_per_resolved(self):
        calc = MetricsCalculator()
        summary = calc.calculate(self._make_results())

        total_cost = 0.01 + 0.02 + 0.03 + 0.005
        assert abs(summary.cost_per_resolved - total_cost / 2) < 1e-10

    def test_error_rate(self):
        calc = MetricsCalculator()
        summary = calc.calculate(self._make_results())

        # 1 out of 4 tasks had errors
        assert summary.error_rate == 25.0

    def test_timeout_rate(self):
        calc = MetricsCalculator()
        summary = calc.calculate(self._make_results())

        # 1 out of 4 tasks had duration > 300s
        assert summary.timeout_rate == 25.0

    def test_failure_breakdown(self):
        calc = MetricsCalculator()
        summary = calc.calculate(self._make_results())

        assert "wrong_edit" in summary.failure_categories
        assert "timeout" in summary.failure_categories
        assert summary.failure_categories["wrong_edit"] == 1

    def test_empty_results(self):
        calc = MetricsCalculator()
        results = EvalResults(
            benchmark="test", split="default", provider="x", model="y",
        )
        summary = calc.calculate(results)
        assert summary.total_tasks == 0
        assert summary.resolved_rate == 0.0

    def test_file_localization(self):
        calc = MetricsCalculator()
        results = EvalResults(
            benchmark="test", split="default", provider="x", model="y",
        )
        results.results = [
            TaskResult(
                task_id="t1", resolved=True,
                modified_files=["a.py", "b.py"],
                expected_files=["a.py", "b.py"],
            ),
            TaskResult(
                task_id="t2", resolved=False,
                modified_files=["a.py", "c.py"],
                expected_files=["a.py", "b.py"],
            ),
        ]
        summary = calc.calculate(results)
        assert summary.file_localization_rate == 50.0


# ---- Report Generator ----


class TestReportGenerator:
    def _make_results(self) -> EvalResults:
        results = EvalResults(
            benchmark="test-bench",
            split="lite",
            provider="anthropic",
            model="claude-sonnet-4-6",
            started_at=datetime(2024, 1, 15, 10, 30),
        )
        results.results = [
            TaskResult(task_id="t1", resolved=True, tokens_used=1000, cost=0.01,
                       turns=2, tool_calls=4, duration_seconds=10.0),
            TaskResult(task_id="t2", resolved=False, tokens_used=2000, cost=0.02,
                       turns=5, tool_calls=8, duration_seconds=20.0,
                       errors=["Edit failed: ambiguous match"]),
        ]
        return results

    def test_generate_report(self):
        gen = ReportGenerator()
        report = gen.generate(self._make_results())

        assert "# Evaluation Report: test-bench" in report
        assert "anthropic" in report
        assert "claude-sonnet-4-6" in report
        assert "50.0%" in report
        assert "Failed Tasks" in report
        assert "t2" in report

    def test_report_has_metrics_table(self):
        gen = ReportGenerator()
        report = gen.generate(self._make_results())

        assert "Resolved" in report
        assert "Avg Tokens" in report
        assert "Avg Cost" in report
        assert "Avg Turns" in report

    def test_generate_comparison(self):
        gen = ReportGenerator()
        results_a = EvalResults(
            benchmark="test", split="default", provider="anthropic", model="sonnet",
        )
        results_a.results = [
            TaskResult(task_id="t1", resolved=True, tokens_used=1000, cost=0.01, turns=2),
        ]
        results_b = EvalResults(
            benchmark="test", split="default", provider="openai", model="gpt-4o",
        )
        results_b.results = [
            TaskResult(task_id="t1", resolved=True, tokens_used=2000, cost=0.02, turns=3),
        ]

        report = gen.generate_comparison(results_a, results_b)
        assert "Comparison" in report
        assert "anthropic" in report
        assert "openai" in report

    def test_empty_results_report(self):
        gen = ReportGenerator()
        results = EvalResults(
            benchmark="empty", split="default", provider="x", model="y",
        )
        report = gen.generate(results)
        assert "# Evaluation Report: empty" in report


# ---- Harness Bench ----


class TestHarnessBench:
    def test_tasks_defined(self):
        assert len(HARNESS_BENCH_TASKS) >= 8

    def test_task_ids_unique(self):
        ids = [t["id"] for t in HARNESS_BENCH_TASKS]
        assert len(ids) == len(set(ids))

    def test_all_tasks_have_description(self):
        for task in HARNESS_BENCH_TASKS:
            assert "description" in task
            assert len(task["description"]) > 10

    def test_load_tasks(self):
        config = EvalConfig()
        runner = HarnessBenchRunner(config)
        tasks = runner.load_tasks()
        assert len(tasks) == len(HARNESS_BENCH_TASKS)

    def test_load_tasks_with_limit(self):
        config = EvalConfig(max_tasks=3)
        runner = HarnessBenchRunner(config)
        tasks = runner.load_tasks(max_tasks=3)
        assert len(tasks) == 3

    def test_task_categories(self):
        categories = {t["category"] for t in HARNESS_BENCH_TASKS}
        assert "multi_file" in categories
        assert "recovery" in categories
        assert "bugfix" in categories
