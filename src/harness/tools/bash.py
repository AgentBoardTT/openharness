"""Bash tool — executes shell commands asynchronously."""

from __future__ import annotations

import asyncio
from typing import Any

from harness.tools.base import BaseTool
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData

_DEFAULT_TIMEOUT_MS = 120_000
_MAX_TIMEOUT_MS = 600_000
_MAX_OUTPUT_CHARS = 30_000

_DEFINITION = ToolDef(
    name="Bash",
    description=(
        "Execute a shell command and return its combined stdout + stderr output. "
        "The command runs in the session working directory. "
        "Output is truncated to 30 000 characters. "
        "Timeout is in milliseconds (default 120 000, max 600 000)."
    ),
    parameters=(
        ToolParam(
            name="command",
            type="string",
            description="The shell command to execute.",
            required=True,
        ),
        ToolParam(
            name="timeout",
            type="integer",
            description=(
                "Timeout in milliseconds before the process is killed. "
                f"Default {_DEFAULT_TIMEOUT_MS}, max {_MAX_TIMEOUT_MS}."
            ),
            required=False,
            default=_DEFAULT_TIMEOUT_MS,
        ),
    ),
)


class BashTool(BaseTool):
    """Executes shell commands and returns their output."""

    @property
    def definition(self) -> ToolDef:
        return _DEFINITION

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResultData:
        command: str = args.get("command", "")
        if not command:
            return self._error("command is required.")

        raw_timeout = args.get("timeout", _DEFAULT_TIMEOUT_MS)
        try:
            timeout_ms = int(raw_timeout)
        except (TypeError, ValueError):
            timeout_ms = _DEFAULT_TIMEOUT_MS

        timeout_ms = max(1, min(timeout_ms, _MAX_TIMEOUT_MS))
        timeout_sec = timeout_ms / 1000.0

        # Delegate to sandbox if configured
        sandbox_executor = ctx.extra.get("sandbox_executor")
        if sandbox_executor is not None:
            return await self._execute_sandboxed(
                command, ctx, sandbox_executor, timeout_sec,
            )

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(ctx.cwd),
            )

            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_sec
                )
            except TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                return self._error(
                    f"Command timed out after {timeout_ms} ms and was killed: {command}"
                )

        except OSError as exc:
            return self._error(f"Failed to start process: {exc}")

        output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""

        if len(output) > _MAX_OUTPUT_CHARS:
            truncated = len(output) - _MAX_OUTPUT_CHARS
            output = output[:_MAX_OUTPUT_CHARS] + f"\n[...{truncated} characters truncated]"

        exit_code = proc.returncode if proc.returncode is not None else 0

        if not output.strip():
            result_text = "Command completed with no output"
        else:
            result_text = output

        if exit_code != 0:
            result_text = result_text.rstrip("\n") + f"\n[Exit code: {exit_code}]"

        return self._ok(result_text) if exit_code == 0 else self._error(result_text)

    async def _execute_sandboxed(
        self,
        command: str,
        ctx: ToolContext,
        sandbox_executor: Any,
        timeout_sec: float,
    ) -> ToolResultData:
        """Execute a command through the sandbox executor."""
        result = await sandbox_executor.execute(
            command, cwd=str(ctx.cwd), timeout_sec=timeout_sec,
        )

        # Check specific failure modes first — they provide better messages
        # than the generic `result.error` string.
        if result.timed_out:
            return self._error(
                f"Command timed out after {timeout_sec}s and was killed: {command}"
            )

        if result.oom_killed:
            return self._error(
                f"Command killed due to memory limit (OOM): {command}"
            )

        if result.error:
            return self._error(result.error)

        output = result.stdout
        if len(output) > _MAX_OUTPUT_CHARS:
            truncated = len(output) - _MAX_OUTPUT_CHARS
            output = output[:_MAX_OUTPUT_CHARS] + f"\n[...{truncated} characters truncated]"

        if not output.strip():
            result_text = "Command completed with no output"
        else:
            result_text = output

        if result.exit_code != 0:
            result_text = result_text.rstrip("\n") + f"\n[Exit code: {result.exit_code}]"

        return self._ok(result_text) if result.exit_code == 0 else self._error(result_text)
