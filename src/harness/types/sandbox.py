"""Sandbox execution types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SandboxMode(Enum):
    """Sandbox execution mode."""

    NONE = "none"
    PROCESS = "process"
    DOCKER = "docker"


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Resource limits for sandboxed execution."""

    max_memory_mb: int = 512
    max_cpu_seconds: int = 30
    max_processes: int = 64
    max_file_size_mb: int = 100


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    """Network access policy for sandboxed execution."""

    allow_network: bool = False
    allowed_hosts: tuple[str, ...] = ()
    blocked_ports: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Complete sandbox policy combining all restrictions."""

    mode: SandboxMode = SandboxMode.PROCESS
    allowed_paths: tuple[str, ...] = ()
    blocked_commands: tuple[str, ...] = ()
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    docker_image: str = "python:3.12-slim"
    env_passthrough: tuple[str, ...] = ()
    strip_env: tuple[str, ...] = (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
    )
