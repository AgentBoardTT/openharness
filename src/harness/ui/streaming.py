"""Stream accumulator for buffered output."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown


class StreamAccumulator:
    """Buffers streaming text and flushes to Rich console.

    Handles partial line rendering and markdown conversion.
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()
        self._buffer = ""
        self._line_buffer = ""

    def feed(self, text: str) -> None:
        """Feed a text chunk into the accumulator."""
        self._buffer += text
        self._line_buffer += text

        # Flush complete lines
        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            self._console.print(line, highlight=False)

    def flush(self) -> str:
        """Flush any remaining buffered text and return full content."""
        if self._line_buffer:
            self._console.print(self._line_buffer, highlight=False)
            self._line_buffer = ""
        result = self._buffer
        self._buffer = ""
        return result

    def render_markdown(self) -> None:
        """Render the accumulated buffer as Markdown."""
        if self._buffer:
            self._console.print(Markdown(self._buffer))

    @property
    def content(self) -> str:
        """Return the full accumulated content without flushing."""
        return self._buffer

    def clear(self) -> None:
        """Clear all buffers."""
        self._buffer = ""
        self._line_buffer = ""
