"""Rich-powered terminal output."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
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

# ── Palette ──────────────────────────────────────────────────────────────────
# A cohesive set of styles used across all output.  Tweak these to re-skin
# the entire terminal experience in one place.

TOOL_ICONS: dict[str, str] = {
    "Bash": "\u2588",       # █  solid block — shell commands
    "Read": "\u25b8",       # ▸  right-pointing triangle — reading
    "Write": "\u25b8",      # ▸
    "Edit": "\u25b8",       # ▸
    "Glob": "\u25cb",       # ○  circle — search
    "Grep": "\u25cb",       # ○
    "Task": "\u25c6",       # ◆  diamond — sub-agent
    "WebFetch": "\u25c6",   # ◆
}
DEFAULT_ICON = "\u25b8"     # ▸

STYLE_TOOL_NAME = "bold #a78bfa"      # violet — primary accent
STYLE_TOOL_DETAIL = "#7c7c8a"         # muted grey
STYLE_TOOL_BASH_CMD = "bold #e2e8f0"  # bright white for shell commands
STYLE_ERROR_LABEL = "bold #f87171"    # red
STYLE_ERROR_BODY = "#f87171"
STYLE_RESULT_DIM = "dim #7c7c8a"
STYLE_RESULT_LABEL = "bold #94a3b8"   # slate
STYLE_RESULT_VALUE = "#e2e8f0"        # light
STYLE_COST_VALUE = "#34d399"          # green
STYLE_COMPACTION = "dim italic #94a3b8"


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
                    f"  [dim]\u2500\u2500[/dim] [{STYLE_COMPACTION}]"
                    f"Context compacted: {before:,} \u2192 {after:,} tokens[/]",
                )

            case SystemEvent():
                pass  # Suppress system events

    # ── Tool Use ─────────────────────────────────────────────────────────────

    def _print_tool_use(self, name: str, args: dict[str, Any]) -> None:
        """Print a tool invocation with icon, styled name, and detail."""
        icon = TOOL_ICONS.get(name, DEFAULT_ICON)
        line = Text()
        line.append(f"  {icon} ", style=STYLE_TOOL_NAME)
        line.append(name, style=STYLE_TOOL_NAME)

        detail = self._tool_detail(name, args)
        if detail:
            line.append("  ", style="default")
            if name == "Bash":
                line.append(detail, style=STYLE_TOOL_BASH_CMD)
            else:
                line.append(detail, style=STYLE_TOOL_DETAIL)

        self._console.print(line)

    @staticmethod
    def _tool_detail(name: str, args: dict[str, Any]) -> str:
        if name == "Bash" and "command" in args:
            cmd = args["command"]
            return f"$ {cmd}" if len(cmd) <= 120 else f"$ {cmd[:117]}..."
        if name in ("Read", "Write", "Edit") and "file_path" in args:
            return args["file_path"]
        if name == "Glob" and "pattern" in args:
            return args["pattern"]
        if name == "Grep" and "pattern" in args:
            return f"/{args['pattern']}/"
        if name == "Task":
            agent = args.get("agent_type", "general")
            prompt = args.get("prompt", "")
            snippet = prompt[:60] + ("\u2026" if len(prompt) > 60 else "")
            return f"[{agent}] {snippet}" if snippet else f"[{agent}]"
        if name == "WebFetch" and "url" in args:
            return args["url"]
        return ""

    # ── Tool Result ──────────────────────────────────────────────────────────

    def _print_tool_result(
        self, content: str, is_error: bool, display: str | None,
    ) -> None:
        """Print a tool result — errors are prominent, success is quiet."""
        show = display or content
        if is_error:
            label = Text("    \u2717 ", style=STYLE_ERROR_LABEL)
            label.append(show[:300], style=STYLE_ERROR_BODY)
            self._console.print(label)
        elif len(show) > 300:
            # Truncated long results shown dim
            self._console.print(
                Text(f"    {show[:300]}\u2026", style=STYLE_RESULT_DIM),
            )

    # ── Final Result ─────────────────────────────────────────────────────────

    def _print_result(self, result: Result) -> None:
        """Print the session result summary as a compact, styled table."""
        self._console.print()

        tbl = Table(
            show_header=False,
            show_edge=False,
            show_lines=False,
            padding=(0, 1),
            expand=False,
        )
        tbl.add_column(style=STYLE_RESULT_LABEL, justify="right", no_wrap=True)
        tbl.add_column(style=STYLE_RESULT_VALUE, no_wrap=True)

        tbl.add_row("Session", str(result.session_id))
        tbl.add_row("Turns", str(result.turns))
        tbl.add_row("Tool calls", str(result.tool_calls))
        if result.total_tokens:
            tbl.add_row("Tokens", f"{result.total_tokens:,}")
        if result.total_cost:
            tbl.add_row("Cost", Text(f"${result.total_cost:.4f}", style=STYLE_COST_VALUE))

        self._console.print(Panel(
            tbl,
            border_style="#3f3f50",
            expand=False,
            padding=(0, 1),
        ))
