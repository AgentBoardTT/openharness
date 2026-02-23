"""Built-in agent definitions."""

from __future__ import annotations

from harness.types.agents import AgentDef

AGENTS: dict[str, AgentDef] = {
    "general": AgentDef(
        name="general",
        description="General-purpose agent with full tool access.",
        tools=("Read", "Write", "Edit", "Bash", "Glob", "Grep"),
        max_turns=50,
    ),
    "explore": AgentDef(
        name="explore",
        description="Fast read-only agent for codebase exploration.",
        tools=("Read", "Glob", "Grep"),
        max_turns=20,
        read_only=True,
    ),
    "plan": AgentDef(
        name="plan",
        description="Read-only agent for designing implementation plans.",
        tools=("Read", "Glob", "Grep"),
        max_turns=30,
        read_only=True,
        system_prompt=(
            "You are a planning agent. Explore the codebase and design an "
            "implementation plan. Do NOT make any changes — only read and analyze."
        ),
    ),
    "review": AgentDef(
        name="review",
        description="Read-only agent for structured code review.",
        tools=("Read", "Glob", "Grep"),
        max_turns=30,
        read_only=True,
        system_prompt=(
            "You are a code review agent. Analyze the code and provide a structured "
            "review with the following sections:\n\n"
            "## Summary\nBrief overview of what the code does.\n\n"
            "## Issues Found\nFor each issue:\n"
            "- **Severity**: critical / warning / info\n"
            "- **Location**: file path and line\n"
            "- **Description**: what the issue is\n"
            "- **Suggestion**: how to fix it\n\n"
            "## Strengths\nWhat the code does well.\n\n"
            "## Suggestions\nGeneral improvements that would make the code better.\n\n"
            "Do NOT make any changes — only read and analyze."
        ),
    ),
}


def get_agent_def(name: str) -> AgentDef:
    """Get an agent definition by name. Raises KeyError if not found."""
    if name not in AGENTS:
        available = ", ".join(sorted(AGENTS))
        raise KeyError(f"Unknown agent type: {name!r}. Available: {available}")
    return AGENTS[name]


def list_agents() -> list[AgentDef]:
    """Return all registered agent definitions."""
    return list(AGENTS.values())
