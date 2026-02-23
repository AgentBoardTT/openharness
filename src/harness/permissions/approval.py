"""Approval callback for interactive tool permission prompts."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ApprovalCallback(Protocol):
    """Protocol for requesting user approval of a tool call."""

    async def request_approval(
        self, tool_name: str, args: dict[str, Any], description: str,
    ) -> bool:
        """Ask the user whether to allow a tool call.

        Returns True if approved, False if denied.
        """
        ...


def describe_tool_call(tool_name: str, args: dict[str, Any]) -> str:
    """Build a human-readable one-line description of a tool call."""
    if tool_name == "Bash" and "command" in args:
        return f"Run command: {args['command']}"
    if tool_name == "Write" and "file_path" in args:
        content = args.get("content", "")
        lines = content.count("\n") + 1 if content else 0
        return f"Write {args['file_path']} ({lines} lines)"
    if tool_name == "Edit" and "file_path" in args:
        return f"Edit {args['file_path']}"
    if tool_name == "Read" and "file_path" in args:
        return f"Read {args['file_path']}"
    if tool_name == "Glob" and "pattern" in args:
        return f"Search files: {args['pattern']}"
    if tool_name == "Grep" and "pattern" in args:
        return f"Search content: {args['pattern']}"
    if tool_name == "Task":
        agent_type = args.get("agent_type", "unknown")
        return f"Launch sub-agent: {agent_type}"
    if tool_name == "WebFetch" and "url" in args:
        return f"Fetch URL: {args['url']}"
    # MCP tools
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        short = parts[-1] if len(parts) > 1 else tool_name
        return f"MCP tool: {short}"
    # Fallback: tool name + truncated args
    args_str = json.dumps(args, default=str)
    if len(args_str) > 80:
        args_str = args_str[:77] + "..."
    return f"{tool_name}({args_str})"


class StdinApprovalCallback:
    """Plain-text approval prompt using stdin/stdout."""

    async def request_approval(
        self, tool_name: str, args: dict[str, Any], description: str,
    ) -> bool:
        """Prompt the user with a y/n question."""
        loop = asyncio.get_running_loop()
        prompt = f"\nAllow {tool_name}? {description}\n[y/n] > "
        try:
            answer = await loop.run_in_executor(None, lambda: input(prompt))
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.strip().lower() in ("y", "yes")
