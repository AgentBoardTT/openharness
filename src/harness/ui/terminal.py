"""Rich-powered terminal output."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from harness.types.messages import (
    CompactionEvent,
    Message,
    Result,
    SystemEvent,
    TextMessage,
    ToolResult,
    ToolUse,
)


class RichPrinter:
    """Rich-based message printer for terminal output.

    Replaces the basic print_message() with colored, formatted output.
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console(stderr=True)
        self._stdout = Console()  # For assistant text output
        self._partial_buffer = ""

    def print_message(self, msg: Message) -> None:
        """Print a message with Rich formatting."""
        match msg:
            case TextMessage(text=t, is_partial=True):
                self._partial_buffer += t
                self._stdout.print(t, end="", highlight=False)

            case TextMessage(text=_, is_partial=False):
                if self._partial_buffer:
                    self._stdout.print()  # Newline after streaming
                    self._partial_buffer = ""

            case ToolUse(name=name, args=args):
                self._print_tool_use(name, args)

            case ToolResult(content=content, is_error=is_error, display=display):
                self._print_tool_result(content, is_error, display)

            case Result() as r:
                self._print_result(r)

            case CompactionEvent(tokens_before=before, tokens_after=after):
                self._console.print(
                    f"[dim]Context compacted: {before:,} → {after:,} tokens[/dim]",
                )

            case SystemEvent():
                pass  # Suppress system events

    def _print_tool_use(self, name: str, args: dict[str, Any]) -> None:
        """Print a tool invocation."""
        label = Text(f"  {name}", style="bold cyan")

        detail = ""
        if name == "Bash" and "command" in args:
            detail = f" $ {args['command']}"
        elif name in ("Read", "Write", "Edit") and "file_path" in args:
            detail = f" {args['file_path']}"
        elif name == "Glob" and "pattern" in args:
            detail = f" {args['pattern']}"
        elif name == "Grep" and "pattern" in args:
            detail = f" /{args['pattern']}/"
        elif name == "Task" and "agent_type" in args:
            detail = f" [{args['agent_type']}]"
        elif name == "WebFetch" and "url" in args:
            detail = f" {args['url']}"

        if detail:
            label.append(detail, style="dim")
        self._console.print(label)

    def _print_tool_result(
        self, content: str, is_error: bool, display: str | None,
    ) -> None:
        """Print a tool result."""
        show = display or content
        if is_error:
            self._console.print(f"  [red]Error:[/red] {show[:300]}")
        elif len(show) > 300:
            self._console.print(f"  [dim]{show[:300]}...[/dim]")

    def _print_result(self, result: Result) -> None:
        """Print the final result summary."""
        self._console.print()

        parts = [
            f"[bold]Session:[/bold] {result.session_id}",
            f"[bold]Turns:[/bold] {result.turns}",
            f"[bold]Tools:[/bold] {result.tool_calls}",
        ]
        if result.total_tokens:
            parts.append(f"[bold]Tokens:[/bold] {result.total_tokens:,}")
        if result.total_cost:
            parts.append(f"[bold]Cost:[/bold] ${result.total_cost:.4f}")

        self._console.print(Panel(
            " │ ".join(parts),
            style="dim",
            expand=False,
        ))
