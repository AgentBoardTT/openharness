"""Write tool — creates or overwrites files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

_DEFINITION = ToolDef(
    name="Write",
    description=(
        "Create or overwrite a file with the given content. "
        "Parent directories are created automatically. "
        "Existing file contents are replaced entirely."
    ),
    parameters=(
        ToolParam(
            name="file_path",
            type="string",
            description="Absolute or cwd-relative path to the file to write.",
            required=True,
        ),
        ToolParam(
            name="content",
            type="string",
            description="The full content to write to the file.",
            required=True,
        ),
    ),
)


class WriteTool(BaseTool):
    """Creates or overwrites a file with the provided content."""

    @property
    def definition(self) -> ToolDef:
        return _DEFINITION

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        raw_path: str = args.get("file_path", "")
        if not raw_path:
            return self._error("file_path is required.")

        content: str = args.get("content", "")

        path = Path(raw_path)
        if not path.is_absolute():
            path = ctx.cwd / path

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except PermissionError:
            return self._error(f"Permission denied writing to: {path}")
        except OSError as exc:
            return self._error(f"OS error writing file: {exc}")

        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        byte_count = len(content.encode("utf-8"))

        return self._ok(f"File written: {path} ({lines} lines, {byte_count} bytes)")
