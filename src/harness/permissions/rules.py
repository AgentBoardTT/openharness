"""Permission rules and configuration."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum


class PermissionDecision(Enum):
    """Result of a permission check."""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass(frozen=True, slots=True)
class PermissionRule:
    """A single permission rule.

    Rules are evaluated in priority order: explicit deny > explicit allow > ask.
    """

    tool: str  # Tool name or glob pattern (e.g. "Bash", "mcp__*", "*")
    decision: PermissionDecision
    args_pattern: dict[str, str] | None = None  # Optional arg matchers


@dataclass(slots=True)
class PermissionConfig:
    """Permission configuration combining mode + explicit rules."""

    deny_rules: list[PermissionRule] = field(default_factory=list)
    allow_rules: list[PermissionRule] = field(default_factory=list)

    def add_deny(
        self, tool: str, args_pattern: dict[str, str] | None = None,
    ) -> None:
        self.deny_rules.append(
            PermissionRule(tool=tool, decision=PermissionDecision.DENY, args_pattern=args_pattern),
        )

    def add_allow(
        self, tool: str, args_pattern: dict[str, str] | None = None,
    ) -> None:
        self.allow_rules.append(
            PermissionRule(tool=tool, decision=PermissionDecision.ALLOW, args_pattern=args_pattern),
        )


def _matches_rule(
    rule: PermissionRule,
    tool_name: str,
    args: dict[str, object],
) -> bool:
    """Check if a rule matches a tool call."""
    if not fnmatch.fnmatch(tool_name, rule.tool):
        return False
    if rule.args_pattern:
        for key, pattern in rule.args_pattern.items():
            val = str(args.get(key, ""))
            if not fnmatch.fnmatch(val, pattern):
                return False
    return True
