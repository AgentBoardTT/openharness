"""Glob tool — finds files matching a glob pattern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

_MAX_RESULTS = 200

# Directories to skip during glob traversal.
_IGNORED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv"})

_DEFINITION = ToolDef(
    name="Glob",
    description=(
        "Find files whose paths match a glob pattern. "
        "Results are sorted by modification time (newest first), "
        "up to 200 matches. "
        "Ignores .git, node_modules, __pycache__, and .venv directories."
    ),
    parameters=(
        ToolParam(
            name="pattern",
            type="string",
            description="Glob pattern to match against file paths (e.g. '**/*.py').",
            required=True,
        ),
        ToolParam(
            name="path",
            type="string",
            description="Directory to search in. Defaults to the current working directory.",
            required=False,
            default=None,
        ),
    ),
)


def _is_ignored(path: Path) -> bool:
    """Return True if any component of path is in the ignored set."""
    return any(part in _IGNORED_DIRS for part in path.parts)


class GlobTool(BaseTool):
    """Finds files by glob pattern, sorted by modification time."""

    @property
    def definition(self) -> ToolDef:
        return _DEFINITION

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        pattern: str = args.get("pattern", "")
        if not pattern:
            return self._error("pattern is required.")

        raw_path: str | None = args.get("path")
        if raw_path:
            search_root = Path(raw_path)
            if not search_root.is_absolute():
                search_root = ctx.cwd / search_root
        else:
            search_root = ctx.cwd

        if not search_root.exists():
            return self._error(f"Search path does not exist: {search_root}")
        if not search_root.is_dir():
            return self._error(f"Search path is not a directory: {search_root}")

        try:
            matched: list[Path] = [
                p
                for p in search_root.glob(pattern)
                if p.is_file() and not _is_ignored(p.relative_to(search_root))
            ]
        except ValueError as exc:
            # relative_to can raise ValueError for paths outside search_root.
            return self._error(f"Glob error: {exc}")
        except Exception as exc:  # noqa: BLE001
            return self._error(f"Unexpected error during glob: {exc}")

        # Sort by modification time descending (newest first).
        matched.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        results = matched[:_MAX_RESULTS]
        truncated = len(matched) - len(results)

        if not results:
            return self._ok(f"No files matched pattern '{pattern}' in {search_root}")

        lines = [str(p) for p in results]
        if truncated:
            lines.append(f"[...{truncated} more results not shown]")

        return self._ok("\n".join(lines))
