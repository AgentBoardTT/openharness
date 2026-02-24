"""Permission evaluation engine.

Evaluation order: Deny rules > Allow rules > Mode-based default.

Modes:
- DEFAULT: Ask for everything except read-only tools (Read, Glob, Grep)
- ACCEPT_EDITS: Auto-approve file operations, ask for Bash
- PLAN: Read-only — deny all writes/executions
- BYPASS: Auto-approve everything
"""

from __future__ import annotations

from typing import Any

from harness.permissions.rules import (
    PermissionConfig,
    PermissionDecision,
    _matches_rule,
)
from harness.types.config import PermissionMode

# Tools considered read-only (safe to auto-approve in DEFAULT mode)
READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "ToolSearch"})

# Tools considered file-editing (auto-approved in ACCEPT_EDITS mode)
EDIT_TOOLS = frozenset({"Read", "Write", "Edit", "Glob", "Grep", "ToolSearch"})

# Tools always denied in PLAN mode
PLAN_DENIED_TOOLS = frozenset({"Write", "Edit", "Bash"})


class PermissionManager:
    """Evaluates whether a tool call should be allowed, denied, or prompted.

    Evaluation order:
    1. Explicit deny rules (highest priority)
    2. Explicit allow rules
    3. PolicyEngine rules (if configured)
    4. Mode-based defaults
    """

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.DEFAULT,
        config: PermissionConfig | None = None,
        policy_engine: Any | None = None,
    ):
        self._mode = mode
        self._config = config or PermissionConfig()
        self._policy_engine = policy_engine

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    def check(
        self, tool_name: str, args: dict[str, Any] | None = None,
    ) -> PermissionDecision:
        """Check permission for a tool call.

        Returns:
            PermissionDecision.ALLOW — execute without prompting
            PermissionDecision.DENY  — refuse execution
            PermissionDecision.ASK   — prompt user for approval
        """
        check_args = args or {}

        # 1. Explicit deny rules (highest priority)
        for rule in self._config.deny_rules:
            if _matches_rule(rule, tool_name, check_args):
                return PermissionDecision.DENY

        # 2. Explicit allow rules
        for rule in self._config.allow_rules:
            if _matches_rule(rule, tool_name, check_args):
                return PermissionDecision.ALLOW

        # 3. PolicyEngine rules (returns None if no match — fall through)
        if self._policy_engine is not None:
            policy_decision = self._policy_engine.check(tool_name, check_args)
            if policy_decision is not None:
                return policy_decision

        # 4. Mode-based defaults
        return self._mode_default(tool_name)

    def _mode_default(self, tool_name: str) -> PermissionDecision:
        """Apply mode-based default permission."""
        match self._mode:
            case PermissionMode.BYPASS:
                return PermissionDecision.ALLOW

            case PermissionMode.PLAN:
                if tool_name in PLAN_DENIED_TOOLS:
                    return PermissionDecision.DENY
                # MCP tools are denied unless explicitly allowed
                if tool_name.startswith("mcp__"):
                    return PermissionDecision.DENY
                return PermissionDecision.ALLOW

            case PermissionMode.ACCEPT_EDITS:
                if tool_name in EDIT_TOOLS:
                    return PermissionDecision.ALLOW
                # Bash and MCP tools still need approval
                return PermissionDecision.ASK

            case PermissionMode.DEFAULT:
                if tool_name in READ_ONLY_TOOLS:
                    return PermissionDecision.ALLOW
                return PermissionDecision.ASK

            case _:
                return PermissionDecision.ASK
