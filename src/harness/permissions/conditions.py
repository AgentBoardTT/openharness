"""Condition evaluators for the policy-as-code engine."""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Maximum allowed length for a regex pattern to mitigate ReDoS.
_MAX_REGEX_LEN = 1024


@dataclass(frozen=True, slots=True)
class Condition:
    """A single condition to evaluate against tool call arguments.

    When ``field`` is ``content_matches``, *pattern* is treated as a regular
    expression.  The regex is compiled eagerly at construction time (via
    :func:`compile_condition`) so that invalid or excessively complex patterns
    are rejected early rather than at evaluation time.
    """

    field: str  # e.g. "command_matches", "path_matches"
    pattern: str
    _compiled_re: re.Pattern[str] | None = field(
        default=None, repr=False, compare=False,
    )


def compile_condition(field_name: str, pattern: str) -> Condition:
    """Create a Condition, eagerly compiling regex patterns.

    Raises ``ValueError`` if the pattern is too long or not valid regex.
    """
    compiled: re.Pattern[str] | None = None
    if field_name == "content_matches":
        if len(pattern) > _MAX_REGEX_LEN:
            raise ValueError(
                f"content_matches pattern exceeds {_MAX_REGEX_LEN} chars"
            )
        compiled = re.compile(pattern)
    return Condition(field=field_name, pattern=pattern, _compiled_re=compiled)


def evaluate_conditions(conditions: list[Condition], args: dict[str, Any]) -> bool:
    """Evaluate all conditions with AND logic. Returns True if all match."""
    for cond in conditions:
        if not _evaluate_single(cond, args):
            return False
    return True


def _evaluate_single(cond: Condition, args: dict[str, Any]) -> bool:
    """Evaluate a single condition against the args."""
    evaluator = _EVALUATORS.get(cond.field)
    if evaluator is None:
        return False
    return evaluator(cond, args)


def _command_matches(cond: Condition, args: dict[str, Any]) -> bool:
    """Match against args["command"] using fnmatch."""
    command = str(args.get("command", ""))
    return fnmatch.fnmatch(command, cond.pattern)


def _path_matches(cond: Condition, args: dict[str, Any]) -> bool:
    """Match against args["file_path"] using fnmatch."""
    path = str(args.get("file_path", ""))
    return fnmatch.fnmatch(path, cond.pattern)


def _not_path_matches(cond: Condition, args: dict[str, Any]) -> bool:
    """Inverse of path_matches - True when path does NOT match."""
    path = str(args.get("file_path", ""))
    return not fnmatch.fnmatch(path, cond.pattern)


def _content_matches(cond: Condition, args: dict[str, Any]) -> bool:
    """Regex match against args["content"].

    Uses the pre-compiled pattern stored on the Condition when available,
    falling back to ``re.search`` with a length guard.
    """
    content = str(args.get("content", ""))
    try:
        if cond._compiled_re is not None:
            return bool(cond._compiled_re.search(content))
        # Fallback: compile on-the-fly with safety guard
        if len(cond.pattern) > _MAX_REGEX_LEN:
            logger.warning("Skipping oversized content_matches pattern")
            return False
        return bool(re.search(cond.pattern, content))
    except re.error:
        logger.warning("Invalid regex in content_matches: %s", cond.pattern)
        return False


_EVALUATORS: dict[str, Any] = {
    "command_matches": _command_matches,
    "path_matches": _path_matches,
    "not_path_matches": _not_path_matches,
    "content_matches": _content_matches,
}
