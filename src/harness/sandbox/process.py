"""ProcessSandbox — sandboxed execution via setrlimit."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from harness.sandbox.executor import ExecutionResult, SandboxExecutor
from harness.types.sandbox import SandboxPolicy


class ProcessSandbox(SandboxExecutor):
    """Sandbox using subprocess with resource limits via setrlimit.

    Works on macOS and Linux. Uses RLIMIT_AS for memory, RLIMIT_CPU for CPU time,
    RLIMIT_NPROC for process count.
    """

    def __init__(self, policy: SandboxPolicy) -> None:
        super().__init__(policy)

    async def execute(
        self, command: str, *, cwd: str | None = None, timeout_sec: float = 30.0,
    ) -> ExecutionResult:
        # Validate command first
        error = self.validate_command(command)
        if error:
            return ExecutionResult(stdout="", exit_code=1, error=error)

        # Build environment: strip sensitive vars
        env = {k: v for k, v in os.environ.items() if k not in self._policy.strip_env}

        # Use policy timeout if not specified
        if timeout_sec <= 0:
            timeout_sec = float(self._policy.resource_limits.max_cpu_seconds)

        def _preexec() -> None:
            """Set resource limits in the child process (Unix only)."""
            if sys.platform == "win32":
                return
            import resource

            limits = self._policy.resource_limits

            # Memory limit (RLIMIT_AS)
            mem_bytes = limits.max_memory_mb * 1024 * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except (ValueError, OSError):
                pass

            # CPU time limit (RLIMIT_CPU)
            try:
                resource.setrlimit(
                    resource.RLIMIT_CPU,
                    (limits.max_cpu_seconds, limits.max_cpu_seconds),
                )
            except (ValueError, OSError):
                pass

            # Process count limit (RLIMIT_NPROC)
            try:
                resource.setrlimit(
                    resource.RLIMIT_NPROC,
                    (limits.max_processes, limits.max_processes),
                )
            except (ValueError, OSError):
                pass

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
                env=env,
                preexec_fn=_preexec if sys.platform != "win32" else None,
            )

            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_sec,
                )
            except TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                return ExecutionResult(
                    stdout="", exit_code=-1, timed_out=True,
                    error=f"Command timed out after {timeout_sec}s",
                )

        except OSError as exc:
            return ExecutionResult(
                stdout="", exit_code=-1, error=f"Failed to start process: {exc}",
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        exit_code = proc.returncode if proc.returncode is not None else 0

        # Detect OOM kill (exit code 137 = killed by signal 9)
        oom_killed = exit_code == 137

        return ExecutionResult(
            stdout=stdout,
            exit_code=exit_code,
            oom_killed=oom_killed,
        )

    async def cleanup(self) -> None:
        """No cleanup needed for process sandbox."""
        pass
