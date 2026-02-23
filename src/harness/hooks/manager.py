"""Hook execution engine."""

from __future__ import annotations

import asyncio
import fnmatch
import shlex
from typing import Any

from harness.hooks.events import HookContext
from harness.types.hooks import Hook, HookEvent, HookResult


class HookManager:
    """Registers and executes hooks for lifecycle events."""

    def __init__(self, hooks: list[Hook] | None = None) -> None:
        self._hooks: list[Hook] = list(hooks) if hooks else []

    def register(self, hook: Hook) -> None:
        """Add a hook."""
        self._hooks.append(hook)

    def _matches(self, hook: Hook, ctx: HookContext) -> bool:
        """Check if a hook matches the given context."""
        # Match event
        hook_event = hook.event if isinstance(hook.event, str) else hook.event.value
        ctx_event = ctx.event.value if isinstance(ctx.event, HookEvent) else ctx.event
        if hook_event != ctx_event:
            return False

        # For tool events, check the matcher pattern
        if hook.matcher and ctx.tool_name:
            if not fnmatch.fnmatch(ctx.tool_name, hook.matcher):
                return False
        elif hook.matcher and not ctx.tool_name:
            return False

        return True

    def _expand_command(self, command: str, ctx: HookContext) -> str:
        """Expand template variables in the hook command."""
        replacements: dict[str, str] = {
            "{tool_name}": ctx.tool_name or "",
            "{session_id}": ctx.session_id,
            "{cwd}": ctx.cwd,
            "{event}": ctx.event.value if isinstance(ctx.event, HookEvent) else str(ctx.event),
        }

        # Extract common args
        if ctx.tool_args:
            replacements["{file_path}"] = str(ctx.tool_args.get("file_path", ""))
            replacements["{command}"] = str(ctx.tool_args.get("command", ""))
            replacements["{pattern}"] = str(ctx.tool_args.get("pattern", ""))

        if ctx.result is not None:
            replacements["{result}"] = ctx.result[:1000]  # Truncate large results

        result = command
        for key, value in replacements.items():
            result = result.replace(key, shlex.quote(value) if value else "''")
        return result

    async def fire(self, ctx: HookContext) -> list[HookResult]:
        """Fire all hooks that match the given context.

        Returns results from all matching hooks.
        """
        results: list[HookResult] = []
        for hook in self._hooks:
            if self._matches(hook, ctx):
                result = await self._execute(hook, ctx)
                results.append(result)
        return results

    async def _execute(self, hook: Hook, ctx: HookContext) -> HookResult:
        """Execute a single hook command."""
        command = self._expand_command(hook.command, ctx)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=ctx.cwd or None,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=hook.timeout,
            )

            output = stdout.decode("utf-8", errors="replace").strip()
            error = stderr.decode("utf-8", errors="replace").strip() or None
            success = proc.returncode == 0

            # Try to parse JSON output for data field
            data: dict[str, Any] = {}
            if output.startswith("{"):
                import json

                try:
                    data = json.loads(output)
                except json.JSONDecodeError:
                    pass

            return HookResult(
                success=success,
                output=output,
                error=error if not success else None,
                data=data,
            )
        except TimeoutError:
            return HookResult(
                success=False,
                error=f"Hook timed out after {hook.timeout}s: {command}",
            )
        except Exception as e:
            return HookResult(
                success=False,
                error=f"Hook failed: {type(e).__name__}: {e}",
            )
