"""Auto-memory — cross-session persistent memory."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default memory directory
_MEMORY_DIR_NAME = ".harness/memory"


class AutoMemory:
    """Manages auto-memory for cross-session persistence.

    Memory is stored as JSON files in ~/.harness/memory/ (user-level)
    and .harness/memory/ (project-level).
    """

    def __init__(self, cwd: str | Path | None = None) -> None:
        self._cwd = Path(cwd).resolve() if cwd else Path.cwd()
        self._user_dir = Path.home() / _MEMORY_DIR_NAME
        self._project_dir = self._cwd / _MEMORY_DIR_NAME

    def _ensure_dir(self, path: Path) -> None:
        """Create directory if it doesn't exist."""
        path.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        key: str,
        value: Any,
        *,
        scope: str = "project",
    ) -> None:
        """Save a memory entry.

        Args:
            key: Memory key (used as filename).
            value: Value to store (must be JSON-serializable).
            scope: "user" for global, "project" for project-local.
        """
        directory = self._user_dir if scope == "user" else self._project_dir
        self._ensure_dir(directory)

        entry = {
            "key": key,
            "value": value,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        path = directory / f"{key}.json"
        path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
        logger.debug("Saved memory '%s' to %s", key, path)

    def load(self, key: str) -> Any | None:
        """Load a memory entry. Project-level takes precedence over user-level."""
        # Check project-level first
        path = self._project_dir / f"{key}.json"
        if path.is_file():
            return self._read_entry(path)

        # Fall back to user-level
        path = self._user_dir / f"{key}.json"
        if path.is_file():
            return self._read_entry(path)

        return None

    def _read_entry(self, path: Path) -> Any | None:
        """Read and parse a memory entry file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("value")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read memory from %s: %s", path, exc)
            return None

    def delete(self, key: str, *, scope: str = "project") -> bool:
        """Delete a memory entry. Returns True if deleted."""
        directory = self._user_dir if scope == "user" else self._project_dir
        path = directory / f"{key}.json"
        if path.is_file():
            path.unlink()
            logger.debug("Deleted memory '%s' from %s", key, path)
            return True
        return False

    def list_keys(self, *, scope: str | None = None) -> list[str]:
        """List all memory keys.

        If scope is None, combines both user and project keys.
        """
        keys: set[str] = set()

        if scope in (None, "project") and self._project_dir.is_dir():
            for f in self._project_dir.glob("*.json"):
                keys.add(f.stem)

        if scope in (None, "user") and self._user_dir.is_dir():
            for f in self._user_dir.glob("*.json"):
                keys.add(f.stem)

        return sorted(keys)

    def get_context_summary(self) -> str:
        """Build a summary of stored memories for the system prompt."""
        keys = self.list_keys()
        if not keys:
            return ""

        lines = ["Stored memories:"]
        for key in keys[:20]:  # Cap at 20
            value = self.load(key)
            if value is not None:
                preview = str(value)
                if len(preview) > 100:
                    preview = preview[:100] + "..."
                lines.append(f"  {key}: {preview}")

        return "\n".join(lines)
