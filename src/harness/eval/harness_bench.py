"""Harness-Bench — custom benchmark for harness-specific capabilities.

Tests capabilities unique to our harness: multi-file editing, error recovery,
context management, tool efficiency, sub-agents, and session continuity.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from harness.eval.types import BenchmarkTask, EvalConfig, EvalResults, TaskResult

# Built-in benchmark tasks testing harness-specific capabilities
HARNESS_BENCH_TASKS: list[dict[str, Any]] = [
    # Multi-file editing
    {
        "id": "hb-multi-file-01",
        "category": "multi_file",
        "difficulty": "medium",
        "description": (
            "In the project directory, find the function `calculate_total()` and rename it "
            "to `compute_total()`. Update all callers across all files."
        ),
        "setup_files": {
            "src/calc.py": (
                "def calculate_total(items):\n"
                "    return sum(i.price for i in items)\n"
            ),
            "src/api.py": (
                "from src.calc import calculate_total\n\n"
                "def get_total(cart):\n"
                "    return calculate_total(cart.items)\n"
            ),
            "src/views.py": (
                "from src.calc import calculate_total\n\n"
                "def render(cart):\n"
                "    total = calculate_total(cart.items)\n"
                "    return f'Total: {total}'\n"
            ),
            "tests/test_calc.py": (
                "from src.calc import calculate_total\n\n"
                "def test_total():\n"
                "    assert calculate_total([]) == 0\n"
            ),
        },
        "verify": "grep -r 'compute_total' src/ tests/ && ! grep -r 'calculate_total' src/ tests/",
    },
    # Error recovery
    {
        "id": "hb-recovery-01",
        "category": "recovery",
        "difficulty": "medium",
        "description": (
            "Fix the syntax error in main.py that prevents it from running. "
            "Then verify it works by running it."
        ),
        "setup_files": {
            "main.py": "def greet(name):\n    print(f'Hello, {name}!'\n\ngreet('World')\n",
        },
        "verify": "python main.py",
    },
    # Tool efficiency
    {
        "id": "hb-tool-efficiency-01",
        "category": "tools",
        "difficulty": "easy",
        "description": "Find all Python files in the project that contain the word 'TODO'.",
        "setup_files": {
            "src/a.py": "# TODO: implement\ndef a(): pass\n",
            "src/b.py": "def b(): pass\n",
            "src/c.py": "# TODO: refactor\ndef c(): pass\n",
            "src/d.py": "def d(): pass  # TODO later\n",
            "README.md": "# Project\nTODO: write docs\n",
        },
        "verify": None,  # Manual: check tool call count is reasonable
    },
    # Context management
    {
        "id": "hb-context-01",
        "category": "context",
        "difficulty": "hard",
        "description": (
            "Read the configuration in config.py, then create a new module "
            "database.py that implements the Database class using the settings "
            "from config.py."
        ),
        "setup_files": {
            "config.py": (
                "DB_HOST = 'localhost'\n"
                "DB_PORT = 5432\n"
                "DB_NAME = 'myapp'\n"
                "DB_USER = 'admin'\n"
            ),
        },
        "verify": "python -c 'from database import Database'",
    },
    # File creation
    {
        "id": "hb-create-01",
        "category": "creation",
        "difficulty": "easy",
        "description": (
            "Create a Python file called `utils.py` with a function `is_palindrome(s)` "
            "that returns True if the string s is a palindrome (case-insensitive)."
        ),
        "setup_files": {},
        "verify": (
            "python -c \"from utils import is_palindrome; "
            "assert is_palindrome('Racecar'); "
            "assert not is_palindrome('hello')\""
        ),
    },
    # Bug fix with test
    {
        "id": "hb-bugfix-01",
        "category": "bugfix",
        "difficulty": "medium",
        "description": (
            "The function `divide(a, b)` in math_utils.py crashes when b is 0. "
            "Fix it to return None when dividing by zero, and verify the existing test passes."
        ),
        "setup_files": {
            "math_utils.py": "def divide(a, b):\n    return a / b\n",
            "test_math.py": (
                "from math_utils import divide\n\n"
                "def test_divide():\n"
                "    assert divide(10, 2) == 5\n"
                "    assert divide(0, 1) == 0\n"
                "    assert divide(10, 0) is None\n"
            ),
        },
        "verify": "python -m pytest test_math.py -v",
    },
    # Read and analyze
    {
        "id": "hb-analyze-01",
        "category": "analysis",
        "difficulty": "easy",
        "description": "Read app.py and list all the imported modules.",
        "setup_files": {
            "app.py": (
                "import os\n"
                "import sys\n"
                "from pathlib import Path\n"
                "from collections import defaultdict\n"
                "import json\n\n"
                "def main():\n"
                "    pass\n"
            ),
        },
        "verify": None,
    },
    # Refactoring
    {
        "id": "hb-refactor-01",
        "category": "refactor",
        "difficulty": "medium",
        "description": (
            "The file handlers.py has duplicated error handling in each function. "
            "Extract the common try/except pattern into a decorator called `handle_errors`."
        ),
        "setup_files": {
            "handlers.py": (
                "def get_user(user_id):\n"
                "    try:\n"
                "        return {'id': user_id, 'name': 'Alice'}\n"
                "    except Exception as e:\n"
                "        print(f'Error: {e}')\n"
                "        return None\n\n"
                "def get_item(item_id):\n"
                "    try:\n"
                "        return {'id': item_id, 'name': 'Widget'}\n"
                "    except Exception as e:\n"
                "        print(f'Error: {e}')\n"
                "        return None\n"
            ),
        },
        "verify": "python -c 'from handlers import handle_errors, get_user, get_item'",
    },
]


class HarnessBenchRunner:
    """Run Harness against our custom benchmark tasks."""

    def __init__(self, config: EvalConfig) -> None:
        self._config = config

    def load_tasks(self, max_tasks: int | None = None) -> list[BenchmarkTask]:
        """Load built-in harness benchmark tasks."""
        tasks = []
        for task_def in HARNESS_BENCH_TASKS:
            task = BenchmarkTask(
                id=task_def["id"],
                description=task_def["description"],
                category=task_def.get("category", ""),
                difficulty=task_def.get("difficulty", "medium"),
                metadata={
                    "setup_files": task_def.get("setup_files", {}),
                    "verify": task_def.get("verify"),
                },
            )
            tasks.append(task)
            if max_tasks and len(tasks) >= max_tasks:
                break
        return tasks

    async def run(
        self,
        tasks: list[BenchmarkTask] | None = None,
        work_dir: Path | None = None,
    ) -> EvalResults:
        """Run evaluation on harness benchmark tasks."""
        from datetime import datetime

        if tasks is None:
            tasks = self.load_tasks(max_tasks=self._config.max_tasks)

        results = EvalResults(
            benchmark="harness-bench",
            split="default",
            provider=self._config.provider,
            model=self._config.model or "default",
            config=self._config,
        )

        for i, task in enumerate(tasks):
            print(f"[{i + 1}/{len(tasks)}] {task.id} ({task.category})...")
            task_result = await self._run_task(task, work_dir)
            results.results.append(task_result)

        results.completed_at = datetime.now()
        return results

    async def _run_task(
        self, task: BenchmarkTask, work_dir: Path | None = None,
    ) -> TaskResult:
        """Run agent on a single benchmark task."""
        import tempfile

        import harness

        result = TaskResult(task_id=task.id)

        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)

            # Set up files
            setup_files = task.metadata.get("setup_files", {})
            for filepath, content in setup_files.items():
                full_path = task_dir / filepath
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            # Run agent
            start_time = time.time()
            try:
                async for msg in harness.run(
                    task.description,
                    provider=self._config.provider,
                    model=self._config.model,
                    permission_mode=self._config.permission_mode,
                    max_turns=self._config.max_turns,
                    cwd=str(task_dir),
                    tools=self._config.tools,
                ):
                    match msg:
                        case harness.Result() as r:
                            result.tokens_used = r.total_tokens
                            result.cost = r.total_cost
                            result.turns = r.turns
                            result.tool_calls = r.tool_calls

                result.duration_seconds = time.time() - start_time

                # Verify result if verify command is provided
                verify_cmd = task.metadata.get("verify")
                if verify_cmd:
                    result.resolved = await self._verify(verify_cmd, task_dir)
                else:
                    # No verification — mark as resolved if no errors
                    result.resolved = len(result.errors) == 0

            except Exception as e:
                result.errors.append(f"{type(e).__name__}: {e}")
                result.duration_seconds = time.time() - start_time

        return result

    async def _verify(self, command: str, cwd: Path) -> bool:
        """Run a verification command and return True if it succeeds."""
        import asyncio

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            return proc.returncode == 0
        except (TimeoutError, Exception):
            return False
