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
