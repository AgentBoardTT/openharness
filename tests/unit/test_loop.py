"""Tests for harness.core.loop — the core agent loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.loop import AgentLoop
from harness.core.session import Session
from harness.types.config import PermissionMode, RunConfig
from harness.types.messages import Result, ToolResult, ToolUse
from tests.conftest import MockProvider, MockTurn


def _make_loop(
    tmp_path: Path,
    turns: list[MockTurn],
    monkeypatch,
) -> AgentLoop:
    """Helper to create an AgentLoop with MockProvider."""
    monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
    (tmp_path / "sessions").mkdir(exist_ok=True)

    provider = MockProvider(turns=turns)
    config = RunConfig(cwd=str(tmp_path), permission_mode=PermissionMode.BYPASS)

    # Create tools
    from harness.tools.manager import ToolManager
    mgr = ToolManager()
    mgr.register_defaults()
    tool_names = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
    tools = {n: mgr.get(n) for n in tool_names if mgr.get(n)}

    session = Session(cwd=str(tmp_path))
    return AgentLoop(provider=provider, tools=tools, config=config, session=session)


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_simple_text_response(self, tmp_path: Path, monkeypatch):
        loop = _make_loop(tmp_path, [
            MockTurn(text="Hello! I'm ready to help."),
        ], monkeypatch)

        messages = []
        async for msg in loop.run("Hi there"):
            messages.append(msg)

        # Should have: SystemEvent, TextMessage (partial), TextMessage (full), Result
        types = [type(m).__name__ for m in messages]
        assert "SystemEvent" in types
        assert "TextMessage" in types
        assert "Result" in types

        result = [m for m in messages if isinstance(m, Result)][0]
        assert result.text == "Hello! I'm ready to help."
        assert result.turns == 1
        assert result.tool_calls == 0

    @pytest.mark.asyncio
    async def test_tool_call_flow(self, tmp_path: Path, monkeypatch):
        # Create a file to read
        (tmp_path / "test.txt").write_text("Hello world\n")

        loop = _make_loop(tmp_path, [
            MockTurn(
                text="Let me read that file.",
                tool_uses=[{
                    "id": "tu1", "name": "Read",
                    "args": {"file_path": str(tmp_path / "test.txt")},
                }],
            ),
            MockTurn(text="The file contains 'Hello world'."),
        ], monkeypatch)

        messages = []
        async for msg in loop.run("Read test.txt"):
            messages.append(msg)

        # Should see ToolUse and ToolResult
        tool_uses = [m for m in messages if isinstance(m, ToolUse)]
        tool_results = [m for m in messages if isinstance(m, ToolResult)]
        assert len(tool_uses) == 1
        assert tool_uses[0].name == "Read"
        assert len(tool_results) == 1
        assert not tool_results[0].is_error
        assert "Hello world" in tool_results[0].content

        result = [m for m in messages if isinstance(m, Result)][0]
        assert result.turns == 2
        assert result.tool_calls == 1

    @pytest.mark.asyncio
    async def test_unknown_tool(self, tmp_path: Path, monkeypatch):
        loop = _make_loop(tmp_path, [
            MockTurn(tool_uses=[{"id": "tu1", "name": "FakeTool", "args": {}}]),
            MockTurn(text="Sorry, that tool doesn't exist."),
        ], monkeypatch)

        messages = []
        async for msg in loop.run("Use FakeTool"):
            messages.append(msg)

        tool_results = [m for m in messages if isinstance(m, ToolResult)]
        assert len(tool_results) == 1
        assert tool_results[0].is_error
        assert "Unknown tool" in tool_results[0].content

    @pytest.mark.asyncio
    async def test_write_tool(self, tmp_path: Path, monkeypatch):
        out_path = str(tmp_path / "output.txt")
        loop = _make_loop(tmp_path, [
            MockTurn(tool_uses=[{
                "id": "tu1",
                "name": "Write",
                "args": {"file_path": out_path, "content": "Written by agent"},
            }]),
            MockTurn(text="File written successfully."),
        ], monkeypatch)

        messages = []
        async for msg in loop.run("Write output.txt"):
            messages.append(msg)

        assert Path(out_path).read_text() == "Written by agent"

    @pytest.mark.asyncio
    async def test_bash_tool(self, tmp_path: Path, monkeypatch):
        loop = _make_loop(tmp_path, [
            MockTurn(tool_uses=[{
                "id": "tu1",
                "name": "Bash",
                "args": {"command": "echo 'test output'"},
            }]),
            MockTurn(text="The command output was 'test output'."),
        ], monkeypatch)

        messages = []
        async for msg in loop.run("Run echo"):
            messages.append(msg)

        tool_results = [m for m in messages if isinstance(m, ToolResult)]
        assert len(tool_results) == 1
        assert "test output" in tool_results[0].content

    @pytest.mark.asyncio
    async def test_multi_tool_single_turn(self, tmp_path: Path, monkeypatch):
        (tmp_path / "a.txt").write_text("File A")
        (tmp_path / "b.txt").write_text("File B")

        loop = _make_loop(tmp_path, [
            MockTurn(tool_uses=[
                {"id": "tu1", "name": "Read", "args": {"file_path": str(tmp_path / "a.txt")}},
                {"id": "tu2", "name": "Read", "args": {"file_path": str(tmp_path / "b.txt")}},
            ]),
            MockTurn(text="Both files read."),
        ], monkeypatch)

        messages = []
        async for msg in loop.run("Read both files"):
            messages.append(msg)

        tool_results = [m for m in messages if isinstance(m, ToolResult)]
        assert len(tool_results) == 2

        result = [m for m in messages if isinstance(m, Result)][0]
        assert result.tool_calls == 2
