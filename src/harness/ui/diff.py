"""Syntax-highlighted diff rendering."""

from __future__ import annotations

import difflib

from rich.console import Console
from rich.text import Text


def render_diff(
    old: str,
    new: str,
    filename: str = "",
    *,
    console: Console | None = None,
) -> str:
    """Render a unified diff between old and new content.

    Returns the diff as a string. If a console is provided,
    also prints it with syntax highlighting.
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}" if filename else "a/file",
        tofile=f"b/{filename}" if filename else "b/file",
        lineterm="",
    ))

    if not diff_lines:
        return "(no changes)"

    diff_text = "\n".join(diff_lines)

    if console is not None:
        _print_colored_diff(console, diff_lines)

    return diff_text


def _print_colored_diff(console: Console, lines: list[str]) -> None:
    """Print diff lines with color highlighting."""
    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            console.print(Text(line, style="bold"))
        elif line.startswith("@@"):
            console.print(Text(line, style="cyan"))
        elif line.startswith("+"):
            console.print(Text(line, style="green"))
        elif line.startswith("-"):
            console.print(Text(line, style="red"))
        else:
            console.print(Text(line, style="dim"))
