"""SWE-bench evaluation runner.

Runs the Harness agent against SWE-bench tasks and collects results.
Requires: pip install swebench datasets
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from harness.eval.types import BenchmarkTask, EvalConfig, EvalResults, TaskResult


class SWEBenchRunner:
    """Run Harness against SWE-bench benchmark tasks.

    Supports: swe-bench-lite, swe-bench-verified, swe-bench-full.
    """

    DATASET_MAP = {
        "lite": "princeton-nlp/SWE-bench_Lite",
        "verified": "princeton-nlp/SWE-bench_Verified",
        "full": "princeton-nlp/SWE-bench",
    }

    def __init__(self, config: EvalConfig) -> None:
        self._config = config
        self._output_dir = Path("eval-results")

    def load_tasks(self, max_tasks: int | None = None) -> list[BenchmarkTask]:
        """Load SWE-bench tasks from the HuggingFace dataset."""
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError(
                "Install the datasets package: pip install datasets"
            ) from None

        dataset_name = self.DATASET_MAP.get(self._config.split, self._config.split)
        ds = load_dataset(dataset_name, split="test")

        tasks = []
        for item in ds:
            task = BenchmarkTask(
                id=item["instance_id"],
                description=item.get("problem_statement", ""),
                repo=item.get("repo", ""),
                category=item.get("repo", "").split("/")[-1] if item.get("repo") else "",
                metadata={
                    "base_commit": item.get("base_commit", ""),
                    "hints_text": item.get("hints_text", ""),
                    "created_at": item.get("created_at", ""),
                    "version": item.get("version", ""),
                },
            )
            tasks.append(task)
            if max_tasks and len(tasks) >= max_tasks:
                break

        return tasks

    async def run(self, tasks: list[BenchmarkTask] | None = None) -> EvalResults:
        """Run evaluation on all tasks."""
        from datetime import datetime

        if tasks is None:
            tasks = self.load_tasks(max_tasks=self._config.max_tasks)

        results = EvalResults(
            benchmark="swe-bench",
            split=self._config.split,
            provider=self._config.provider,
            model=self._config.model or "default",
            config=self._config,
        )

        for i, task in enumerate(tasks):
            print(f"[{i + 1}/{len(tasks)}] {task.id}...")
            task_result = await self._run_task(task)
            results.results.append(task_result)

            # Save intermediate results
            self._save_results(results)

        results.completed_at = datetime.now()
        self._save_results(results)
        return results

    async def _run_task(self, task: BenchmarkTask) -> TaskResult:
        """Run the agent on a single task."""
        import harness

        start_time = time.time()
        result = TaskResult(task_id=task.id)

        try:
            accumulated_text = ""
            async for msg in harness.run(
                task.description,
                provider=self._config.provider,
                model=self._config.model,
                permission_mode=self._config.permission_mode,
                max_turns=self._config.max_turns,
                max_tokens=self._config.max_tokens,
                tools=self._config.tools,
            ):
                match msg:
                    case harness.TextMessage(text=t, is_partial=False):
                        accumulated_text = t
                    case harness.Result() as r:
                        result.tokens_used = r.total_tokens
                        result.cost = r.total_cost
                        result.turns = r.turns
                        result.tool_calls = r.tool_calls

            result.patch = accumulated_text
            result.duration_seconds = time.time() - start_time
        except Exception as e:
            result.errors.append(f"{type(e).__name__}: {e}")
            result.duration_seconds = time.time() - start_time

        return result

    def _save_results(self, results: EvalResults) -> None:
        """Save results to disk."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"swe-bench-{self._config.split}.jsonl"

        with open(path, "w") as f:
            for r in results.results:
                entry = {
                    "instance_id": r.task_id,
                    "model_name_or_path": f"{results.provider}/{results.model}",
                    "model_patch": r.patch,
                    "resolved": r.resolved,
                    "tokens": r.tokens_used,
                    "cost": r.cost,
                    "turns": r.turns,
                    "tool_calls": r.tool_calls,
                    "duration": r.duration_seconds,
                    "errors": r.errors,
                }
                f.write(json.dumps(entry) + "\n")
