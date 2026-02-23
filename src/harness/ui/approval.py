"""Rich-formatted approval prompt for tool calls."""

from __future__ import annotations

import asyncio
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


class RichApprovalCallback:
    """Rich-formatted interactive approval prompt."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console(stderr=True)

    async def request_approval(
        self, tool_name: str, args: dict[str, Any], description: str,
    ) -> bool:
        """Show a styled approval prompt and wait for y/n."""
        title = Text(f" \u25c6 {tool_name} ", style="bold #fbbf24")
        body = Text(description, style="#94a3b8")

        self._console.print()
        self._console.print(Panel(
            body,
            title=title,
            border_style="#fbbf24",
            expand=False,
            padding=(0, 1),
        ))

        loop = asyncio.get_running_loop()
        prompt_text = "[bold #fbbf24]Allow?[/bold #fbbf24] [#7c7c8a](y/n)[/#7c7c8a] \u203a "
        try:
            self._console.print(prompt_text, end="")
            answer = await loop.run_in_executor(None, lambda: input(""))
        except (EOFError, KeyboardInterrupt):
            self._console.print()
            return False
        return answer.strip().lower() in ("y", "yes")
