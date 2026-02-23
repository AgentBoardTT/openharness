"""Grep tool — searches file content using ripgrep or Python fallback."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

_DEFAULT_MAX_RESULTS = 50

_IGNORED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv"})

_DEFINITION = ToolDef(
    name="Grep",
    description=(
        "Search for a regex pattern in file contents. "
        "Uses ripgrep (rg) when available, otherwise falls back to Python re. "
        "Returns matching lines as 'path:line_number: content'. "
        "Ignores binary files and common build/cache directories."
    ),
    parameters=(
        ToolParam(
            name="pattern",
            type="string",
            description="Regular expression pattern to search for.",
            required=True,
        ),
        ToolParam(
            name="path",
            type="string",
            description="Directory or file to search in. Defaults to cwd.",
            required=False,
            default=None,
        ),
        ToolParam(
            name="glob",
            type="string",
            description="Glob pattern to filter which files are searched (e.g. '*.py').",
            required=False,
            default=None,
        ),
        ToolParam(
            name="include",
            type="string",
            description="Alias for glob — file-name pattern to include.",
            required=False,
            default=None,
        ),
        ToolParam(
            name="max_results",
            type="integer",
            description=f"Max matching lines to return (default {_DEFAULT_MAX_RESULTS}).",
            required=False,
            default=_DEFAULT_MAX_RESULTS,
        ),
    ),
)


# ---------------------------------------------------------------------------
# ripgrep backend
# ---------------------------------------------------------------------------

async def _rg_search(
    pattern: str,
    search_path: Path,
    glob_filter: str | None,
    max_results: int,
) -> list[str] | None:
    """Run ripgrep and parse JSON output.

    Returns a list of formatted match strings, or None if rg is unavailable.
    """
    if not shutil.which("rg"):
        return None

    cmd: list[str] = [
        "rg",
        "--json",
        "--max-count", str(max_results),
        "--max-total-count", str(max_results),
    ]
    if glob_filter:
        cmd += ["--glob", glob_filter]

    cmd += [pattern, str(search_path)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    except (TimeoutError, OSError):
        return None

    matches: list[str] = []
    for line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get("type") != "match":
            continue

        data = obj.get("data", {})
        file_path = data.get("path", {}).get("text", "")
        line_number = data.get("line_number", 0)
        text = data.get("lines", {}).get("text", "").rstrip("\n")
        matches.append(f"{file_path}:{line_number}: {text}")

    return matches


# ---------------------------------------------------------------------------
# Python fallback backend
# ---------------------------------------------------------------------------

def _is_ignored(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return any(part in _IGNORED_DIRS for part in rel.parts)


def _is_binary(path: Path) -> bool:
    """Heuristic: read first 8 KB and check for null bytes."""
    try:
        chunk = path.read_bytes()[:8192]
        return b"\x00" in chunk
    except OSError:
        return True


def _python_search(
    pattern: str,
    search_path: Path,
    glob_filter: str | None,
    max_results: int,
) -> list[str]:
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern: {exc}") from exc

    matches: list[str] = []

    if search_path.is_file():
        files: list[Path] = [search_path]
    else:
        if glob_filter:
            files = [
                p
                for p in search_path.rglob(glob_filter)
                if p.is_file() and not _is_ignored(p, search_path)
            ]
        else:
            files = [
                p
                for p in search_path.rglob("*")
                if p.is_file() and not _is_ignored(p, search_path)
            ]

    for file_path in files:
        if _is_binary(file_path):
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                matches.append(f"{file_path}:{lineno}: {line.rstrip()}")
                if len(matches) >= max_results:
                    return matches

    return matches


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------

class GrepTool(BaseTool):
    """Searches file content for a regex pattern."""

    @property
    def definition(self) -> ToolDef:
        return _DEFINITION

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        pattern: str = args.get("pattern", "")
        if not pattern:
            return self._error("pattern is required.")

        raw_path: str | None = args.get("path")
        if raw_path:
            search_path = Path(raw_path)
            if not search_path.is_absolute():
                search_path = ctx.cwd / search_path
        else:
            search_path = ctx.cwd

        if not search_path.exists():
            return self._error(f"Search path does not exist: {search_path}")

        # glob and include are aliases; glob takes precedence.
        glob_filter: str | None = args.get("glob") or args.get("include")

        raw_max = args.get("max_results", _DEFAULT_MAX_RESULTS)
        try:
            max_results = int(raw_max)
        except (TypeError, ValueError):
            max_results = _DEFAULT_MAX_RESULTS

        # Try ripgrep first.
        try:
            rg_results = await _rg_search(pattern, search_path, glob_filter, max_results)
        except Exception:  # noqa: BLE001
            rg_results = None

        if rg_results is not None:
            matches = rg_results
        else:
            try:
                matches = _python_search(pattern, search_path, glob_filter, max_results)
            except ValueError as exc:
                return self._error(str(exc))

        if not matches:
            return self._ok(f"No matches found for pattern '{pattern}' in {search_path}")

        result = "\n".join(matches)
        if len(matches) >= max_results:
            result += f"\n[Results limited to {max_results} matches]"

        return self._ok(result)
