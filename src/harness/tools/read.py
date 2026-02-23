"""Read tool — reads files with optional line range."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

_MAX_LINE_LENGTH = 2000
_DEFAULT_LIMIT = 2000

_DEFINITION = ToolDef(
    name="Read",
    description=(
        "Read a file from the local filesystem. "
        "Optionally specify an offset (1-based line number to start from) "
        "and a limit (number of lines to read). "
        "Lines longer than 2000 characters are truncated. "
        "Returns content with line numbers in cat -n style."
    ),
    parameters=(
        ToolParam(
            name="file_path",
            type="string",
            description="Absolute or cwd-relative path to the file to read.",
            required=True,
        ),
        ToolParam(
            name="offset",
            type="integer",
            description="1-based line number to start reading from.",
            required=False,
            default=None,
        ),
        ToolParam(
            name="limit",
            type="integer",
            description=f"Maximum number of lines to return (default {_DEFAULT_LIMIT}).",
            required=False,
            default=None,
        ),
    ),
)


class ReadTool(BaseTool):
    """Reads a file and returns its content with line numbers."""

    @property
    def definition(self) -> ToolDef:
        return _DEFINITION

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        raw_path: str = args.get("file_path", "")
        if not raw_path:
            return self._error("file_path is required.")

        offset: int | None = args.get("offset")
        limit: int | None = args.get("limit")

        path = Path(raw_path)
        if not path.is_absolute():
            path = ctx.cwd / path

        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self._error(f"File not found: {path}")
        except IsADirectoryError:
            return self._error(f"Path is a directory, not a file: {path}")
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except UnicodeDecodeError:
            return self._error(
                f"Cannot read file as text (binary or unsupported encoding): {path}"
            )

        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        # Resolve the slice bounds (1-based offset -> 0-based index).
        start_idx = (offset - 1) if offset is not None else 0
        start_idx = max(0, start_idx)

        effective_limit = limit if limit is not None else _DEFAULT_LIMIT
        end_idx = start_idx + effective_limit

        selected = lines[start_idx:end_idx]

        numbered: list[str] = []
        for i, line in enumerate(selected, start=start_idx + 1):
            # Strip trailing newline for display, then truncate if needed.
            display_line = line.rstrip("\n\r")
            if len(display_line) > _MAX_LINE_LENGTH:
                display_line = display_line[:_MAX_LINE_LENGTH] + " [truncated]"
            numbered.append(f"{i:>6}\t{display_line}")

        content = "\n".join(numbered)

        if end_idx < total_lines:
            content += f"\n[...{total_lines - end_idx} more lines not shown (offset={end_idx + 1})]"

        return self._ok(content)
