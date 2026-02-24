"""Export audit logs in JSON/CSV format for compliance reviews."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path


def export_audit_log(
    session_id: str,
    *,
    fmt: str = "json",
    audit_dir: Path | None = None,
) -> str:
    """Export a single session's audit log.

    Args:
        session_id: The session ID to export.
        fmt: Output format — "json" or "csv".
        audit_dir: Override audit directory.

    Returns:
        Formatted string of audit events.
    """
    audit_dir = audit_dir or (Path.home() / ".harness" / "audit")
    log_path = audit_dir / f"audit-{session_id}.jsonl"

    if not log_path.exists():
        return ""

    events = _read_jsonl(log_path)
    if fmt == "csv":
        return _to_csv(events)
    return json.dumps(events, indent=2)


def export_all_audit_logs(
    *,
    fmt: str = "json",
    audit_dir: Path | None = None,
) -> str:
    """Export all audit logs.

    Returns:
        Formatted string of all audit events across sessions.
    """
    audit_dir = audit_dir or (Path.home() / ".harness" / "audit")
    if not audit_dir.exists():
        return "[]" if fmt == "json" else ""

    all_events: list[dict] = []
    for log_path in sorted(audit_dir.glob("audit-*.jsonl")):
        all_events.extend(_read_jsonl(log_path))

    if fmt == "csv":
        return _to_csv(all_events)
    return json.dumps(all_events, indent=2)


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts."""
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _to_csv(events: list[dict]) -> str:
    """Convert audit events to CSV format."""
    if not events:
        return ""
    output = io.StringIO()
    fields = ["event_id", "timestamp", "event_type", "session_id", "data", "hash"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for event in events:
        row = dict(event)
        if "data" in row and isinstance(row["data"], dict):
            row["data"] = json.dumps(row["data"])
        writer.writerow(row)
    return output.getvalue()
