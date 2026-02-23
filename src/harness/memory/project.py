"""HARNESS.md loading — project-level instructions."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default filenames to search for project instructions
_PROJECT_FILENAMES = ("HARNESS.md", ".harness.md", "harness.md")

# Maximum size to read (prevent loading huge files into context)
_MAX_SIZE_BYTES = 50_000


def load_project_instructions(cwd: str | Path) -> str | None:
    """Load project instructions from HARNESS.md.

    Searches for HARNESS.md in the project directory and parent directories
    up to the filesystem root.

    Returns the content or None if not found.
    """
    path = Path(cwd).resolve()

    # Walk up the directory tree looking for HARNESS.md
    for directory in _walk_up(path):
        for filename in _PROJECT_FILENAMES:
            candidate = directory / filename
            if candidate.is_file():
                try:
                    size = candidate.stat().st_size
                    if size > _MAX_SIZE_BYTES:
                        logger.warning(
                            "HARNESS.md at %s is too large (%d bytes, max %d)",
                            candidate, size, _MAX_SIZE_BYTES,
                        )
                        return None
                    content = candidate.read_text(encoding="utf-8").strip()
                    if content:
                        logger.info("Loaded project instructions from %s", candidate)
                        return content
                except Exception as exc:
                    logger.warning("Failed to read %s: %s", candidate, exc)

    return None


def _walk_up(path: Path) -> list[Path]:
    """Walk up the directory tree from path to root."""
    directories = []
    current = path if path.is_dir() else path.parent
    while True:
        directories.append(current)
        parent = current.parent
        if parent == current:
            break
        # Stop at git root if found
        if (current / ".git").exists():
            break
        current = parent
    return directories
