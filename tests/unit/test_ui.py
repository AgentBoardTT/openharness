"""Tests for harness.ui — Rich printer, streaming, and diff rendering."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from harness.types.messages import (
    CompactionEvent,
    Result,
    SystemEvent,
    TextMessage,
    ToolResult,
    ToolUse,
)
from harness.ui.diff import render_diff
from harness.ui.streaming import StreamAccumulator
from harness.ui.terminal import RichPrinter


class TestRichPrinter:
    def _make_printer(self):
        """Create a RichPrinter with captured console output."""
        stderr_buf = StringIO()
        stdout_buf = StringIO()
        console = Console(file=stderr_buf, force_terminal=True, width=120)
        stdout_console = Console(file=stdout_buf, force_terminal=True, width=120)
        printer = RichPrinter(console=console)
        printer._stdout = stdout_console
        return printer, stderr_buf, stdout_buf

    def test_print_partial_text(self):
        printer, _, stdout_buf = self._make_printer()
        printer.print_message(TextMessage(text="Hello", is_partial=True))
        assert "Hello" in stdout_buf.getvalue()

    def test_print_tool_use_bash(self):
        printer, stderr_buf, _ = self._make_printer()
        printer.print_message(ToolUse(id="t1", name="Bash", args={"command": "ls -la"}))
        output = stderr_buf.getvalue()
        assert "Bash" in output
        assert "ls -la" in output

    def test_print_tool_use_read(self):
        printer, stderr_buf, _ = self._make_printer()
        printer.print_message(ToolUse(id="t1", name="Read", args={"file_path": "/tmp/test.py"}))
        output = stderr_buf.getvalue()
        assert "Read" in output
        assert "/tmp/test.py" in output

    def test_print_tool_use_task(self):
        printer, stderr_buf, _ = self._make_printer()
        printer.print_message(ToolUse(id="t1", name="Task", args={"agent_type": "explore"}))
        output = stderr_buf.getvalue()
        assert "Task" in output
        assert "explore" in output

    def test_print_tool_result_error(self):
        printer, stderr_buf, _ = self._make_printer()
        printer.print_message(ToolResult(
            tool_use_id="t1", content="File not found", is_error=True,
        ))
        output = stderr_buf.getvalue()
        assert "Error" in output

    def test_print_result(self):
        printer, stderr_buf, _ = self._make_printer()
        printer.print_message(Result(
            text="Done",
            session_id="abc123",
            turns=3,
            tool_calls=5,
            total_tokens=1000,
            total_cost=0.005,
        ))
        output = stderr_buf.getvalue()
        assert "abc123" in output
        assert "1,000" in output

    def test_print_compaction(self):
        printer, stderr_buf, _ = self._make_printer()
        printer.print_message(CompactionEvent(
            tokens_before=50000, tokens_after=25000, summary="Compacted",
        ))
        output = stderr_buf.getvalue()
        # Rich may insert ANSI codes within numbers, so check key words
        assert "compacted" in output.lower()
        assert "tokens" in output.lower()

    def test_system_event_suppressed(self):
        printer, stderr_buf, _ = self._make_printer()
        printer.print_message(SystemEvent(type="session_start", data={}))
        assert stderr_buf.getvalue().strip() == ""


class TestStreamAccumulator:
    def test_feed_and_content(self):
        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=120)
        acc = StreamAccumulator(console=console)
        acc.feed("Hello ")
        acc.feed("World")
        assert acc.content == "Hello World"

    def test_flush_returns_content(self):
        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=120)
        acc = StreamAccumulator(console=console)
        acc.feed("Test content\n")
        result = acc.flush()
        assert result == "Test content\n"
        assert acc.content == ""

    def test_clear(self):
        acc = StreamAccumulator()
        acc.feed("data")
        acc.clear()
        assert acc.content == ""

    def test_newline_flushing(self):
        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=120)
        acc = StreamAccumulator(console=console)
        acc.feed("line1\nline2\n")
        output = buf.getvalue()
        assert "line1" in output
        assert "line2" in output


class TestDiffRendering:
    def test_no_changes(self):
        result = render_diff("hello\n", "hello\n")
        assert result == "(no changes)"

    def test_simple_diff(self):
        old = "line 1\nline 2\nline 3\n"
        new = "line 1\nline 2 modified\nline 3\n"
        result = render_diff(old, new, "test.py")
        assert "-line 2" in result
        assert "+line 2 modified" in result

    def test_diff_with_filename(self):
        old = "a\n"
        new = "b\n"
        result = render_diff(old, new, "myfile.py")
        assert "a/myfile.py" in result
        assert "b/myfile.py" in result

    def test_diff_with_console(self):
        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=120)
        old = "line 1\n"
        new = "line 2\n"
        result = render_diff(old, new, "test.py", console=console)
        assert "-line 1" in result
        assert "+line 2" in result
        # Console should have received output
        assert len(buf.getvalue()) > 0

    def test_addition(self):
        old = "line 1\n"
        new = "line 1\nline 2\n"
        result = render_diff(old, new, "test.py")
        assert "+line 2" in result

    def test_deletion(self):
        old = "line 1\nline 2\n"
        new = "line 1\n"
        result = render_diff(old, new, "test.py")
        assert "-line 2" in result
