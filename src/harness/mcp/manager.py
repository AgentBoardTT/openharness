"""Multi-server MCP manager."""

from __future__ import annotations

import logging
from typing import Any

from harness.mcp.client import MCPClient
from harness.types.config import MCPServerConfig
from harness.types.tools import ToolDef, ToolResultData

logger = logging.getLogger(__name__)


class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}

    async def add_server(self, name: str, config: MCPServerConfig) -> None:
        """Add and connect to an MCP server."""
        client = MCPClient(name, config)
        try:
            await client.connect()
            self._clients[name] = client
            logger.info("Added MCP server: %s (%d tools)", name, len(client.tools))
        except Exception as exc:
            logger.error("Failed to connect MCP server '%s': %s", name, exc)
            raise

    def get_all_tools(self) -> list[ToolDef]:
        """Get all tools from all connected servers."""
        tools = []
        for client in self._clients.values():
            tools.extend(client.tools)
        return tools

    def get_server_for_tool(self, tool_name: str) -> tuple[MCPClient, str] | None:
        """Find which server owns a tool. Returns (client, short_name) or None.

        tool_name is the full prefixed name like "mcp__postgres__query".
        """
        parts = tool_name.split("__", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return None
        server_name = parts[1]
        short_name = parts[2]
        client = self._clients.get(server_name)
        if client is None:
            return None
        return client, short_name

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> ToolResultData:
        """Route a tool call to the correct MCP server."""
        result = self.get_server_for_tool(tool_name)
        if result is None:
            return ToolResultData(
                content=f"No MCP server found for tool: {tool_name}",
                is_error=True,
            )
        client, short_name = result
        return await client.call_tool(short_name, args)

    async def disconnect_all(self) -> None:
        """Disconnect all MCP servers."""
        for name, client in self._clients.items():
            try:
                await client.disconnect()
                logger.info("Disconnected MCP server: %s", name)
            except Exception as exc:
                logger.warning("Error disconnecting '%s': %s", name, exc)
        self._clients.clear()

    @property
    def server_count(self) -> int:
        return len(self._clients)

    @property
    def tool_count(self) -> int:
        return sum(len(c.tools) for c in self._clients.values())
