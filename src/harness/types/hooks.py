"""Hook types for the Harness event system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HookEvent(Enum):
    """Events that can trigger hooks."""

    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    USER_PROMPT = "user_prompt"
    AGENT_STOP = "agent_stop"
    COMPACTION = "compaction"


@dataclass(frozen=True, slots=True)
class Hook:
    """A hook that runs a command on an event."""

    event: HookEvent | str
    command: str
    matcher: str | None = None  # Tool name pattern for tool events
    timeout: float = 30.0


@dataclass(frozen=True, slots=True)
class HookResult:
    """Result from running a hook."""

    success: bool
    output: str = ""
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
