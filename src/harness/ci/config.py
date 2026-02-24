"""CI configuration loader (.harness/ci.yml)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CIConfig:
    """CI/CD configuration."""

    triggers: list[str] = field(default_factory=lambda: ["pull_request", "issues"])
    provider: str = "anthropic"
    model: str | None = None
    sandbox: str = "process"
    check_name: str = "harness-agent"
    max_turns: int = 50
    permission_mode: str = "bypass"
    review_prompt: str | None = None
    issue_prompt: str | None = None


def load_ci_config(cwd: str | None = None) -> CIConfig:
    """Load CI config from .harness/ci.yml if it exists."""
    search_dirs = []
    if cwd:
        search_dirs.append(Path(cwd))
    search_dirs.append(Path.cwd())

    for d in search_dirs:
        ci_path = d / ".harness" / "ci.yml"
        if ci_path.exists():
            try:
                import yaml

                data = yaml.safe_load(ci_path.read_text())
                if isinstance(data, dict):
                    return _parse_config(data)
            except ImportError:
                pass
            except Exception:
                pass

    return CIConfig()


def _parse_config(data: dict[str, Any]) -> CIConfig:
    """Parse raw YAML data into CIConfig."""
    config = CIConfig()

    if "triggers" in data and isinstance(data["triggers"], list):
        config.triggers = data["triggers"]
    if "provider" in data:
        config.provider = str(data["provider"])
    if "model" in data:
        config.model = str(data["model"])
    if "sandbox" in data:
        config.sandbox = str(data["sandbox"])
    if "check_name" in data:
        config.check_name = str(data["check_name"])
    if "max_turns" in data:
        config.max_turns = int(data["max_turns"])
    if "review_prompt" in data:
        config.review_prompt = str(data["review_prompt"])
    if "issue_prompt" in data:
        config.issue_prompt = str(data["issue_prompt"])

    return config


def generate_ci_template() -> str:
    """Generate a default .harness/ci.yml template."""
    return """\
# Harness CI Configuration
# See: https://github.com/harness-agent/harness

triggers:
  - pull_request
  - issues

provider: anthropic
# model: claude-sonnet-4-6
sandbox: process
check_name: harness-agent
max_turns: 50

# Custom prompts (optional)
# review_prompt: "Review this PR focusing on security and performance"
# issue_prompt: "Analyze this issue and suggest implementation"
"""
