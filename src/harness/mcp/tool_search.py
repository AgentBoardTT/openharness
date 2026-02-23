"""Progressive MCP tool loading via ToolSearch meta-tool."""

from __future__ import annotations

from typing import Any

from harness.mcp.manager import MCPManager
from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

_DEFINITION = ToolDef(
    name="ToolSearch",
    description=(
        "Search for available MCP tools by keyword. Use this to discover "
        "tools from connected MCP servers. Returns matching tool names "
        "and descriptions."
    ),
    parameters=(
        ToolParam(
            name="query",
            type="string",
            description="Search query to find tools by name or description.",
            required=True,
        ),
        ToolParam(
            name="max_results",
            type="integer",
            description="Maximum number of results to return (default 5).",
            required=False,
            default=5,
        ),
    ),
)


class ToolSearchTool(BaseTool):
    """Meta-tool for progressive MCP tool discovery.

    When there are many MCP tools, instead of loading all definitions
    into the context (expensive), we expose this search tool that lets
    the model discover tools on demand.
    """

    def __init__(self, mcp_manager: MCPManager) -> None:
        self._mcp = mcp_manager

    @property
    def definition(self) -> ToolDef:
        return _DEFINITION

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        query = args.get("query", "").lower()
        max_results = args.get("max_results", 5)

        if not query:
            return self._error("query is required")

        all_tools = self._mcp.get_all_tools()
        if not all_tools:
            return self._ok("No MCP tools available.")

        # Score and rank tools by relevance
        scored = []
        for tool in all_tools:
            score = 0
            name_lower = tool.name.lower()
            desc_lower = tool.description.lower()

            # Exact name match
            if query in name_lower:
                score += 10
            # Word match in name
            for word in query.split():
                if word in name_lower:
                    score += 5
                if word in desc_lower:
                    score += 2

            if score > 0:
                scored.append((score, tool))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:max_results]

        if not results:
            return self._ok(
                f"No tools matching '{query}'. "
                f"Available tools: {', '.join(t.name for t in all_tools[:10])}"
            )

        lines = [f"Found {len(results)} matching tools:\n"]
        for _, tool in results:
            lines.append(f"  {tool.name}")
            lines.append(f"    {tool.description}")
            if tool.parameters:
                param_names = [p.name for p in tool.parameters]
                lines.append(f"    Parameters: {', '.join(param_names)}")
            lines.append("")

        return self._ok("\n".join(lines))
