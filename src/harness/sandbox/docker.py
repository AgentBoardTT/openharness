"""DockerSandbox — sandboxed execution via docker CLI."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

from harness.sandbox.executor import ExecutionResult, SandboxExecutor
from harness.types.sandbox import SandboxPolicy

# Paths that must never be volume-mounted into a container.
_DANGEROUS_MOUNT_ROOTS = frozenset({
    "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64",
    "/proc", "/root", "/run", "/sbin", "/sys", "/usr", "/var",
})


class DockerSandbox(SandboxExecutor):
    """Sandbox using Docker containers via the docker CLI (no SDK required).

    Security note: the ``allowed_paths`` in the policy are validated against
    a deny-list of dangerous mount roots before being passed to ``docker run
    -v``.  For true isolation, restrict ``allowed_paths`` to project
    subdirectories.
    """

    def __init__(self, policy: SandboxPolicy) -> None:
        super().__init__(policy)
        self._container_names: list[str] = []

    @staticmethod
    def _is_safe_mount(path: str) -> bool:
        """Return False if *path* would expose a dangerous host directory.

        Checks both the raw path and the resolved (symlink-expanded) path,
        since on some systems (e.g. macOS) ``/etc`` resolves to
        ``/private/etc``.
        """
        normalised = "/" + path.strip("/") if path.startswith("/") else path
        resolved = str(Path(path).resolve())
        for candidate in (normalised, resolved):
            if candidate in _DANGEROUS_MOUNT_ROOTS:
                return False
            for root in _DANGEROUS_MOUNT_ROOTS:
                if root != "/" and candidate.startswith(root + "/"):
                    return False
        return True

    def _build_docker_args(
        self, command: str, *, cwd: str | None = None, timeout_sec: float = 30.0,
    ) -> tuple[list[str], str]:
        """Build docker run arguments from policy.

        Returns (args_list, container_name).
        """
        container_name = f"harness-sandbox-{uuid.uuid4().hex[:8]}"
        limits = self._policy.resource_limits

        args = [
            "docker", "run",
            "--rm",
            f"--name={container_name}",
            f"--memory={limits.max_memory_mb}m",
            # --stop-timeout enforces a hard deadline inside Docker itself
            f"--stop-timeout={limits.max_cpu_seconds}",
        ]

        # Network policy
        if not self._policy.network.allow_network:
            args.append("--network=none")

        # Volume mounts for allowed paths — reject dangerous roots
        for path in self._policy.allowed_paths:
            if self._is_safe_mount(path):
                args.extend(["-v", f"{path}:{path}"])

        # Working directory
        if cwd:
            args.extend(["-w", cwd])

        # Image and command
        args.extend([self._policy.docker_image, "sh", "-c", command])

        return args, container_name

    async def execute(
        self, command: str, *, cwd: str | None = None, timeout_sec: float = 30.0,
    ) -> ExecutionResult:
        # Validate command first
        error = self.validate_command(command)
        if error:
            return ExecutionResult(stdout="", exit_code=1, error=error)

        docker_args, container_name = self._build_docker_args(
            command, cwd=cwd, timeout_sec=timeout_sec,
        )
        self._container_names.append(container_name)

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_sec + 10,  # grace period
                )
            except TimeoutError:
                # Kill the wrapper process; cleanup() will remove the container
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                return ExecutionResult(
                    stdout="", exit_code=-1, timed_out=True,
                )

        except OSError as exc:
            return ExecutionResult(
                stdout="", exit_code=-1,
                error=f"Failed to run docker: {exc}",
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        exit_code = proc.returncode if proc.returncode is not None else 0
        oom_killed = exit_code == 137

        # Container exited normally — remove from tracking
        if container_name in self._container_names:
            self._container_names.remove(container_name)

        return ExecutionResult(
            stdout=stdout,
            exit_code=exit_code,
            oom_killed=oom_killed,
        )

    async def cleanup(self) -> None:
        """Kill and remove any running containers."""
        for name in self._container_names:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except OSError:
                pass
        self._container_names.clear()
