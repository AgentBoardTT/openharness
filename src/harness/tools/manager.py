"""ToolManager — registry and dispatcher for all tools."""

from __future__ import annotations

from typing import Any

from harness.tools.base import BaseTool
from harness.tools.bash import BashTool
from harness.tools.edit import EditTool
from harness.tools.glob import GlobTool
from harness.tools.grep import GrepTool
from harness.tools.read import ReadTool
from harness.tools.write import WriteTool
from harness.types.tools import ToolContext, ToolDef, ToolResultData


class ToolManager:
    """Registers tools and dispatches execution requests.

    Usage::

        manager = ToolManager()
        manager.register_defaults()
        result = await manager.execute("Read", {"file_path": "foo.py"}, ctx)
    """

    def __init__(self) -> None:
        self._registry: dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Add a tool to the registry under its definition name."""
        self._registry[tool.definition.name] = tool

    def register_defaults(self) -> None:
        """Create and register the six built-in tools."""
        for tool in (
            ReadTool(),
            WriteTool(),
            EditTool(),
            BashTool(),
            GlobTool(),
            GrepTool(),
        ):
            self.register(tool)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool | None:
        """Return the tool with the given name, or None."""
        return self._registry.get(name)

    def get_definitions(self) -> list[ToolDef]:
        """Return all registered tool definitions (for provider schema)."""
        return [tool.definition for tool in self._registry.values()]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def execute(
        self,
        name: str,
        args: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResultData:
        """Dispatch a tool call by name.

        Returns a ToolResultData with is_error=True if the tool is not found
        or raises an unexpected exception.
        """
        tool = self._registry.get(name)
        if tool is None:
            return ToolResultData(
                content=f"Unknown tool: '{name}'. "
                f"Available tools: {sorted(self._registry)}",
                is_error=True,
            )

        try:
            return await tool.execute(args, ctx)
        except Exception as exc:  # noqa: BLE001
            return ToolResultData(
                content=f"Tool '{name}' raised an unexpected error: {exc}",
                is_error=True,
            )

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter(self, names: list[str]) -> ToolManager:
        """Return a new ToolManager containing only the named tools.

        Tools not present in this manager are silently omitted.
        """
        filtered = ToolManager()
        for name in names:
            tool = self._registry.get(name)
            if tool is not None:
                filtered.register(tool)
        return filtered

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, name: object) -> bool:
        return name in self._registry

    def __repr__(self) -> str:
        return f"ToolManager(tools={sorted(self._registry)})"
