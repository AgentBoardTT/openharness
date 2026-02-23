"""Session information types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Metadata about a session."""

    session_id: str
    created_at: datetime
    updated_at: datetime
    cwd: str
    provider: str
    model: str
    turns: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    parent_id: str | None = None  # For branching
