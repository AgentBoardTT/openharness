"""Harness — multi-provider coding agent SDK.

Usage:
    import harness

    async for msg in harness.run("Fix the bug"):
        match msg:
            case harness.TextMessage(text=t):
                print(t, end="")
            case harness.Result(text=t):
                print(f"Done: {t}")
"""

from harness.core.engine import run
from harness.types.agents import AgentDef
from harness.types.config import MCPServerConfig, PermissionMode, RunConfig
from harness.types.hooks import Hook, HookEvent, HookResult
from harness.types.messages import (
    CompactionEvent,
    Message,
    Result,
    SystemEvent,
    TextMessage,
    ToolResult,
    ToolUse,
)
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

__version__ = "0.6.0"

__all__ = [
    # Core API
    "run",
    # Message types
    "CompactionEvent",
    "Message",
    "Result",
    "SystemEvent",
    "TextMessage",
    "ToolResult",
    "ToolUse",
    # Configuration
    "AgentDef",
    "Hook",
    "HookEvent",
    "HookResult",
    "MCPServerConfig",
    "PermissionMode",
    "RunConfig",
    # Tool types
    "ToolContext",
    "ToolDef",
    "ToolParam",
    "ToolResultData",
]
