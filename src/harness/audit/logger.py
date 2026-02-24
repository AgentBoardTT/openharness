"""AuditLogger — append-only JSONL with chain integrity."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any


class AuditEventType(Enum):
    """Types of audit events."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PERMISSION_DECISION = "permission_decision"
    PROVIDER_CALL = "provider_call"
    PII_DETECTED = "pii_detected"


class AuditLogger:
    """Append-only audit logger with tamper-detection via hash chaining.

    Each event includes a SHA-256 hash computed over the event *without* the
    ``hash`` field, then the hash is stored alongside it.  To verify chain
    integrity, use :meth:`verify_chain` which re-derives each hash and checks
    ``prev_hash`` links.

    The log file handle is kept open for the lifetime of the logger to avoid
    repeated open/close overhead.  Call :meth:`close` (or use as a context
    manager) to flush and release the handle.
    """

    def __init__(
        self,
        session_id: str,
        *,
        enabled: bool = True,
        log_tool_args: bool = True,
        audit_dir: Path | None = None,
    ) -> None:
        self._enabled = enabled
        self._session_id = session_id
        self._log_tool_args = log_tool_args
        self._prev_hash = "0" * 64  # genesis hash
        self._event_count = 0
        self._handle = None

        if enabled:
            self._audit_dir = audit_dir or (Path.home() / ".harness" / "audit")
            self._audit_dir.mkdir(parents=True, exist_ok=True)
            self._log_path = self._audit_dir / f"audit-{session_id}.jsonl"
            self._handle = open(self._log_path, "a")  # noqa: SIM115
        else:
            self._audit_dir = None
            self._log_path = None

    # -- Context manager support ------------------------------------------

    def __enter__(self) -> AuditLogger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Flush and close the underlying file handle."""
        if self._handle is not None:
            self._handle.flush()
            self._handle.close()
            self._handle = None

    # -- Properties -------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    @property
    def event_count(self) -> int:
        return self._event_count

    # -- Core write -------------------------------------------------------

    @staticmethod
    def _compute_hash(event: dict[str, Any]) -> str:
        """Compute SHA-256 over the event dict *without* the ``hash`` key."""
        payload = {k: v for k, v in event.items() if k != "hash"}
        event_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(event_json.encode()).hexdigest()

    def _write_event(self, event_type: AuditEventType, data: dict[str, Any]) -> str | None:
        """Write an audit event. Returns the event_id or None if disabled."""
        if not self._enabled or self._handle is None:
            return None

        event_id = uuid.uuid4().hex[:16]
        event = {
            "event_id": event_id,
            "timestamp": time.time(),
            "event_type": event_type.value,
            "session_id": self._session_id,
            "data": data,
            "prev_hash": self._prev_hash,
        }

        event_hash = self._compute_hash(event)
        event["hash"] = event_hash
        self._prev_hash = event_hash
        self._event_count += 1

        self._handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        self._handle.flush()

        return event_id

    # -- Chain verification -----------------------------------------------

    @staticmethod
    def verify_chain(log_path: Path) -> tuple[bool, list[str]]:
        """Verify the integrity of an audit log file.

        Re-derives each event's hash (excluding the ``hash`` field) and checks
        that consecutive ``prev_hash`` links form an unbroken chain starting
        from the genesis hash (``"0" * 64``).

        Returns ``(valid, errors)`` where *valid* is ``True`` when the chain
        is intact and *errors* lists human-readable descriptions of any
        problems found.
        """
        errors: list[str] = []
        expected_prev = "0" * 64

        with open(log_path) as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {lineno}: invalid JSON — {e}")
                    break  # chain is broken

                stored_hash = event.get("hash", "")
                recomputed = AuditLogger._compute_hash(event)
                if recomputed != stored_hash:
                    errors.append(
                        f"Line {lineno}: hash mismatch "
                        f"(stored={stored_hash[:12]}… recomputed={recomputed[:12]}…)"
                    )

                if event.get("prev_hash") != expected_prev:
                    errors.append(
                        f"Line {lineno}: prev_hash mismatch "
                        f"(expected={expected_prev[:12]}… got={event.get('prev_hash', '')[:12]}…)"
                    )

                expected_prev = stored_hash

        return (len(errors) == 0, errors)

    # -- Convenience methods ----------------------------------------------

    def log_session_start(self, provider: str, model: str) -> str | None:
        return self._write_event(AuditEventType.SESSION_START, {
            "provider": provider,
            "model": model,
        })

    def log_session_end(
        self, *, turns: int = 0, total_tokens: int = 0, total_cost: float = 0.0,
    ) -> str | None:
        return self._write_event(AuditEventType.SESSION_END, {
            "turns": turns,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
        })

    def log_tool_call(
        self, tool_name: str, args: dict[str, Any] | None = None,
    ) -> str | None:
        data: dict[str, Any] = {"tool": tool_name}
        if self._log_tool_args and args:
            data["args"] = args
        return self._write_event(AuditEventType.TOOL_CALL, data)

    def log_tool_result(
        self, tool_name: str, *, is_error: bool = False, content_length: int = 0,
    ) -> str | None:
        return self._write_event(AuditEventType.TOOL_RESULT, {
            "tool": tool_name,
            "is_error": is_error,
            "content_length": content_length,
        })

    def log_permission_decision(
        self, tool_name: str, decision: str, mode: str,
    ) -> str | None:
        return self._write_event(AuditEventType.PERMISSION_DECISION, {
            "tool": tool_name,
            "decision": decision,
            "mode": mode,
        })

    def log_provider_call(
        self,
        provider: str,
        model: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
    ) -> str | None:
        return self._write_event(AuditEventType.PROVIDER_CALL, {
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        })

    def log_pii_detected(
        self, pattern_name: str, context: str,
    ) -> str | None:
        return self._write_event(AuditEventType.PII_DETECTED, {
            "pattern": pattern_name,
            "context": context,
        })
