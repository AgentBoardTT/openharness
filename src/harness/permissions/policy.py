"""PolicyEngine — YAML/TOML policy file loading and evaluation."""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.permissions.conditions import Condition, compile_condition, evaluate_conditions
from harness.permissions.rules import PermissionDecision

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """A single policy rule."""

    tool: str
    decision: PermissionDecision
    conditions: tuple[Condition, ...] = ()
    description: str = ""


@dataclass(frozen=True, slots=True)
class Policy:
    """A parsed policy file."""

    version: int = 1
    rules: tuple[PolicyRule, ...] = ()
    defaults: dict[str, str] = field(default_factory=dict)
    inherit_from: str | None = None


class PolicyEngine:
    """Loads and evaluates policy-as-code files.

    Supports YAML and TOML formats with inheritance chains.
    """

    def __init__(self, *, simulation_mode: bool = False) -> None:
        self._policies: list[Policy] = []
        self._simulation_mode = simulation_mode
        self._audit_log: list[dict[str, Any]] = []
        self._loaded_paths: set[str] = set()

    @property
    def policies(self) -> list[Policy]:
        return list(self._policies)

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def load_file(self, path: str | Path) -> None:
        """Load a policy file (YAML or TOML). Resolves inheritance."""
        path = Path(path).expanduser().resolve()
        path_str = str(path)

        if path_str in self._loaded_paths:
            return  # Circular detection
        self._loaded_paths.add(path_str)

        if not path.exists():
            return

        raw = self._parse_file(path)
        if raw is None:
            return

        policy = self._build_policy(raw)
        self._policies.append(policy)

        # Resolve inheritance
        if policy.inherit_from:
            parent_path = Path(policy.inherit_from).expanduser().resolve()
            if str(parent_path) not in self._loaded_paths:
                self.load_file(parent_path)

    def load_files(self, paths: list[str | Path]) -> None:
        """Load multiple policy files."""
        for p in paths:
            self.load_file(p)

    def check(self, tool_name: str, args: dict[str, Any] | None = None) -> PermissionDecision | None:
        """Evaluate policies against a tool call.

        Returns PermissionDecision if a rule matches, or None to fall through
        to mode-based defaults.
        """
        args = args or {}

        for policy in self._policies:
            for rule in policy.rules:
                if not fnmatch.fnmatch(tool_name, rule.tool):
                    continue
                if rule.conditions and not evaluate_conditions(list(rule.conditions), args):
                    continue

                # Rule matches
                entry = {
                    "tool": tool_name,
                    "rule_tool": rule.tool,
                    "decision": rule.decision.value,
                    "description": rule.description,
                    "simulation": self._simulation_mode,
                }
                self._audit_log.append(entry)

                if not self._simulation_mode:
                    return rule.decision
                # In simulation mode, log but don't enforce
                return None

        return None  # No matching rule — fall through

    def simulate(
        self, tool_name: str, args: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a what-if analysis. Returns list of matching rules."""
        args = args or {}
        matches: list[dict[str, Any]] = []

        for policy in self._policies:
            for rule in policy.rules:
                if not fnmatch.fnmatch(tool_name, rule.tool):
                    continue
                if rule.conditions and not evaluate_conditions(list(rule.conditions), args):
                    continue
                matches.append({
                    "tool": rule.tool,
                    "decision": rule.decision.value,
                    "conditions": [(c.field, c.pattern) for c in rule.conditions],
                    "description": rule.description,
                })

        return matches

    @staticmethod
    def _parse_file(path: Path) -> dict[str, Any] | None:
        """Parse a YAML or TOML file."""
        suffix = path.suffix.lower()
        try:
            text = path.read_text()
        except OSError as exc:
            logger.warning("Cannot read policy file %s: %s", path, exc)
            return None

        if suffix in (".yml", ".yaml"):
            try:
                import yaml
                return yaml.safe_load(text)
            except ImportError:
                logger.warning("pyyaml not installed — cannot load %s", path)
                return None
            except Exception as exc:
                logger.warning("Failed to parse YAML policy %s: %s", path, exc)
                return None
        elif suffix == ".toml":
            try:
                import tomllib
                return tomllib.loads(text)
            except Exception as exc:
                logger.warning("Failed to parse TOML policy %s: %s", path, exc)
                return None

        logger.warning("Unsupported policy file extension: %s", path)
        return None

    @staticmethod
    def _build_policy(raw: dict[str, Any]) -> Policy:
        """Build a Policy from parsed file data."""
        rules: list[PolicyRule] = []

        for rule_data in raw.get("rules", []):
            tool = rule_data.get("tool", "*")
            decision_str = rule_data.get("decision", "ask")
            try:
                decision = PermissionDecision(decision_str)
            except ValueError:
                logger.warning("Unknown decision '%s' in policy rule, defaulting to 'ask'", decision_str)
                decision = PermissionDecision.ASK

            conditions: list[Condition] = []
            when = rule_data.get("when", {})
            for cond_field, cond_pattern in when.items():
                try:
                    conditions.append(compile_condition(cond_field, str(cond_pattern)))
                except (ValueError, Exception) as exc:
                    logger.warning("Skipping invalid condition %s=%s: %s", cond_field, cond_pattern, exc)

            rules.append(PolicyRule(
                tool=tool,
                decision=decision,
                conditions=tuple(conditions),
                description=rule_data.get("description", ""),
            ))

        defaults = raw.get("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}

        return Policy(
            version=raw.get("version", 1),
            rules=tuple(rules),
            defaults={str(k): str(v) for k, v in defaults.items()},
            inherit_from=raw.get("inherit_from"),
        )
