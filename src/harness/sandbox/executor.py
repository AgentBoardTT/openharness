"""SandboxExecutor ABC + factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from harness.types.sandbox import SandboxMode, SandboxPolicy


@dataclass(slots=True)
class ExecutionResult:
    """Result from sandboxed command execution."""

    stdout: str
    exit_code: int
    timed_out: bool = False
    oom_killed: bool = False
    error: str | None = None


class SandboxExecutor(ABC):
    """Abstract base for sandbox executors."""

    def __init__(self, policy: SandboxPolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> SandboxPolicy:
        return self._policy

    @abstractmethod
    async def execute(
        self, command: str, *, cwd: str | None = None, timeout_sec: float = 30.0,
    ) -> ExecutionResult:
        """Execute a command in the sandbox."""
        ...

    def validate_command(self, command: str) -> str | None:
        """Check if a command is allowed. Returns error message or None.

        Normalises whitespace before matching so that extra spaces or tabs
        cannot be used to bypass a blocked pattern like ``rm -rf /``.
        """
        normalised = " ".join(command.split())
        for blocked in self._policy.blocked_commands:
            normalised_blocked = " ".join(blocked.split())
            if normalised_blocked in normalised:
                return f"Command blocked by sandbox policy: contains '{blocked}'"
        return None

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        ...


def create_executor(policy: SandboxPolicy) -> SandboxExecutor:
    """Factory to create the appropriate sandbox executor."""
    if policy.mode == SandboxMode.DOCKER:
        from harness.sandbox.docker import DockerSandbox
        return DockerSandbox(policy)
    elif policy.mode == SandboxMode.PROCESS:
        from harness.sandbox.process import ProcessSandbox
        return ProcessSandbox(policy)
    else:
        raise ValueError(f"Unknown sandbox mode: {policy.mode}")
