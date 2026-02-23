"""Tests for the MCP system (without real MCP servers)."""

from pathlib import Path

import pytest

from harness.mcp.manager import MCPManager
from harness.mcp.tool_search import ToolSearchTool
from harness.types.tools import ToolContext, ToolDef, ToolParam


class TestMCPManager:
    def test_empty_manager(self):
        mgr = MCPManager()
        assert mgr.server_count == 0
        assert mgr.tool_count == 0
        assert mgr.get_all_tools() == []

    def test_get_server_for_tool_parsing(self):
        mgr = MCPManager()
        # No server connected, but parsing should work
        result = mgr.get_server_for_tool("mcp__postgres__query")
        # No client registered, returns None
        assert result is None

    def test_invalid_tool_name_format(self):
        mgr = MCPManager()
        assert mgr.get_server_for_tool("Read") is None
        assert mgr.get_server_for_tool("mcp__only_two") is None
        assert mgr.get_server_for_tool("") is None

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self):
        mgr = MCPManager()
        result = await mgr.call_tool("mcp__unknown__tool", {})
        assert result.is_error is True
        assert "No MCP server found" in result.content

    @pytest.mark.asyncio
    async def test_disconnect_all_empty(self):
        mgr = MCPManager()
        await mgr.disconnect_all()  # Should not raise
        assert mgr.server_count == 0


class TestToolSearchTool:
    def _make_manager_with_tools(self) -> MCPManager:
        """Create an MCPManager with mock tools injected."""
        mgr = MCPManager()
        # Inject fake tools by manipulating internal state
        from harness.mcp.client import MCPClient
        from harness.types.config import MCPServerConfig

        client = MCPClient("test", MCPServerConfig(command="echo"))
        client._tools = [
            ToolDef(
                name="mcp__test__read_file",
                description="Read a file from the filesystem",
                parameters=(
                    ToolParam(name="path", type="string", description="File path"),
                ),
            ),
            ToolDef(
                name="mcp__test__write_file",
                description="Write content to a file",
                parameters=(
                    ToolParam(name="path", type="string", description="File path"),
                    ToolParam(name="content", type="string", description="Content to write"),
                ),
            ),
            ToolDef(
                name="mcp__test__query_db",
                description="Execute a database query",
                parameters=(
                    ToolParam(name="sql", type="string", description="SQL query"),
                ),
            ),
        ]
        client._connected = True
        mgr._clients["test"] = client
        return mgr

    @pytest.mark.asyncio
    async def test_search_by_name(self):
        mgr = self._make_manager_with_tools()
        tool = ToolSearchTool(mgr)
        ctx = ToolContext(cwd=Path("/tmp"))
        result = await tool.execute({"query": "read"}, ctx)
        assert not result.is_error
        assert "read_file" in result.content

    @pytest.mark.asyncio
    async def test_search_by_description(self):
        mgr = self._make_manager_with_tools()
        tool = ToolSearchTool(mgr)
        ctx = ToolContext(cwd=Path("/tmp"))
        result = await tool.execute({"query": "database"}, ctx)
        assert not result.is_error
        assert "query_db" in result.content

    @pytest.mark.asyncio
    async def test_no_match_shows_available(self):
        mgr = self._make_manager_with_tools()
        tool = ToolSearchTool(mgr)
        ctx = ToolContext(cwd=Path("/tmp"))
        result = await tool.execute({"query": "nonexistent_xyz"}, ctx)
        assert not result.is_error
        assert "No tools matching" in result.content
        assert "mcp__test__" in result.content  # Shows available tools

    @pytest.mark.asyncio
    async def test_empty_query_error(self):
        mgr = self._make_manager_with_tools()
        tool = ToolSearchTool(mgr)
        ctx = ToolContext(cwd=Path("/tmp"))
        result = await tool.execute({"query": ""}, ctx)
        assert result.is_error

    @pytest.mark.asyncio
    async def test_no_tools_available(self):
        mgr = MCPManager()
        tool = ToolSearchTool(mgr)
        ctx = ToolContext(cwd=Path("/tmp"))
        result = await tool.execute({"query": "anything"}, ctx)
        assert "No MCP tools available" in result.content

    def test_definition(self):
        mgr = MCPManager()
        tool = ToolSearchTool(mgr)
        defn = tool.definition
        assert defn.name == "ToolSearch"
        assert len(defn.parameters) == 2
