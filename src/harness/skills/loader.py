"""SKILL.md parser with YAML frontmatter support."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SkillDef:
    """Parsed skill definition from a SKILL.md file."""

    name: str
    description: str
    prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    user_invocable: bool = True


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_skill_md(path: Path) -> SkillDef:
    """Parse a SKILL.md file into a SkillDef.

    Format:
        ---
        name: commit
        description: Create a git commit
        allowed_tools: [Bash, Read, Glob, Grep]
        args: [message]
        user_invocable: true
        ---
        <prompt content>

    The YAML frontmatter is parsed minimally (no PyYAML dependency).
    """
    content = path.read_text(encoding="utf-8")

    # Extract frontmatter
    match = _FRONTMATTER_RE.match(content)
    if not match:
        # No frontmatter — use directory name as skill name, entire content as prompt
        name = path.parent.name if path.parent.name != "." else path.stem
        return SkillDef(name=name, description="", prompt=content.strip())

    frontmatter_text = match.group(1)
    prompt = content[match.end():].strip()

    # Parse simple YAML (key: value pairs, lists)
    meta = _parse_simple_yaml(frontmatter_text)

    name = str(meta.get("name", path.parent.name))
    description = str(meta.get("description", ""))
    allowed_tools = _as_list(meta.get("allowed_tools", []))
    args = _as_list(meta.get("args", []))
    user_invocable = _as_bool(meta.get("user_invocable", True))

    return SkillDef(
        name=name,
        description=description,
        prompt=prompt,
        allowed_tools=allowed_tools,
        args=args,
        user_invocable=user_invocable,
    )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a minimal subset of YAML (single-level key-value pairs).

    Handles:
        key: value
        key: [item1, item2]
        key: true/false
    """
    result: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # List value: [item1, item2]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            items = [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
            result[key] = items
        # Boolean
        elif value.lower() in ("true", "yes"):
            result[key] = True
        elif value.lower() in ("false", "no"):
            result[key] = False
        # Numeric
        elif value.isdigit():
            result[key] = int(value)
        # String (strip quotes if present)
        else:
            result[key] = value.strip("\"'")

    return result


def _as_list(val: Any) -> list[str]:
    """Coerce a value to a list of strings."""
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [v.strip() for v in val.split(",") if v.strip()]
    return []


def _as_bool(val: Any) -> bool:
    """Coerce a value to bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "yes", "1")
    return bool(val)
