"""CLI entry point for Harness."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import click

from harness.cli.output import print_message


class HarnessGroup(click.Group):
    """Custom group that treats unknown args as the prompt.

    When the first arg is NOT a subcommand, we separate Click options from
    positional prompt words and let Click parse the options normally.
    """

    # Options that take a value argument
    _VALUE_OPTS = {
        "-p", "--provider", "-m", "--model", "-s", "--session",
        "--max-turns", "--cwd", "--api-key", "--base-url", "--permission",
    }
    # Boolean flags (no value argument)
    _FLAG_OPTS = {
        "-v", "--verbose", "--rich", "--no-rich",
        "--interactive", "--no-interactive",
        "--dangerously-skip-permissions",
    }

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # If first arg matches a subcommand, dispatch normally
        if args and args[0] in self.commands:
            return super().parse_args(ctx, args)

        # Separate Click options from prompt words
        click_args: list[str] = []
        prompt_words: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in self._VALUE_OPTS and i + 1 < len(args):
                click_args.extend([arg, args[i + 1]])
                i += 2
            elif arg in self._FLAG_OPTS:
                click_args.append(arg)
                i += 1
            elif arg.startswith("-") and "=" in arg:
                # e.g. --cwd=/tmp/foo
                click_args.append(arg)
                i += 1
            else:
                prompt_words.append(arg)
                i += 1

        ctx.ensure_object(dict)
        ctx.obj["prompt_args"] = prompt_words
        return super().parse_args(ctx, click_args)


@click.group(cls=HarnessGroup, invoke_without_command=True)
@click.option("--provider", "-p", default="anthropic", help="LLM provider")
@click.option("--model", "-m", default=None, help="Model ID or alias")
@click.option("--session", "-s", default=None, help="Resume session ID")
@click.option("--max-turns", default=100, help="Maximum agent loop turns")
@click.option("--cwd", default=None, help="Working directory")
@click.option("--api-key", default=None, help="Provider API key")
@click.option("--base-url", default=None, help="Provider base URL")
@click.option(
    "--permission",
    type=click.Choice(["default", "accept_edits", "plan", "bypass"]),
    default="default",
    help="Permission mode",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--rich/--no-rich", default=None, help="Rich terminal output (default: auto)")
@click.option("--interactive/--no-interactive", default=False, help="Enable interactive prompts")
@click.option(
    "--dangerously-skip-permissions",
    is_flag=True,
    default=False,
    help="Auto-approve all tool calls (bypass permission checks)",
)
@click.pass_context
def cli(
    ctx: click.Context,
    provider: str,
    model: str | None,
    session: str | None,
    max_turns: int,
    cwd: str | None,
    api_key: str | None,
    base_url: str | None,
    permission: str,
    verbose: bool,
    rich: bool | None,
    interactive: bool,
    dangerously_skip_permissions: bool,
) -> None:
    """Harness -- multi-provider coding agent.

    \b
    Usage:
      harness "Fix the bug in auth.py"
      harness --rich "Read README.md"
      harness                              (interactive REPL)
      harness --dangerously-skip-permissions "list files"
      harness models list
      harness sessions list
      harness config list
    """
    if ctx.invoked_subcommand is not None:
        return

    # --dangerously-skip-permissions overrides permission mode
    if dangerously_skip_permissions:
        permission = "bypass"

    # Load saved defaults for provider/model when user didn't pass explicit flags
    from harness.core.config import load_defaults
    saved = load_defaults()
    source = ctx.get_parameter_source  # click.core.ParameterSource
    if source("provider") == click.core.ParameterSource.DEFAULT and "provider" in saved:
        provider = saved["provider"]
    if source("model") == click.core.ParameterSource.DEFAULT and "model" in saved:
        model = saved["model"]

    ctx.ensure_object(dict)
    prompt_args = ctx.obj.get("prompt_args", [])

    # Determine rich mode: explicit flag > TTY auto-detection
    use_rich = rich if rich is not None else sys.stderr.isatty()

    if not prompt_args:
        if not sys.stdin.isatty():
            # Piped input — one-shot mode
            prompt_text = sys.stdin.read().strip()
            if not prompt_text:
                click.echo("Error: empty prompt", err=True)
                sys.exit(1)
            approval_cb = _create_approval_callback(permission, use_rich, is_tty=False)
            asyncio.run(_run_agent(
                prompt_text,
                provider=provider,
                model=model,
                session_id=session,
                max_turns=max_turns,
                cwd=cwd,
                api_key=api_key,
                base_url=base_url,
                permission_mode=permission,
                use_rich=use_rich,
                interactive=interactive,
                approval_callback=approval_cb,
            ))
        else:
            # TTY with no prompt — launch interactive REPL
            from harness.cli.repl import Repl

            approval_cb = _create_approval_callback(permission, use_rich, is_tty=True)
            repl = Repl(
                provider=provider,
                model=model,
                max_turns=max_turns,
                cwd=cwd,
                api_key=api_key,
                base_url=base_url,
                permission_mode=permission,
                use_rich=use_rich,
                approval_callback=approval_cb,
            )
            asyncio.run(repl.run())
    else:
        prompt_text = " ".join(prompt_args)
        if not prompt_text:
            click.echo("Error: empty prompt", err=True)
            sys.exit(1)

        is_tty = sys.stdin.isatty()
        approval_cb = _create_approval_callback(permission, use_rich, is_tty=is_tty)
        asyncio.run(_run_agent(
            prompt_text,
            provider=provider,
            model=model,
            session_id=session,
            max_turns=max_turns,
            cwd=cwd,
            api_key=api_key,
            base_url=base_url,
            permission_mode=permission,
            use_rich=use_rich,
            interactive=interactive or is_tty,
            approval_callback=approval_cb,
        ))


def _create_approval_callback(
    permission_mode: str, use_rich: bool, *, is_tty: bool,
) -> Any | None:
    """Create an approval callback based on the permission mode and terminal state.

    Returns None if permission mode is bypass (no approval needed) or if
    there's no TTY to prompt the user.
    """
    if permission_mode == "bypass":
        return None
    if not is_tty:
        return None
    if use_rich:
        from harness.ui.approval import RichApprovalCallback
        return RichApprovalCallback()
    from harness.permissions.approval import StdinApprovalCallback
    return StdinApprovalCallback()


async def _run_agent(
    prompt: str,
    *,
    provider: str,
    model: str | None,
    session_id: str | None,
    max_turns: int,
    cwd: str | None,
    api_key: str | None,
    base_url: str | None,
    permission_mode: str,
    use_rich: bool = False,
    interactive: bool = False,
    approval_callback: Any | None = None,
) -> None:
    """Run the agent and print output."""
    from harness.core.engine import run

    # Choose output printer
    if use_rich:
        from harness.ui.terminal import RichPrinter

        printer = RichPrinter()
        output_fn = printer.print_message
    else:
        output_fn = print_message

    async for msg in run(
        prompt,
        provider=provider,
        model=model,
        session_id=session_id,
        max_turns=max_turns,
        cwd=cwd,
        api_key=api_key,
        base_url=base_url,
        permission_mode=permission_mode,
        interactive=interactive,
        approval_callback=approval_callback,
    ):
        output_fn(msg)


def _register_subcommands() -> None:
    """Register CLI subcommands."""
    from harness.cli.commands import config_cmd, connect_cmd, eval_cmd, models_cmd, sessions_cmd

    cli.add_command(config_cmd, "config")
    cli.add_command(models_cmd, "models")
    cli.add_command(sessions_cmd, "sessions")
    cli.add_command(eval_cmd, "eval")
    cli.add_command(connect_cmd, "connect")


_register_subcommands()


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
