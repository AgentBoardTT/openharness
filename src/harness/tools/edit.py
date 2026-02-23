"""Edit tool — performs exact string replacement in files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

_CONTEXT_LINES = 3  # Lines of context shown around a change.

_DEFINITION = ToolDef(
    name="Edit",
    description=(
        "Perform an exact string replacement in a file. "
        "By default, old_string must appear exactly once (unique match). "
        "Set replace_all=true to replace every occurrence. "
        "old_string and new_string must differ."
    ),
    parameters=(
        ToolParam(
            name="file_path",
            type="string",
            description="Absolute or cwd-relative path to the file to edit.",
            required=True,
        ),
        ToolParam(
            name="old_string",
            type="string",
            description="The exact text to find in the file.",
            required=True,
        ),
        ToolParam(
            name="new_string",
            type="string",
            description="The text to replace old_string with.",
            required=True,
        ),
        ToolParam(
            name="replace_all",
            type="boolean",
            description="Replace all occurrences instead of requiring a unique match.",
            required=False,
            default=False,
        ),
    ),
)


def _brief_context(text: str, new_string: str, n: int = _CONTEXT_LINES) -> str:
    """Return a snippet showing the first inserted block with surrounding context."""
    lines = text.splitlines()
    # Find the first line that contains any part of new_string.
    new_lines = new_string.splitlines()
    first_new = new_lines[0] if new_lines else ""
    target_idx: int | None = None
    for idx, line in enumerate(lines):
        if first_new and first_new in line:
            target_idx = idx
            break

    if target_idx is None:
        # Fall back to the first line of the file.
        target_idx = 0

    start = max(0, target_idx - n)
    end = min(len(lines), target_idx + len(new_lines) + n)
    snippet_lines = lines[start:end]
    return "\n".join(snippet_lines)


class EditTool(BaseTool):
    """Performs exact string replacement in a file."""

    @property
    def definition(self) -> ToolDef:
        return _DEFINITION

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        raw_path: str = args.get("file_path", "")
        old_string: str = args.get("old_string", "")
        new_string: str = args.get("new_string", "")
        replace_all: bool = bool(args.get("replace_all", False))

        if not raw_path:
            return self._error("file_path is required.")
        if "old_string" not in args:
            return self._error("old_string is required.")
        if "new_string" not in args:
            return self._error("new_string is required.")
        if old_string == new_string:
            return self._error("old_string and new_string must differ.")

        path = Path(raw_path)
        if not path.is_absolute():
            path = ctx.cwd / path

        try:
            original = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self._error(f"File not found: {path}")
        except IsADirectoryError:
            return self._error(f"Path is a directory, not a file: {path}")
        except PermissionError:
            return self._error(f"Permission denied reading: {path}")
        except UnicodeDecodeError:
            return self._error(f"Cannot read file as text: {path}")

        count = original.count(old_string)

        if replace_all:
            if count == 0:
                return self._error(
                    f"old_string not found in file: {path}\n"
                    "No replacements made."
                )
            updated = original.replace(old_string, new_string)
            replacements = count
        else:
            if count == 0:
                return self._error(
                    f"old_string not found in file: {path}\n"
                    "Hint: ensure the string matches the file content exactly."
                )
            if count > 1:
                return self._error(
                    f"old_string appears {count} times in {path}. "
                    "It must be unique for a safe edit. "
                    "Add more surrounding context or use replace_all=true."
                )
            updated = original.replace(old_string, new_string, 1)
            replacements = 1

        try:
            path.write_text(updated, encoding="utf-8")
        except PermissionError:
            return self._error(f"Permission denied writing: {path}")
        except OSError as exc:
            return self._error(f"OS error writing file: {exc}")

        snippet = _brief_context(updated, new_string)
        summary = (
            f"Made {replacements} replacement(s) in {path}\n"
            f"--- context ---\n{snippet}"
        )
        return self._ok(summary)
