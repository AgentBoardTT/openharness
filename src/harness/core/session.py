"""JSONL append-only session persistence."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.types.providers import ChatMessage
from harness.types.session import SessionInfo


def _sessions_dir() -> Path:
    """Get the sessions directory, creating it if needed."""
    d = Path.home() / ".harness" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_session_id() -> str:
    """Generate a new session ID."""
    return uuid.uuid4().hex[:12]


class Session:
    """Append-only JSONL session with DAG support."""

    def __init__(self, session_id: str | None = None, cwd: str = "."):
        self.session_id = session_id or new_session_id()
        self._path = _sessions_dir() / f"{self.session_id}.jsonl"
        self._messages: list[ChatMessage] = []
        self._metadata: dict[str, Any] = {
            "session_id": self.session_id,
            "cwd": cwd,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._turns = 0
        self._total_tokens = 0
        self._total_cost = 0.0

        if self._path.exists():
            self._load()

    def _load(self) -> None:
        """Load existing session from JSONL."""
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("type") == "metadata":
                    self._metadata.update(entry.get("data", {}))
                elif entry.get("type") == "message":
                    msg_data = entry["data"]
                    self._messages.append(ChatMessage(
                        role=msg_data["role"],
                        content=msg_data["content"],
                        tool_use_id=msg_data.get("tool_use_id"),
                        tool_name=msg_data.get("tool_name"),
                    ))
                elif entry.get("type") == "turn":
                    self._turns = entry.get("turn", self._turns)
                    self._total_tokens += entry.get("tokens", 0)
                    self._total_cost += entry.get("cost", 0.0)

    def _append(self, entry: dict[str, Any]) -> None:
        """Append an entry to the JSONL file."""
        with open(self._path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def save_metadata(self, provider: str, model: str) -> None:
        """Save session metadata."""
        self._metadata["provider"] = provider
        self._metadata["model"] = model
        self._metadata["updated_at"] = datetime.now(UTC).isoformat()
        self._append({"type": "metadata", "data": self._metadata})

    def add_message(self, msg: ChatMessage) -> None:
        """Add a message to the session."""
        self._messages.append(msg)
        data: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_use_id:
            data["tool_use_id"] = msg.tool_use_id
        if msg.tool_name:
            data["tool_name"] = msg.tool_name
        self._append({"type": "message", "data": data})

    def record_turn(self, tokens: int = 0, cost: float = 0.0) -> None:
        """Record a completed turn."""
        self._turns += 1
        self._total_tokens += tokens
        self._total_cost += cost
        self._append({
            "type": "turn",
            "turn": self._turns,
            "tokens": tokens,
            "cost": cost,
            "timestamp": datetime.now(UTC).isoformat(),
        })

    @property
    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    @property
    def turns(self) -> int:
        return self._turns

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def get_info(self) -> SessionInfo:
        """Get session info summary."""
        now_iso = datetime.now(UTC).isoformat()
        created = self._metadata.get("created_at", now_iso)
        updated = self._metadata.get("updated_at", created)
        return SessionInfo(
            session_id=self.session_id,
            created_at=datetime.fromisoformat(created),
            updated_at=datetime.fromisoformat(updated),
            cwd=self._metadata.get("cwd", "."),
            provider=self._metadata.get("provider", "unknown"),
            model=self._metadata.get("model", "unknown"),
            turns=self._turns,
            total_tokens=self._total_tokens,
            total_cost=self._total_cost,
            parent_id=self._metadata.get("parent_id"),
        )

    def set_messages(self, messages: list[ChatMessage]) -> None:
        """Replace messages (used after compaction)."""
        self._messages = list(messages)

    def clear_messages(self) -> None:
        """Clear in-memory messages (for compaction)."""
        self._messages.clear()

    def fork(self, up_to: int | None = None) -> Session:
        """Create a forked session with messages copied up to index *up_to*.

        The forked session gets a new ID and records this session as its
        parent via ``parent_id`` in the metadata.

        Args:
            up_to: Copy messages up to this index (exclusive).
                   If *None*, copies all messages.

        Returns:
            A new :class:`Session` with a fresh ID and the copied history.
        """
        child = Session.__new__(Session)
        child.session_id = new_session_id()
        child._path = _sessions_dir() / f"{child.session_id}.jsonl"
        child._turns = 0
        child._total_tokens = 0
        child._total_cost = 0.0

        # Copy messages
        end = up_to if up_to is not None else len(self._messages)
        child._messages = list(self._messages[:end])

        # Metadata with parent link
        child._metadata = {
            "session_id": child.session_id,
            "parent_id": self.session_id,
            "cwd": self._metadata.get("cwd", "."),
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Persist the forked state
        child._append({"type": "metadata", "data": child._metadata})
        for msg in child._messages:
            data: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_use_id:
                data["tool_use_id"] = msg.tool_use_id
            if msg.tool_name:
                data["tool_name"] = msg.tool_name
            child._append({"type": "message", "data": data})

        return child


def list_sessions() -> list[SessionInfo]:
    """List all saved sessions."""
    sessions_dir = _sessions_dir()
    results = []
    for path in sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        sid = path.stem
        try:
            s = Session(sid)
            results.append(s.get_info())
        except Exception:
            continue
    return results
