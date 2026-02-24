"""Tests for the policy-as-code engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.permissions.conditions import Condition, compile_condition, evaluate_conditions
from harness.permissions.policy import PolicyEngine, PolicyRule, Policy
from harness.permissions.rules import PermissionDecision
from harness.permissions.manager import PermissionManager
from harness.types.config import PermissionMode


# ---------------------------------------------------------------------------
# Condition evaluator tests
# ---------------------------------------------------------------------------


class TestConditions:
    def test_command_matches(self) -> None:
        conds = [Condition(field="command_matches", pattern="git *")]
        assert evaluate_conditions(conds, {"command": "git status"})
        assert not evaluate_conditions(conds, {"command": "ls -la"})

    def test_path_matches(self) -> None:
        conds = [Condition(field="path_matches", pattern="src/**")]
        assert evaluate_conditions(conds, {"file_path": "src/main.py"})
        assert not evaluate_conditions(conds, {"file_path": "tests/test.py"})

    def test_not_path_matches(self) -> None:
        conds = [Condition(field="not_path_matches", pattern="*.env")]
        assert evaluate_conditions(conds, {"file_path": "src/main.py"})
        assert not evaluate_conditions(conds, {"file_path": "config.env"})

    def test_content_matches(self) -> None:
        conds = [Condition(field="content_matches", pattern=r"import\s+os")]
        assert evaluate_conditions(conds, {"content": "import os\nimport sys"})
        assert not evaluate_conditions(conds, {"content": "import json"})

    def test_multiple_conditions_and_logic(self) -> None:
        conds = [
            Condition(field="path_matches", pattern="src/**"),
            Condition(field="not_path_matches", pattern="*.env"),
        ]
        assert evaluate_conditions(conds, {"file_path": "src/main.py"})
        assert not evaluate_conditions(conds, {"file_path": "src/.env"})

    def test_empty_conditions_return_true(self) -> None:
        assert evaluate_conditions([], {})

    def test_unknown_field_returns_false(self) -> None:
        conds = [Condition(field="nonexistent", pattern="*")]
        assert not evaluate_conditions(conds, {})

    def test_compile_condition_valid_regex(self) -> None:
        cond = compile_condition("content_matches", r"\d+")
        assert cond._compiled_re is not None
        assert evaluate_conditions([cond], {"content": "abc 123"})

    def test_compile_condition_invalid_regex(self) -> None:
        with pytest.raises(Exception):
            compile_condition("content_matches", r"[invalid")

    def test_compile_condition_too_long(self) -> None:
        with pytest.raises(ValueError, match="exceeds"):
            compile_condition("content_matches", "a" * 2000)

    def test_compile_condition_non_regex_field(self) -> None:
        """Non-content_matches fields should not compile regex."""
        cond = compile_condition("command_matches", "git *")
        assert cond._compiled_re is None


# ---------------------------------------------------------------------------
# PolicyEngine tests
# ---------------------------------------------------------------------------


class TestPolicyEngine:
    def test_empty_engine_returns_none(self) -> None:
        engine = PolicyEngine()
        assert engine.check("Bash", {"command": "ls"}) is None

    def test_load_yaml_file(self, tmp_path: Path) -> None:
        policy_file = tmp_path / "policy.yml"
        policy_file.write_text("""
version: 1
rules:
  - tool: Bash
    when:
      command_matches: "git *"
    decision: allow
    description: "Allow git commands"
  - tool: Write
    when:
      path_matches: "*.env"
    decision: deny
    description: "Block writing to .env files"
""")
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("pyyaml not installed")

        engine = PolicyEngine()
        engine.load_file(policy_file)

        assert len(engine.policies) == 1
        assert engine.check("Bash", {"command": "git status"}) == PermissionDecision.ALLOW
        assert engine.check("Write", {"file_path": "config.env"}) == PermissionDecision.DENY
        assert engine.check("Bash", {"command": "rm -rf /"}) is None  # no match

    def test_load_toml_file(self, tmp_path: Path) -> None:
        policy_file = tmp_path / "policy.toml"
        policy_file.write_text("""
version = 1

