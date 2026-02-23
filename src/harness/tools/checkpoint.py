"""Checkpoint tool — file backup and restore."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

CHECKPOINT_DIR = ".harness/checkpoints"


class CheckpointTool(BaseTool):
    """Create snapshots of files before modification.

    Supports save, restore, and list operations.
    """

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="Checkpoint",
            description=(
                "Save, restore, or list file checkpoints. Use before making risky "
                "changes to create a backup you can restore later."
            ),
            parameters=(
                ToolParam(
                    name="action",
                    type="string",
                    description="The action to perform.",
                    required=True,
                    enum=("save", "restore", "list"),
                ),
                ToolParam(
                    name="file_path",
                    type="string",
                    description="The file to checkpoint (required for save/restore).",
                    required=False,
                ),
            ),
        )

    def _checkpoint_dir(self, ctx: ToolContext) -> Path:
        """Get the checkpoint directory for the current session."""
        return ctx.cwd / CHECKPOINT_DIR / ctx.session_id

    def _checkpoint_path(self, ctx: ToolContext, file_path: str) -> Path:
        """Get the checkpoint path for a specific file."""
        # Use the relative path as the checkpoint filename (flattened with --)
        try:
            rel = Path(file_path).resolve().relative_to(ctx.cwd.resolve())
        except ValueError:
            rel = Path(file_path).resolve()
        safe_name = str(rel).replace("/", "--").replace("\\", "--")
        return self._checkpoint_dir(ctx) / safe_name

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        action = args.get("action", "")
        if action not in ("save", "restore", "list"):
            return self._error("'action' must be 'save', 'restore', or 'list'.")

        if action == "list":
            return self._list_checkpoints(ctx)

        file_path = args.get("file_path", "")
        if not file_path:
            return self._error("'file_path' is required for save/restore.")

        # Resolve path
        resolved = Path(file_path)
        if not resolved.is_absolute():
            resolved = ctx.cwd / file_path

        if action == "save":
            return self._save(ctx, resolved, file_path)
        else:
            return self._restore(ctx, resolved, file_path)

    def _save(self, ctx: ToolContext, resolved: Path, file_path: str) -> ToolResultData:
        """Save a checkpoint of the file."""
        if not resolved.is_file():
            return self._error(f"File not found: {file_path}")

        cp_path = self._checkpoint_path(ctx, file_path)
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(resolved), str(cp_path))
        return self._ok(f"Checkpoint saved: {file_path}")

    def _restore(self, ctx: ToolContext, resolved: Path, file_path: str) -> ToolResultData:
        """Restore a file from checkpoint."""
        cp_path = self._checkpoint_path(ctx, file_path)
        if not cp_path.is_file():
            return self._error(f"No checkpoint found for: {file_path}")

        resolved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(cp_path), str(resolved))
        return self._ok(f"Restored from checkpoint: {file_path}")

    def _list_checkpoints(self, ctx: ToolContext) -> ToolResultData:
        """List all checkpointed files."""
        cp_dir = self._checkpoint_dir(ctx)
        if not cp_dir.is_dir():
            return self._ok("No checkpoints found.")

        files = sorted(f.name.replace("--", "/") for f in cp_dir.iterdir() if f.is_file())
        if not files:
            return self._ok("No checkpoints found.")

        listing = "\n".join(f"  - {f}" for f in files)
        return self._ok(f"Checkpointed files:\n{listing}")
