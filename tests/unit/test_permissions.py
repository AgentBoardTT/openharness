"""Tests for the permission system."""

from harness.permissions.manager import (
    EDIT_TOOLS,
    PLAN_DENIED_TOOLS,
    READ_ONLY_TOOLS,
    PermissionManager,
)
from harness.permissions.rules import (
    PermissionConfig,
    PermissionDecision,
    PermissionRule,
    _matches_rule,
)
from harness.types.config import PermissionMode

# --- Rule matching ---


class TestMatchesRule:
    def test_exact_tool_match(self):
        rule = PermissionRule(tool="Bash", decision=PermissionDecision.DENY)
        assert _matches_rule(rule, "Bash", {}) is True
        assert _matches_rule(rule, "Read", {}) is False

    def test_glob_pattern(self):
        rule = PermissionRule(tool="mcp__*", decision=PermissionDecision.DENY)
        assert _matches_rule(rule, "mcp__postgres__query", {}) is True
        assert _matches_rule(rule, "Read", {}) is False

    def test_wildcard_matches_all(self):
        rule = PermissionRule(tool="*", decision=PermissionDecision.ALLOW)
        assert _matches_rule(rule, "Read", {}) is True
        assert _matches_rule(rule, "Bash", {}) is True
        assert _matches_rule(rule, "mcp__x__y", {}) is True

    def test_args_pattern_match(self):
        rule = PermissionRule(
            tool="Bash",
            decision=PermissionDecision.DENY,
            args_pattern={"command": "rm *"},
        )
        assert _matches_rule(rule, "Bash", {"command": "rm -rf /"}) is True
        assert _matches_rule(rule, "Bash", {"command": "ls"}) is False

    def test_args_pattern_missing_key(self):
        rule = PermissionRule(
            tool="Read",
            decision=PermissionDecision.ALLOW,
            args_pattern={"file_path": "*.py"},
        )
        assert _matches_rule(rule, "Read", {}) is False
        assert _matches_rule(rule, "Read", {"file_path": "main.py"}) is True


# --- PermissionConfig ---


class TestPermissionConfig:
    def test_add_deny(self):
        config = PermissionConfig()
        config.add_deny("Bash")
        assert len(config.deny_rules) == 1
        assert config.deny_rules[0].tool == "Bash"
        assert config.deny_rules[0].decision == PermissionDecision.DENY

    def test_add_allow(self):
        config = PermissionConfig()
        config.add_allow("Read", args_pattern={"file_path": "*.py"})
        assert len(config.allow_rules) == 1
        assert config.allow_rules[0].args_pattern == {"file_path": "*.py"}


# --- PermissionManager modes ---


class TestDefaultMode:
    def test_read_only_tools_allowed(self):
        mgr = PermissionManager(mode=PermissionMode.DEFAULT)
        for tool in READ_ONLY_TOOLS:
            assert mgr.check(tool) == PermissionDecision.ALLOW

    def test_write_tools_ask(self):
        mgr = PermissionManager(mode=PermissionMode.DEFAULT)
        assert mgr.check("Write") == PermissionDecision.ASK
        assert mgr.check("Edit") == PermissionDecision.ASK
        assert mgr.check("Bash") == PermissionDecision.ASK


class TestAcceptEditsMode:
    def test_edit_tools_allowed(self):
        mgr = PermissionManager(mode=PermissionMode.ACCEPT_EDITS)
        for tool in EDIT_TOOLS:
            assert mgr.check(tool) == PermissionDecision.ALLOW

    def test_bash_asks(self):
        mgr = PermissionManager(mode=PermissionMode.ACCEPT_EDITS)
        assert mgr.check("Bash") == PermissionDecision.ASK

    def test_mcp_tools_ask(self):
        mgr = PermissionManager(mode=PermissionMode.ACCEPT_EDITS)
        assert mgr.check("mcp__postgres__query") == PermissionDecision.ASK


class TestPlanMode:
    def test_denied_tools(self):
        mgr = PermissionManager(mode=PermissionMode.PLAN)
        for tool in PLAN_DENIED_TOOLS:
            assert mgr.check(tool) == PermissionDecision.DENY

    def test_read_tools_allowed(self):
        mgr = PermissionManager(mode=PermissionMode.PLAN)
        assert mgr.check("Read") == PermissionDecision.ALLOW
        assert mgr.check("Glob") == PermissionDecision.ALLOW
        assert mgr.check("Grep") == PermissionDecision.ALLOW

    def test_mcp_tools_denied(self):
        mgr = PermissionManager(mode=PermissionMode.PLAN)
        assert mgr.check("mcp__postgres__query") == PermissionDecision.DENY


class TestBypassMode:
    def test_everything_allowed(self):
        mgr = PermissionManager(mode=PermissionMode.BYPASS)
        assert mgr.check("Read") == PermissionDecision.ALLOW
        assert mgr.check("Write") == PermissionDecision.ALLOW
        assert mgr.check("Bash") == PermissionDecision.ALLOW
        assert mgr.check("mcp__x__y") == PermissionDecision.ALLOW


# --- Explicit rules override mode ---


class TestExplicitRules:
    def test_deny_overrides_mode(self):
        config = PermissionConfig()
        config.add_deny("Read")
        mgr = PermissionManager(mode=PermissionMode.BYPASS, config=config)
        # Even in BYPASS mode, explicit deny wins
        assert mgr.check("Read") == PermissionDecision.DENY

    def test_allow_overrides_mode(self):
        config = PermissionConfig()
        config.add_allow("Bash")
        mgr = PermissionManager(mode=PermissionMode.DEFAULT, config=config)
        # In DEFAULT mode, Bash would be ASK, but explicit allow wins
        assert mgr.check("Bash") == PermissionDecision.ALLOW

    def test_deny_beats_allow(self):
        config = PermissionConfig()
        config.add_deny("Bash")
        config.add_allow("Bash")
        mgr = PermissionManager(mode=PermissionMode.BYPASS, config=config)
        # Deny rules take priority over allow rules
        assert mgr.check("Bash") == PermissionDecision.DENY

    def test_args_pattern_deny(self):
        config = PermissionConfig()
        config.add_deny("Bash", args_pattern={"command": "rm *"})
        mgr = PermissionManager(mode=PermissionMode.BYPASS, config=config)
        assert mgr.check("Bash", {"command": "rm -rf /"}) == PermissionDecision.DENY
        assert mgr.check("Bash", {"command": "ls"}) == PermissionDecision.ALLOW
