"""Build SandboxPolicy from config."""

from __future__ import annotations

from pathlib import Path

from harness.types.config import SandboxConfig
from harness.types.sandbox import (
    NetworkPolicy,
    ResourceLimits,
    SandboxMode,
    SandboxPolicy,
)


def build_policy(config: SandboxConfig, cwd: str | None = None) -> SandboxPolicy:
    """Build a SandboxPolicy from a SandboxConfig, resolving relative paths."""
    cwd_path = Path(cwd) if cwd else Path.cwd()

    # Resolve allowed paths relative to cwd
    resolved_paths: list[str] = []
    for p in config.allowed_paths:
        path = Path(p)
        if not path.is_absolute():
            path = cwd_path / path
        resolved_paths.append(str(path.resolve()))

    try:
        mode = SandboxMode(config.mode)
    except ValueError:
        mode = SandboxMode.PROCESS

    return SandboxPolicy(
        mode=mode,
        allowed_paths=tuple(resolved_paths),
        blocked_commands=tuple(config.blocked_commands),
        resource_limits=ResourceLimits(
            max_memory_mb=config.max_memory_mb,
            max_cpu_seconds=config.max_cpu_seconds,
        ),
        network=NetworkPolicy(allow_network=config.network_access),
        docker_image=config.docker_image,
    )
