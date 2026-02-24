"""Configuration types for Harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionMode(Enum):
    """Permission modes controlling what the agent can do without asking."""

    DEFAULT = "default"  # Ask for everything
    ACCEPT_EDITS = "accept_edits"  # Auto-approve file operations
    PLAN = "plan"  # Read-only mode
    BYPASS = "bypass"  # Auto-approve everything


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    """Configuration for an MCP server."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"  # "stdio" or "http"
    url: str | None = None  # For HTTP transport


@dataclass(frozen=True, slots=True)
class AuditConfig:
    """Configuration for the audit/compliance engine."""

    enabled: bool = False
    scan_pii: bool = True
    retention_days: int = 90
    retention_max_size_mb: int = 0
    log_tool_args: bool = True


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Configuration for the policy-as-code engine."""

    policy_paths: tuple[str, ...] = ()
    simulation_mode: bool = False


@dataclass(frozen=True, slots=True)
class RouterConfigData:
    """Configuration for the universal model router."""

    strategy: str = "manual"
    fallback_chain: tuple[str, ...] = ()
    max_cost_per_session: float = 0.0
    max_tokens_per_session: int = 0
    simple_task_model: str | None = None


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """Configuration for the sandboxed execution runtime."""

    enabled: bool = False
    mode: str = "process"
    allowed_paths: tuple[str, ...] = ()
    blocked_commands: tuple[str, ...] = ()
    max_memory_mb: int = 512
    max_cpu_seconds: int = 30
    network_access: bool = False
    docker_image: str = "python:3.12-slim"


@dataclass(slots=True)
class RunConfig:
    """Configuration for a single harness.run() invocation."""

    provider: str = "anthropic"
    model: str | None = None
    tools: list[str] = field(
        default_factory=lambda: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    )
    mcp_servers: dict[str, MCPServerConfig] = field(default_factory=dict)
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    session_id: str | None = None
    max_turns: int = 100
    max_tokens: int = 16384
    cwd: str | None = None
    system_prompt: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    audit: AuditConfig | None = None
    policy: PolicyConfig | None = None
    router: RouterConfigData | None = None
    sandbox: SandboxConfig | None = None
