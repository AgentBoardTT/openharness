"""Tests for harness.core.engine — the public run() function."""

from __future__ import annotations

from pathlib import Path

import pytest

import harness
from harness.types.messages import Result, ToolResult
from tests.conftest import MockProvider, MockTurn


class TestRun:
    @pytest.mark.asyncio
    async def test_simple_run(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
        (tmp_path / "sessions").mkdir()

        provider = MockProvider(turns=[
            MockTurn(text="I can help with that!"),
        ])

        messages = []
        async for msg in harness.run(
            "Hello",
            cwd=str(tmp_path),
            _provider=provider,
        ):
            messages.append(msg)

        result = [m for m in messages if isinstance(m, Result)][0]
        assert result.text == "I can help with that!"
        assert result.session_id

    @pytest.mark.asyncio
    async def test_run_with_tool(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
        (tmp_path / "sessions").mkdir()

        (tmp_path / "readme.md").write_text("# My Project")

        provider = MockProvider(turns=[
            MockTurn(tool_uses=[{
                "id": "tu1",
                "name": "Read",
                "args": {"file_path": str(tmp_path / "readme.md")},
            }]),
            MockTurn(text="The README contains a project heading."),
        ])

        messages = []
        async for msg in harness.run(
            "Read the README",
            cwd=str(tmp_path),
            _provider=provider,
        ):
            messages.append(msg)

        tool_results = [m for m in messages if isinstance(m, ToolResult)]
        assert len(tool_results) == 1
        assert "My Project" in tool_results[0].content

    @pytest.mark.asyncio
    async def test_run_session_persists(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
        (tmp_path / "sessions").mkdir()

        provider = MockProvider(turns=[MockTurn(text="Done.")])

        session_id = None
        async for msg in harness.run(
            "Hello",
            cwd=str(tmp_path),
            _provider=provider,
        ):
            if isinstance(msg, Result):
                session_id = msg.session_id

        assert session_id
        session_file = tmp_path / "sessions" / f"{session_id}.jsonl"
        assert session_file.exists()
        content = session_file.read_text()
        assert "Hello" in content
