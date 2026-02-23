"""Tests for additional tools — WebFetch, Question, Checkpoint, Task."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from harness.tools.checkpoint import CheckpointTool
from harness.tools.question import QuestionTool
from harness.tools.task import TaskTool
from harness.tools.web import WebFetchTool, WebSearchTool, _html_to_text
from harness.types.tools import ToolContext


def _ctx(tmp_path: Path, session_id: str = "test-session") -> ToolContext:
    return ToolContext(cwd=tmp_path, session_id=session_id)


# ---- WebFetch / WebSearch ----

class TestWebFetchTool:
    def test_definition(self):
        tool = WebFetchTool()
        defn = tool.definition
        assert defn.name == "WebFetch"
        assert any(p.name == "url" for p in defn.parameters)

    @pytest.mark.asyncio
    async def test_missing_url(self, tmp_path):
        tool = WebFetchTool()
        result = await tool.execute({}, _ctx(tmp_path))
        assert result.is_error
        assert "required" in result.content.lower()

    @pytest.mark.asyncio
    async def test_invalid_url_scheme(self, tmp_path):
        tool = WebFetchTool()
        result = await tool.execute({"url": "ftp://example.com"}, _ctx(tmp_path))
        assert result.is_error
        assert "http" in result.content.lower()


class TestHtmlToText:
    def test_strip_tags(self):
        assert _html_to_text("<p>Hello</p>") == "Hello"

    def test_strip_script(self):
        html = "<script>alert(1)</script>Hello"
        assert "alert" not in _html_to_text(html)
        assert "Hello" in _html_to_text(html)

    def test_decode_entities(self):
        assert "&amp;" not in _html_to_text("A &amp; B")
        assert "A & B" in _html_to_text("A &amp; B")

    def test_block_elements_become_newlines(self):
        html = "<p>First</p><p>Second</p>"
        result = _html_to_text(html)
        assert "First" in result
        assert "Second" in result


class TestWebSearchTool:
    def test_definition(self):
        tool = WebSearchTool()
        assert tool.definition.name == "WebSearch"

    @pytest.mark.asyncio
    async def test_returns_not_available(self, tmp_path):
        tool = WebSearchTool()
        result = await tool.execute({"query": "test"}, _ctx(tmp_path))
        assert result.is_error
        assert "not available" in result.content.lower()


# ---- QuestionTool ----

class TestQuestionTool:
    def test_definition(self):
        tool = QuestionTool()
        defn = tool.definition
        assert defn.name == "AskUser"

    @pytest.mark.asyncio
    async def test_non_interactive_returns_error(self, tmp_path):
        tool = QuestionTool(interactive=False)
        result = await tool.execute({"question": "What color?"}, _ctx(tmp_path))
        assert result.is_error
        assert "non-interactive" in result.content.lower()

    @pytest.mark.asyncio
    async def test_missing_question(self, tmp_path):
        tool = QuestionTool(interactive=True)
        result = await tool.execute({}, _ctx(tmp_path))
        assert result.is_error
        assert "required" in result.content.lower()


# ---- CheckpointTool ----

class TestCheckpointTool:
    @pytest.mark.asyncio
    async def test_save_checkpoint(self, tmp_path):
        # Create a file to checkpoint
        test_file = tmp_path / "test.py"
        test_file.write_text("original content")

        tool = CheckpointTool()
        ctx = _ctx(tmp_path)
        result = await tool.execute(
            {"action": "save", "file_path": str(test_file)},
            ctx,
        )
        assert not result.is_error
        assert "saved" in result.content.lower()

    @pytest.mark.asyncio
    async def test_save_nonexistent_file(self, tmp_path):
        tool = CheckpointTool()
        result = await tool.execute(
            {"action": "save", "file_path": str(tmp_path / "nope.py")},
            _ctx(tmp_path),
        )
        assert result.is_error
        assert "not found" in result.content.lower()

    @pytest.mark.asyncio
    async def test_restore_checkpoint(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("original content")

        tool = CheckpointTool()
        ctx = _ctx(tmp_path)

        # Save
        await tool.execute({"action": "save", "file_path": str(test_file)}, ctx)

        # Modify file
        test_file.write_text("modified content")
        assert test_file.read_text() == "modified content"

        # Restore
        result = await tool.execute(
            {"action": "restore", "file_path": str(test_file)},
            ctx,
        )
        assert not result.is_error
        assert test_file.read_text() == "original content"

    @pytest.mark.asyncio
    async def test_restore_no_checkpoint(self, tmp_path):
        tool = CheckpointTool()
        result = await tool.execute(
            {"action": "restore", "file_path": str(tmp_path / "test.py")},
            _ctx(tmp_path),
        )
        assert result.is_error
        assert "no checkpoint" in result.content.lower()

    @pytest.mark.asyncio
    async def test_list_empty(self, tmp_path):
        tool = CheckpointTool()
        result = await tool.execute({"action": "list"}, _ctx(tmp_path))
        assert not result.is_error
        assert "no checkpoints" in result.content.lower()

    @pytest.mark.asyncio
    async def test_list_with_checkpoints(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        tool = CheckpointTool()
        ctx = _ctx(tmp_path)
        await tool.execute({"action": "save", "file_path": str(test_file)}, ctx)

        result = await tool.execute({"action": "list"}, ctx)
        assert not result.is_error
        assert "test.py" in result.content

    @pytest.mark.asyncio
    async def test_invalid_action(self, tmp_path):
        tool = CheckpointTool()
        result = await tool.execute({"action": "invalid"}, _ctx(tmp_path))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_save_restore_relative_path(self, tmp_path):
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("code here")

        tool = CheckpointTool()
        ctx = _ctx(tmp_path)

        # Save with relative path
        result = await tool.execute(
            {"action": "save", "file_path": str(test_file)},
            ctx,
        )
        assert not result.is_error

        # Modify and restore
        test_file.write_text("changed")
        await tool.execute({"action": "restore", "file_path": str(test_file)}, ctx)
        assert test_file.read_text() == "code here"


# ---- TaskTool ----

class TestTaskTool:
    def test_definition(self):
        tool = TaskTool(agent_manager=None)
        defn = tool.definition
        assert defn.name == "Task"
        assert any(p.name == "prompt" for p in defn.parameters)
        assert any(p.name == "agent_type" for p in defn.parameters)

    @pytest.mark.asyncio
    async def test_missing_prompt(self, tmp_path):
        tool = TaskTool(agent_manager=None)
        result = await tool.execute({}, _ctx(tmp_path))
        assert result.is_error
        assert "required" in result.content.lower()

    @pytest.mark.asyncio
    async def test_spawn_agent(self, tmp_path):
        # Mock agent manager
        mock_mgr = AsyncMock()
        mock_mgr.spawn.return_value = "Sub-agent completed the task."

        tool = TaskTool(agent_manager=mock_mgr)
        result = await tool.execute(
            {"prompt": "Read the README", "agent_type": "explore"},
            _ctx(tmp_path),
        )
        assert not result.is_error
        assert "completed" in result.content.lower()
        mock_mgr.spawn.assert_called_once_with("explore", "Read the README")

    @pytest.mark.asyncio
    async def test_spawn_default_agent_type(self, tmp_path):
        mock_mgr = AsyncMock()
        mock_mgr.spawn.return_value = "Done."

        tool = TaskTool(agent_manager=mock_mgr)
        await tool.execute({"prompt": "Do something"}, _ctx(tmp_path))
        mock_mgr.spawn.assert_called_once_with("general", "Do something")

    @pytest.mark.asyncio
    async def test_spawn_unknown_agent(self, tmp_path):
        mock_mgr = AsyncMock()
        mock_mgr.spawn.side_effect = KeyError("Unknown agent type: 'bad'")

        tool = TaskTool(agent_manager=mock_mgr)
        result = await tool.execute(
            {"prompt": "test", "agent_type": "bad"},
            _ctx(tmp_path),
        )
        assert result.is_error

    @pytest.mark.asyncio
    async def test_spawn_failure(self, tmp_path):
        mock_mgr = AsyncMock()
        mock_mgr.spawn.side_effect = RuntimeError("Connection failed")

        tool = TaskTool(agent_manager=mock_mgr)
        result = await tool.execute(
            {"prompt": "test"},
            _ctx(tmp_path),
        )
        assert result.is_error
        assert "RuntimeError" in result.content
