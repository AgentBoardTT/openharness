"""RetentionPolicy — age/size-based cleanup of audit logs."""

from __future__ import annotations

import gzip
import shutil
import time
from pathlib import Path


class RetentionPolicy:
    """Manages retention of audit log files based on age and size limits."""

    def __init__(
        self,
        audit_dir: Path | None = None,
        *,
        max_age_days: int = 90,
        max_size_mb: int = 0,
        archive: bool = False,
    ) -> None:
        self._audit_dir = audit_dir or (Path.home() / ".harness" / "audit")
        self._max_age_days = max_age_days
        self._max_size_mb = max_size_mb
        self._archive = archive

    def enforce_retention(self) -> int:
        """Delete or archive old audit files. Returns number of files removed."""
        if not self._audit_dir.exists():
            return 0

        # Snapshot file metadata once to avoid repeated/stale stat() calls.
        file_stats: dict[Path, tuple[float, int]] = {}
        for f in self._audit_dir.glob("audit-*.jsonl"):
            st = f.stat()
            file_stats[f] = (st.st_mtime, st.st_size)

        removed = 0
        now = time.time()
        cutoff = now - (self._max_age_days * 86400)

        # Age-based cleanup
        if self._max_age_days > 0:
            for f, (mtime, _size) in sorted(file_stats.items(), key=lambda x: x[1][0]):
                if mtime < cutoff:
                    self._remove_or_archive(f)
                    del file_stats[f]
                    removed += 1

        # Size-based cleanup (remove oldest first until under limit)
        if self._max_size_mb > 0:
            max_bytes = self._max_size_mb * 1024 * 1024
            ordered = sorted(file_stats.items(), key=lambda x: x[1][0])
            total_size = sum(size for (_mtime, size) in file_stats.values())
            for f, (_mtime, size) in ordered:
                if total_size <= max_bytes:
                    break
                total_size -= size
                self._remove_or_archive(f)
                removed += 1

        return removed

    def _remove_or_archive(self, path: Path) -> None:
        """Archive or delete a single file."""
        if self._archive:
            self._gzip_file(path)
        else:
            path.unlink()

    @staticmethod
    def _gzip_file(path: Path) -> Path:
        """Compress a file with gzip and remove the original."""
        gz_path = path.with_suffix(path.suffix + ".gz")
        with open(path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        path.unlink()
        return gz_path