[[rules]]
tool = "Read"
decision = "allow"
description = "Allow all reads"
""")
        engine = PolicyEngine()
        engine.load_file(policy_file)

        assert len(engine.policies) == 1
        assert engine.check("Read", {}) == PermissionDecision.ALLOW

    def test_inheritance_chain(self, tmp_path: Path) -> None:
        parent = tmp_path / "parent.yml"
        child = tmp_path / "child.yml"

        parent.write_text("""
version: 1
rules:
  - tool: Read
    decision: allow
""")
        child.write_text(f"""
version: 1
inherit_from: {parent}
rules:
  - tool: Bash
    decision: deny
""")
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("pyyaml not installed")

        engine = PolicyEngine()
        engine.load_file(child)

        # Both policies should be loaded
        assert len(engine.policies) == 2
        assert engine.check("Bash", {}) == PermissionDecision.DENY
        assert engine.check("Read", {}) == PermissionDecision.ALLOW

    def test_circular_inheritance_detection(self, tmp_path: Path) -> None:
        a = tmp_path / "a.yml"
        b = tmp_path / "b.yml"

        a.write_text(f"""
version: 1
inherit_from: {b}
rules:
  - tool: Bash
    decision: allow
""")
        b.write_text(f"""
version: 1
inherit_from: {a}
rules:
  - tool: Read
    decision: allow
""")
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("pyyaml not installed")

        engine = PolicyEngine()
        engine.load_file(a)
        # Should not infinite loop — circular detection stops it
        assert len(engine.policies) == 2

    def test_simulation_mode(self, tmp_path: Path) -> None:
        policy_file = tmp_path / "policy.yml"
        policy_file.write_text("""
version: 1
rules:
  - tool: Bash
    decision: deny
""")
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("pyyaml not installed")

        engine = PolicyEngine(simulation_mode=True)
        engine.load_file(policy_file)

        # In simulation mode, check returns None but logs the match
        result = engine.check("Bash", {})
        assert result is None
        assert len(engine.audit_log) == 1
        assert engine.audit_log[0]["decision"] == "deny"
        assert engine.audit_log[0]["simulation"] is True

    def test_simulate_method(self) -> None:
        engine = PolicyEngine()
        engine._policies.append(Policy(
            version=1,
            rules=(
                PolicyRule(
                    tool="Bash",
                    decision=PermissionDecision.ALLOW,
                    conditions=(Condition(field="command_matches", pattern="git *"),),
                    description="Allow git",
                ),
            ),
        ))

        matches = engine.simulate("Bash", {"command": "git status"})
        assert len(matches) == 1
        assert matches[0]["decision"] == "allow"

    def test_missing_file_ignored(self, tmp_path: Path) -> None:
        engine = PolicyEngine()
        engine.load_file(tmp_path / "nonexistent.yml")
        assert len(engine.policies) == 0


# ---------------------------------------------------------------------------
# Integration with PermissionManager
# ---------------------------------------------------------------------------


class TestPolicyManagerIntegration:
    def test_policy_engine_overrides_mode_default(self) -> None:
        engine = PolicyEngine()
        engine._policies.append(Policy(
            version=1,
            rules=(
                PolicyRule(tool="Bash", decision=PermissionDecision.ALLOW),
            ),
        ))

        # In DEFAULT mode, Bash would normally be ASK
        manager = PermissionManager(
            mode=PermissionMode.DEFAULT,
            policy_engine=engine,
        )
        assert manager.check("Bash", {}) == PermissionDecision.ALLOW

    def test_explicit_rules_take_priority_over_policy(self) -> None:
        from harness.permissions.rules import PermissionConfig

        engine = PolicyEngine()
        engine._policies.append(Policy(
            version=1,
            rules=(
                PolicyRule(tool="Bash", decision=PermissionDecision.ALLOW),
            ),
        ))

        config = PermissionConfig()
        config.add_deny("Bash")

        manager = PermissionManager(
            mode=PermissionMode.DEFAULT,
            config=config,
            policy_engine=engine,
        )
        # Explicit deny should win over policy allow
        assert manager.check("Bash", {}) == PermissionDecision.DENY

    def test_no_policy_engine_falls_through(self) -> None:
        manager = PermissionManager(mode=PermissionMode.DEFAULT)
        # Without policy engine, should use mode defaults
        assert manager.check("Bash", {}) == PermissionDecision.ASK
        assert manager.check("Read", {}) == PermissionDecision.ALLOW
