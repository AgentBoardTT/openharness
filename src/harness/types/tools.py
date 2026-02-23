"""Tool definition types and protocols."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ToolParam:
    """A parameter for a tool."""

    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: tuple[str, ...] | None = None
    default: Any = None
    items: dict[str, Any] | None = None  # For array types: JSON Schema for items


@dataclass(frozen=True, slots=True)
class ToolDef:
    """Definition of a tool exposed to the model."""

    name: str
    description: str
    parameters: tuple[ToolParam, ...] = ()


@dataclass(slots=True)
class ToolResultData:
    """Data returned from tool execution."""

    content: str
    is_error: bool = False
    display: str | None = None  # Optional rich display for the UI


@dataclass(slots=True)
class ToolContext:
    """Context passed to tool execute methods."""

    cwd: Path
    permission_mode: str = "default"
    session_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Tool(Protocol):
    """Protocol that all tools must implement."""

    @property
    def definition(self) -> ToolDef:
        """Return the tool definition for the model."""
        ...

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        """Execute the tool with the given arguments and context."""
        ...
