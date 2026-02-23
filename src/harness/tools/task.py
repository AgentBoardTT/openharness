"""Task tool — spawns sub-agents for complex delegated work."""

from __future__ import annotations

from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData


class TaskTool(BaseTool):
    """Spawn a sub-agent to handle a task autonomously.

    The sub-agent gets its own context and tools based on agent_type.
    """

    def __init__(self, agent_manager: Any) -> None:
        self._agent_manager = agent_manager

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="Task",
            description=(
                "Launch a sub-agent to handle a task. The sub-agent runs autonomously "
                "with its own context and returns the result. Use 'general' for full "
                "tool access, 'explore' for fast read-only search, or 'plan' for "
                "read-only planning."
            ),
            parameters=(
                ToolParam(
                    name="prompt",
                    type="string",
                    description="The task description for the sub-agent.",
                    required=True,
                ),
                ToolParam(
                    name="agent_type",
                    type="string",
                    description="The type of sub-agent to spawn.",
                    required=False,
                    enum=("general", "explore", "plan"),
                    default="general",
                ),
            ),
        )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        prompt = args.get("prompt")
        if not prompt:
            return self._error("'prompt' parameter is required.")

        agent_type = args.get("agent_type", "general")

        try:
            result = await self._agent_manager.spawn(agent_type, prompt)
            return self._ok(result)
        except KeyError as e:
            return self._error(str(e))
        except Exception as e:
            return self._error(f"Sub-agent failed: {type(e).__name__}: {e}")
