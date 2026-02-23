"""Tests for harness.tools module."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.tools.bash import BashTool
from harness.tools.edit import EditTool
from harness.tools.glob import GlobTool
from harness.tools.grep import GrepTool
from harness.tools.manager import ToolManager
from harness.tools.read import ReadTool
from harness.tools.write import WriteTool
from harness.types.tools import ToolContext


def _ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(cwd=tmp_path)


class TestReadTool:
    @pytest.mark.asyncio
    async def test_read_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("line 1\nline 2\nline 3\n")
        tool = ReadTool()
        result = await tool.execute({"file_path": str(f)}, _ctx(tmp_path))
        assert not result.is_error
        assert "line 1" in result.content
        assert "line 2" in result.content

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, tmp_path: Path):
        tool = ReadTool()
        result = await tool.execute({"file_path": str(tmp_path / "nope.txt")}, _ctx(tmp_path))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_read_with_offset_limit(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("\n".join(f"line {i}" for i in range(1, 101)))
        tool = ReadTool()
        result = await tool.execute({"file_path": str(f), "offset": 10, "limit": 5}, _ctx(tmp_path))
        assert not result.is_error
        assert "line 10" in result.content or "line 11" in result.content

    @pytest.mark.asyncio
    async def test_read_relative_path(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        tool = ReadTool()
        result = await tool.execute({"file_path": "hello.txt"}, _ctx(tmp_path))
        assert not result.is_error
        assert "hello world" in result.content


class TestWriteTool:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_path: Path):
        tool = WriteTool()
        path = str(tmp_path / "output.txt")
        result = await tool.execute({"file_path": path, "content": "hello world"}, _ctx(tmp_path))
        assert not result.is_error
        assert Path(path).read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_write_creates_dirs(self, tmp_path: Path):
        tool = WriteTool()
        path = str(tmp_path / "a" / "b" / "c.txt")
        result = await tool.execute({"file_path": path, "content": "nested"}, _ctx(tmp_path))
        assert not result.is_error
        assert Path(path).read_text() == "nested"

    @pytest.mark.asyncio
    async def test_write_overwrites(self, tmp_path: Path):
        f = tmp_path / "existing.txt"
        f.write_text("old content")
        tool = WriteTool()
        result = await tool.execute({"file_path": str(f), "content": "new content"}, _ctx(tmp_path))
        assert not result.is_error
        assert f.read_text() == "new content"


class TestEditTool:
    @pytest.mark.asyncio
    async def test_edit_replace(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    print('hello')\n")
        tool = EditTool()
        result = await tool.execute({
            "file_path": str(f),
            "old_string": "print('hello')",
            "new_string": "print('world')",
        }, _ctx(tmp_path))
        assert not result.is_error
        assert "print('world')" in f.read_text()

    @pytest.mark.asyncio
    async def test_edit_not_found(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    pass\n")
        tool = EditTool()
        result = await tool.execute({
            "file_path": str(f),
            "old_string": "nonexistent string",
            "new_string": "replacement",
        }, _ctx(tmp_path))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_edit_ambiguous(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\nx = 1\n")
        tool = EditTool()
        result = await tool.execute({
            "file_path": str(f),
            "old_string": "x = 1",
            "new_string": "x = 2",
        }, _ctx(tmp_path))
        assert result.is_error  # Not unique

    @pytest.mark.asyncio
    async def test_edit_replace_all(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\nx = 1\n")
        tool = EditTool()
        result = await tool.execute({
            "file_path": str(f),
            "old_string": "x = 1",
            "new_string": "x = 2",
            "replace_all": True,
        }, _ctx(tmp_path))
        assert not result.is_error
        assert f.read_text() == "x = 2\nx = 2\n"


class TestBashTool:
    @pytest.mark.asyncio
    async def test_bash_echo(self, tmp_path: Path):
        tool = BashTool()
        result = await tool.execute({"command": "echo hello"}, _ctx(tmp_path))
        assert not result.is_error
        assert "hello" in result.content

    @pytest.mark.asyncio
    async def test_bash_exit_code(self, tmp_path: Path):
        tool = BashTool()
        result = await tool.execute({"command": "exit 42"}, _ctx(tmp_path))
        assert "42" in result.content

    @pytest.mark.asyncio
    async def test_bash_cwd(self, tmp_path: Path):
        tool = BashTool()
        result = await tool.execute({"command": "pwd"}, _ctx(tmp_path))
        assert not result.is_error
        assert str(tmp_path) in result.content


class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob_pattern(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.py"}, _ctx(tmp_path))
        assert not result.is_error
        assert "a.py" in result.content
        assert "b.py" in result.content
        assert "c.txt" not in result.content

    @pytest.mark.asyncio
    async def test_glob_recursive(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("")
        tool = GlobTool()
        result = await tool.execute({"pattern": "**/*.py"}, _ctx(tmp_path))
        assert not result.is_error
        assert "deep.py" in result.content


class TestGrepTool:
    @pytest.mark.asyncio
    async def test_grep_basic(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("def hello():\n    return 'world'\n")
        tool = GrepTool()
        result = await tool.execute({"pattern": "hello"}, _ctx(tmp_path))
        assert not result.is_error
        assert "hello" in result.content

    @pytest.mark.asyncio
    async def test_grep_no_match(self, tmp_path: Path):
        (tmp_path / "test.py").write_text("def hello():\n    return 'world'\n")
        tool = GrepTool()
        result = await tool.execute({"pattern": "nonexistent_xyz"}, _ctx(tmp_path))
        assert not result.is_error
        assert "No matches" in result.content or result.content.strip() == ""


class TestToolManager:
    def test_register_defaults(self):
        m = ToolManager()
        m.register_defaults()
        assert len(m) == 6
        assert "Read" in m
        assert "Write" in m
        assert "Edit" in m
        assert "Bash" in m
        assert "Glob" in m
        assert "Grep" in m

    def test_get_definitions(self):
        m = ToolManager()
        m.register_defaults()
        defs = m.get_definitions()
        assert len(defs) == 6
        names = {d.name for d in defs}
        assert names == {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}

    def test_filter(self):
        m = ToolManager()
        m.register_defaults()
        filtered = m.filter(["Read", "Bash"])
        assert len(filtered) == 2
        assert "Read" in filtered
        assert "Bash" in filtered
        assert "Write" not in filtered

    @pytest.mark.asyncio
    async def test_execute_unknown(self, tmp_path: Path):
        m = ToolManager()
        m.register_defaults()
        result = await m.execute("NonExistent", {}, _ctx(tmp_path))
        assert result.is_error
