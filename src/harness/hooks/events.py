"""Hook context builder for event data."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.types.hooks import HookEvent


@dataclass(slots=True)
class HookContext:
    """Context passed to hooks when they fire."""

    event: HookEvent
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    is_error: bool = False
    session_id: str = ""
    cwd: str = ""


def build_hook_context(
    event: HookEvent,
    *,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | None = None,
    result: str | None = None,
    is_error: bool = False,
    session_id: str = "",
    cwd: str | Path = "",
) -> HookContext:
    """Build a HookContext for a given event."""
    return HookContext(
        event=event,
        tool_name=tool_name,
        tool_args=tool_args or {},
        result=result,
        is_error=is_error,
        session_id=session_id,
        cwd=str(cwd),
    )
