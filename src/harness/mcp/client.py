"""Low-level MCP client wrapping the official mcp SDK."""

from __future__ import annotations

import logging
from typing import Any

from harness.types.config import MCPServerConfig
from harness.types.tools import ToolDef, ToolParam, ToolResultData

logger = logging.getLogger(__name__)


class MCPClient:
    """Manages a connection to a single MCP server."""

    def __init__(self, name: str, config: MCPServerConfig):
        self.name = name
        self._config = config
        self._session = None
        self._read = None
        self._write = None
        self._tools: list[ToolDef] = []
        self._connected = False

    async def connect(self) -> None:
        """Connect to the MCP server via stdio transport."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise ImportError(
                "The 'mcp' package is required for MCP support. "
                "Install it with: pip install mcp"
            ) from exc

        params = StdioServerParameters(
            command=self._config.command,
            args=self._config.args,
            env=self._config.env if self._config.env else None,
        )

        self._read, self._write = await stdio_client(params).__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()
        await self._session.initialize()
        self._connected = True

        # Discover tools
        await self._discover_tools()
        logger.info(
            "MCP server '%s' connected with %d tools",
            self.name, len(self._tools),
        )

    async def _discover_tools(self) -> None:
        """Fetch available tools from the MCP server."""
        if not self._session:
            return

        result = await self._session.list_tools()
        self._tools = []
        for tool in result.tools:
            params = []
            if tool.inputSchema and "properties" in tool.inputSchema:
                required = set(tool.inputSchema.get("required", []))
                for pname, pschema in tool.inputSchema["properties"].items():
                    params.append(ToolParam(
                        name=pname,
                        type=pschema.get("type", "string"),
                        description=pschema.get("description", ""),
                        required=pname in required,
                    ))
            self._tools.append(ToolDef(
                name=f"mcp__{self.name}__{tool.name}",
                description=tool.description or f"MCP tool from {self.name}",
                parameters=tuple(params),
            ))

    @property
    def tools(self) -> list[ToolDef]:
        """Return discovered tool definitions."""
        return list(self._tools)

    @property
    def connected(self) -> bool:
        return self._connected

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> ToolResultData:
        """Call a tool on the MCP server.

        tool_name should be the short name (without mcp__server__ prefix).
        """
        if not self._session:
            return ToolResultData(
                content=f"MCP server '{self.name}' not connected",
                is_error=True,
            )
        try:
            result = await self._session.call_tool(tool_name, args)
            # Extract text content from the result
            content_parts = []
            is_error = result.isError if hasattr(result, 'isError') else False
            for item in result.content:
                if hasattr(item, 'text'):
                    content_parts.append(item.text)
                elif hasattr(item, 'data'):
                    content_parts.append(str(item.data))
                else:
                    content_parts.append(str(item))
            return ToolResultData(
                content="\n".join(content_parts) if content_parts else "No output",
                is_error=is_error,
            )
        except Exception as exc:
            return ToolResultData(
                content=f"MCP tool error: {type(exc).__name__}: {exc}",
                is_error=True,
            )

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
        self._connected = False
        self._session = None
