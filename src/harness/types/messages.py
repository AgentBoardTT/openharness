"""Message types for the Harness agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TextMessage:
    """Streaming text chunk from the model."""

    text: str
    is_partial: bool = True


@dataclass(frozen=True, slots=True)
class ToolUse:
    """Model requests a tool call."""

    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result of executing a tool."""

    tool_use_id: str
    content: str
    is_error: bool = False
    display: str | None = None


@dataclass(frozen=True, slots=True)
class Result:
    """Final result when the agent loop completes."""

    text: str
    session_id: str
    turns: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    stop_reason: str = "end_turn"


@dataclass(frozen=True, slots=True)
class CompactionEvent:
    """Context was compacted to fit within limits."""

    tokens_before: int
    tokens_after: int
    summary: str


@dataclass(frozen=True, slots=True)
class SystemEvent:
    """Lifecycle event (session start, model switch, etc.)."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


Message = (
    TextMessage | ToolUse | ToolResult | Result | CompactionEvent | SystemEvent
)
