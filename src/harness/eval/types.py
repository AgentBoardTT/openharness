"""Evaluation types and result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FailureCategory(Enum):
    """Categories for task failure analysis."""

    WRONG_FILE = "wrong_file"
    WRONG_EDIT = "wrong_edit"
    WRONG_TOOL = "wrong_tool"
    CONTEXT_OVERFLOW = "context_overflow"
    LOOP_STUCK = "loop_stuck"
    PERMISSION_DENIED = "permission_denied"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    INCOMPLETE = "incomplete"
    OVERCOMPLETE = "overcomplete"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class TaskResult:
    """Result of running the agent on a single evaluation task."""

    task_id: str
    resolved: bool = False
    patch: str = ""
    tokens_used: int = 0
    cost: float = 0.0
    turns: int = 0
    tool_calls: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    failure_category: FailureCategory | None = None
    modified_files: list[str] = field(default_factory=list)
    expected_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalConfig:
    """Configuration for an evaluation run."""

    provider: str = "anthropic"
    model: str | None = None
    benchmark: str = "harness_bench"
    split: str = "default"
    max_tasks: int | None = None
    max_turns: int = 100
    max_tokens: int = 16384
    timeout_seconds: int = 600
    runs_per_task: int = 1
    permission_mode: str = "bypass"
    tools: list[str] = field(
        default_factory=lambda: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    )


@dataclass(slots=True)
class EvalResults:
    """Aggregated results from an evaluation run."""

    benchmark: str
    split: str
    provider: str
    model: str
    results: list[TaskResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    config: EvalConfig = field(default_factory=EvalConfig)

    @property
    def total_tasks(self) -> int:
        return len(self.results)

    @property
    def resolved_count(self) -> int:
        return sum(1 for r in self.results if r.resolved)

    @property
    def resolved_rate(self) -> float:
        if not self.results:
            return 0.0
        return (self.resolved_count / self.total_tasks) * 100

    @property
    def total_tokens(self) -> int:
        return sum(r.tokens_used for r in self.results)

    @property
    def total_cost(self) -> float:
        return sum(r.cost for r in self.results)

    @property
    def avg_turns(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.turns for r in self.results) / len(self.results)

    @property
    def avg_tool_calls(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.tool_calls for r in self.results) / len(self.results)

    @property
    def avg_duration(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.duration_seconds for r in self.results) / len(self.results)


@dataclass(slots=True)
class BenchmarkTask:
    """A single benchmark task to evaluate."""

    id: str
    description: str
    repo: str = ""
    test_commands: list[str] = field(default_factory=list)
    expected_files: list[str] = field(default_factory=list)
    category: str = ""
    difficulty: str = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)
