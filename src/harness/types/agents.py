"""Agent definition types for sub-agents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentDef:
    """Definition of a sub-agent type."""

    name: str
    description: str
    model: str | None = None  # Override model, None = inherit
    tools: tuple[str, ...] = ()  # Allowed tools, empty = inherit
    system_prompt: str | None = None
    max_turns: int = 50
    read_only: bool = False
