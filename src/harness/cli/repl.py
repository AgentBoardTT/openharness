"""Interactive REPL for Harness."""

from __future__ import annotations

import asyncio
import getpass
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from harness.types.messages import Message, Result, SystemEvent, TextMessage

# Default models per provider (must match engine.py)
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "google": "gemini-2.0-flash",
    "ollama": "llama3.3",
}

PROVIDER_DISPLAY = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
    "ollama": "Ollama",
}


class Repl:
    """Interactive read-eval-print loop for Harness.

    Enters a loop: read prompt -> run agent -> print output -> repeat.
    Supports session continuity, Ctrl+C cancellation, and slash commands.
    """

    # Ordered dict — this is the order they appear in /help and the command palette
    SLASH_COMMANDS = {
        # --- Core workflow ---
        "/help": "Show available commands and tips",
        "/connect": "Set up or change your API key",
        "/model": "Switch model (e.g. /model gpt-5.2)",
        "/models": "List available models",
        # --- Session & context ---
        "/status": "Show provider, model, session, and cost",
        "/cost": "Show token usage and cost for this session",
        "/compact": "Summarize conversation to free up context",
        "/session": "Show or switch session ID",
        # --- Code & project ---
        "/diff": "Show git diff of changes in working directory",
        "/init": "Create a HARNESS.md project config file",
        "/doctor": "Check your setup (provider, API key, tools)",
        "/permission": "View or change permission mode",
        # --- Display ---
        "/clear": "Clear the screen",
        "/exit": "Exit Harness (or press Ctrl+D)",
    }

    def __init__(
        self,
        *,
        provider: str = "anthropic",
        model: str | None = None,
        max_turns: int = 100,
        cwd: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        permission_mode: str = "default",
        use_rich: bool = True,
        approval_callback: Any | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_turns = max_turns
        self._cwd = cwd
        self._api_key = api_key
        self._base_url = base_url
        self._permission_mode = permission_mode
        self._use_rich = use_rich
        self._approval_callback = approval_callback
        self._session_id: str | None = None
        self._cancelled = False
        self._total_tokens = 0
        self._total_cost = 0.0
        self._turn_count = 0

    # -- Display helpers -------------------------------------------------------

    @property
    def _display_model(self) -> str:
        """Human-readable model name for display."""
        model_id = self._model or DEFAULT_MODELS.get(self._provider, "unknown")
        try:
            from harness.providers.registry import resolve_model
            info = resolve_model(model_id)
            return info.display_name
        except Exception:
            return model_id

    @property
    def _display_provider(self) -> str:
        return PROVIDER_DISPLAY.get(self._provider, self._provider)

    @property
    def _short_model(self) -> str:
        model_id = self._model or DEFAULT_MODELS.get(self._provider, "?")
        try:
            from harness.providers.registry import resolve_model
            info = resolve_model(model_id)
            return info.aliases[0] if info.aliases else info.id
        except Exception:
            return model_id

    def _has_api_key(self) -> bool:
        """Check whether an API key is available for the current provider."""
        if self._api_key:
            return True
        if self._provider == "ollama":
            return True
        from harness.core.config import resolve_api_key
        return resolve_api_key(self._provider) is not None

    # -- Main loop -------------------------------------------------------------

    async def run(self) -> None:
        """Main REPL loop."""
        self._print_banner()

        if not self._has_api_key():
            self._print_no_key_guide()

        while True:
            try:
                prompt = await self._read_prompt()
            except EOFError:
                print("\nGoodbye!")
                break
            except KeyboardInterrupt:
                print()
                continue

            if not prompt:
                continue

            # Bare "/" — show command palette
            if prompt == "/":
                self._show_command_palette()
                continue

            # Handle slash commands
            if prompt.startswith("/"):
                if self._handle_slash_command(prompt):
                    continue
                if prompt.split()[0].lower() == "/exit":
                    break

            # Check for API key before running
            if not self._has_api_key():
                self._print_no_key_guide()
                continue

            # Run the prompt through the agent
            await self._run_prompt(prompt)

    async def _read_prompt(self) -> str:
        """Read a prompt from stdin asynchronously."""
        loop = asyncio.get_running_loop()
        prompt_str = f"{self._short_model} > "
        try:
            line = await loop.run_in_executor(None, lambda: input(prompt_str))
        except EOFError:
            raise
        except KeyboardInterrupt:
            raise
        return line.strip()

    async def _run_prompt(self, prompt: str) -> None:
        """Run a single prompt through the engine and print messages."""
        from harness.core.engine import run

        if self._use_rich:
            from harness.ui.terminal import RichPrinter
            printer = RichPrinter()
            output_fn = printer.print_message
        else:
            from harness.cli.output import print_message
            output_fn = print_message

        self._cancelled = False
        original_handler = signal.getsignal(signal.SIGINT)

        def _cancel_handler(signum: int, frame: Any) -> None:
            self._cancelled = True

        try:
            signal.signal(signal.SIGINT, _cancel_handler)

            async for msg in run(
                prompt,
                provider=self._provider,
                model=self._model,
                session_id=self._session_id,
                max_turns=self._max_turns,
                cwd=self._cwd,
                api_key=self._api_key,
                base_url=self._base_url,
                permission_mode=self._permission_mode,
                interactive=True,
                approval_callback=self._approval_callback,
            ):
                if self._cancelled:
                    print("\n[cancelled]")
                    break

                # Capture session ID
                if isinstance(msg, SystemEvent) and msg.type == "session_start":
                    if self._session_id is None:
                        self._session_id = msg.data.get("session_id")
                elif isinstance(msg, Result):
                    if self._session_id is None:
                        self._session_id = msg.session_id
                    # Track usage
                    self._total_tokens += getattr(msg, "total_tokens", 0) or 0
                    self._total_cost += getattr(msg, "cost", 0.0) or 0.0
                    self._turn_count += 1

                output_fn(msg)

        finally:
            signal.signal(signal.SIGINT, original_handler)

        print()

    # -- Slash command dispatch -------------------------------------------------

    def _handle_slash_command(self, cmd: str) -> bool:
        """Handle a slash command. Returns True if handled (continue loop)."""
        parts = cmd.strip().split(maxsplit=1)
        base = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "/help": lambda: self._handle_help(),
            "/exit": lambda: None,  # handled in main loop
            "/connect": lambda: self._handle_connect(),
            "/model": lambda: self._handle_model(arg),
            "/models": lambda: self._handle_models(),
            "/status": lambda: self._handle_status(),
            "/cost": lambda: self._handle_cost(),
            "/compact": lambda: self._handle_compact(),
            "/session": lambda: self._handle_session(arg),
            "/diff": lambda: self._handle_diff(),
            "/init": lambda: self._handle_init(),
            "/doctor": lambda: self._handle_doctor(),
            "/permission": lambda: self._handle_permission(arg),
            "/clear": lambda: print("\033[2J\033[H", end=""),
        }

        if base == "/exit":
            print("Goodbye!")
            return False

        handler = handlers.get(base)
        if handler:
            handler()
            return True

        # Fuzzy suggestion
        matches = [c for c in self.SLASH_COMMANDS if c.startswith(base)]
        if matches:
            print(f"  Unknown command: {base}. Did you mean: {', '.join(matches)}?")
        else:
            print(f"  Unknown command: {base}. Type / to see all commands.")
        return True

    # -- Command palette -------------------------------------------------------

    def _show_command_palette(self) -> None:
        """Show all commands in a clean, grouped palette — triggered by bare '/'."""
        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print()
                c.print("  [bold]Commands[/bold]")
                c.print()
                c.print("  [cyan]/connect[/cyan]     Set up or change your API key")
                c.print("  [cyan]/model[/cyan]       Switch model [dim](e.g. /model opus)[/dim]")
                c.print("  [cyan]/models[/cyan]      List available models")
                c.print()
                c.print("  [cyan]/status[/cyan]      Show provider, model, session info")
                c.print("  [cyan]/cost[/cyan]        Show token usage and cost")
                c.print("  [cyan]/compact[/cyan]     Summarize conversation to free context")
                c.print("  [cyan]/session[/cyan]     Show or switch session")
                c.print()
                c.print("  [cyan]/diff[/cyan]        Show uncommitted changes [dim](git diff)[/dim]")
                c.print("  [cyan]/init[/cyan]        Create HARNESS.md project config")
                c.print("  [cyan]/doctor[/cyan]      Check your setup")
                c.print("  [cyan]/permission[/cyan]  View or change permission mode")
                c.print()
                c.print("  [cyan]/clear[/cyan]       Clear the screen")
                c.print("  [cyan]/help[/cyan]        Show help with examples")
                c.print("  [cyan]/exit[/cyan]        Exit [dim](or Ctrl+D)[/dim]")
                c.print()
                return
            except ImportError:
                pass

        print()
        print("  Commands")
        print()
        print("  /connect     Set up or change your API key")
        print("  /model       Switch model (e.g. /model opus)")
        print("  /models      List available models")
        print()
        print("  /status      Show provider, model, session info")
        print("  /cost        Show token usage and cost")
        print("  /compact     Summarize conversation to free context")
        print("  /session     Show or switch session")
        print()
        print("  /diff        Show uncommitted changes (git diff)")
        print("  /init        Create HARNESS.md project config")
        print("  /doctor      Check your setup")
        print("  /permission  View or change permission mode")
        print()
        print("  /clear       Clear the screen")
        print("  /help        Show help with examples")
        print("  /exit        Exit (or Ctrl+D)")
        print()

    # -- Command handlers -------------------------------------------------------

    def _handle_help(self) -> None:
        """Show help with commands and getting-started tips."""
        self._show_command_palette()
        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print("  [bold]Getting started[/bold]")
                c.print()
                c.print('  Just type what you want in plain English:')
                c.print()
                c.print('    [dim]"Fix the bug in auth.py"[/dim]')
                c.print('    [dim]"Write unit tests for the utils module"[/dim]')
                c.print('    [dim]"Explain how the login flow works"[/dim]')
                c.print('    [dim]"Refactor this function to use async/await"[/dim]')
                c.print('    [dim]"Find and fix all TODO comments in the codebase"[/dim]')
                c.print()
                c.print("  [bold]Keyboard shortcuts[/bold]")
                c.print()
                c.print("    [cyan]Ctrl+C[/cyan]   Cancel the current response")
                c.print("    [cyan]Ctrl+D[/cyan]   Exit Harness")
                c.print("    [cyan]/[/cyan]        Show command palette")
                c.print()
                return
            except ImportError:
                pass

        print("  Getting started")
        print()
        print("  Just type what you want in plain English:")
        print()
        print('    "Fix the bug in auth.py"')
        print('    "Write unit tests for the utils module"')
        print('    "Explain how the login flow works"')
        print('    "Refactor this function to use async/await"')
        print('    "Find and fix all TODO comments in the codebase"')
        print()
        print("  Keyboard shortcuts")
        print()
        print("    Ctrl+C   Cancel the current response")
        print("    Ctrl+D   Exit Harness")
        print("    /        Show command palette")
        print()

    def _handle_models(self) -> None:
        """List popular models grouped by provider."""
        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print()
                c.print("  [bold]Available models[/bold] [dim](use /model <name> to switch)[/dim]")
                c.print()
                c.print("    [cyan]Anthropic[/cyan]  sonnet [dim](default)[/dim], opus, haiku")
                c.print("    [cyan]OpenAI[/cyan]     gpt-5.2, gpt-4o, gpt-4.1, o3")
                c.print("    [cyan]Google[/cyan]     gemini-2.5-pro, gemini-2.5-flash, gemini-2.0-flash")
                c.print("    [cyan]Ollama[/cyan]     llama3.3, mistral, qwen, phi [dim](local, no key)[/dim]")
                c.print()
                c.print("  [dim]Run `harness models list` for the full list (50+ models).[/dim]")
                c.print()
                return
            except ImportError:
                pass

        print()
        print("  Available models (use /model <name> to switch)")
        print()
        print("    Anthropic  sonnet (default), opus, haiku")
        print("    OpenAI     gpt-5.2, gpt-4o, gpt-4.1, o3")
        print("    Google     gemini-2.5-pro, gemini-2.5-flash, gemini-2.0-flash")
        print("    Ollama     llama3.3, mistral, qwen, phi (local, no key)")
        print()
        print("  Run `harness models list` for the full list (50+ models).")
        print()

    def _handle_model(self, arg: str) -> None:
        """Switch to a different model."""
        if not arg:
            print(f"\n  Current: {self._display_model} ({self._display_provider})")
            print("  Usage: /model <name>    e.g. /model opus, /model gpt-5.2")
            print("  Type /models to see what's available.\n")
            return

        try:
            from harness.providers.registry import resolve_model
            info = resolve_model(arg)
        except KeyError:
            print(f"  Unknown model: {arg}. Type /models to see available models.")
            return

        old_display = self._display_model
        self._model = info.id
        self._provider = info.provider

        if not self._has_api_key():
            print(f"\n  Switched to {info.display_name}, but no API key for {self._display_provider}.")
            print("  Run /connect to set one up.\n")
        else:
            print(f"\n  {old_display} -> {info.display_name}\n")

    def _handle_status(self) -> None:
        """Show current configuration status."""
        has_key = self._has_api_key()
        key_status = "connected" if has_key else "not set -- run /connect"
        sid = self._session_id or "(new session)"
        cwd = self._cwd or os.getcwd()

        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print()
                c.print(f"  [bold]Provider[/bold]     {self._display_provider}")
                c.print(f"  [bold]Model[/bold]        {self._display_model}")
                key_style = "green" if has_key else "yellow"
                c.print(f"  [bold]API key[/bold]      [{key_style}]{key_status}[/{key_style}]")
                c.print(f"  [bold]Session[/bold]      {sid}")
                c.print(f"  [bold]Turns[/bold]        {self._turn_count}")
                c.print(f"  [bold]Tokens[/bold]       {self._total_tokens:,}")
                c.print(f"  [bold]Cost[/bold]         ${self._total_cost:.4f}")
                c.print(f"  [bold]Directory[/bold]    {cwd}")
                c.print(f"  [bold]Permission[/bold]   {self._permission_mode}")
                c.print()
                return
            except ImportError:
                pass

        print()
        print(f"  Provider     {self._display_provider}")
        print(f"  Model        {self._display_model}")
        print(f"  API key      {key_status}")
        print(f"  Session      {sid}")
        print(f"  Turns        {self._turn_count}")
        print(f"  Tokens       {self._total_tokens:,}")
        print(f"  Cost         ${self._total_cost:.4f}")
        print(f"  Directory    {cwd}")
        print(f"  Permission   {self._permission_mode}")
        print()

    def _handle_cost(self) -> None:
        """Show token usage and cost for the current session."""
        if self._turn_count == 0:
            print("\n  No usage yet. Start a conversation to see costs.\n")
            return

        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print()
                c.print(f"  [bold]Session cost[/bold]")
                c.print(f"    Turns:   {self._turn_count}")
                c.print(f"    Tokens:  {self._total_tokens:,}")
                c.print(f"    Cost:    [green]${self._total_cost:.4f}[/green]")
                c.print()
                return
            except ImportError:
                pass

        print()
        print(f"  Session cost")
        print(f"    Turns:   {self._turn_count}")
        print(f"    Tokens:  {self._total_tokens:,}")
        print(f"    Cost:    ${self._total_cost:.4f}")
        print()

    def _handle_compact(self) -> None:
        """Hint to the user about compaction."""
        print()
        print("  Context compaction happens automatically when the conversation")
        print("  approaches the model's context limit. Harness summarizes earlier")
        print("  messages to free up space while preserving key information.")
        print()
        if self._turn_count > 0:
            print(f"  Current session: {self._turn_count} turns, {self._total_tokens:,} tokens.")
        print("  To start fresh, use /session new")
        print()

    def _handle_session(self, arg: str) -> None:
        """Show or manage session."""
        if not arg:
            sid = self._session_id or "(none -- will be created on first prompt)"
            print(f"\n  Session: {sid}")
            print("  /session new     Start a fresh session")
            print("  /session <id>    Resume a previous session\n")
            return

        if arg == "new":
            self._session_id = None
            self._total_tokens = 0
            self._total_cost = 0.0
            self._turn_count = 0
            print("\n  New session started. Previous context cleared.\n")
            return

        # Resume an existing session
        self._session_id = arg
        self._total_tokens = 0
        self._total_cost = 0.0
        self._turn_count = 0
        print(f"\n  Resuming session: {arg}\n")

    def _handle_diff(self) -> None:
        """Show git diff of working directory."""
        cwd = self._cwd or os.getcwd()
        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, cwd=cwd, timeout=10,
            )
            if result.returncode != 0:
                print("\n  Not a git repository, or git is not installed.\n")
                return

            stat = result.stdout.strip()
            if not stat:
                # Check staged changes too
                staged = subprocess.run(
                    ["git", "diff", "--cached", "--stat"],
                    capture_output=True, text=True, cwd=cwd, timeout=10,
                )
                if staged.stdout.strip():
                    print(f"\n  Staged changes:\n{staged.stdout}")
                else:
                    print("\n  No uncommitted changes.\n")
                return

            # Show stat + abbreviated diff
            print(f"\n{stat}\n")

            full = subprocess.run(
                ["git", "diff", "--color=always"],
                capture_output=True, text=True, cwd=cwd, timeout=10,
            )
            # Show first 60 lines of the diff
            lines = full.stdout.splitlines()
            for line in lines[:60]:
                print(f"  {line}")
            if len(lines) > 60:
                print(f"\n  ... ({len(lines) - 60} more lines, run `git diff` to see all)")
            print()

        except FileNotFoundError:
            print("\n  git is not installed.\n")
        except subprocess.TimeoutExpired:
            print("\n  git diff timed out.\n")

    def _handle_init(self) -> None:
        """Create a HARNESS.md project config file."""
        cwd = Path(self._cwd or os.getcwd())
        harness_md = cwd / "HARNESS.md"

        if harness_md.exists():
            print(f"\n  HARNESS.md already exists at {harness_md}")
            print("  Edit it to customize project instructions for the agent.\n")
            return

        template = """# Project Instructions

## About this project
<!-- Describe what this project does so the agent has context -->

## Code style
<!-- e.g. "Use pytest for testing", "Follow PEP 8" -->

## Important notes
<!-- Anything the agent should always keep in mind -->
"""
        harness_md.write_text(template)
        print(f"\n  Created {harness_md}")
        print("  Edit this file to give the agent context about your project.")
        print("  The agent reads it automatically at the start of every session.\n")

    def _handle_doctor(self) -> None:
        """Check setup and report issues."""
        issues = []
        ok_items = []

        # Check provider
        ok_items.append(f"Provider: {self._display_provider}")

        # Check model
        model_id = self._model or DEFAULT_MODELS.get(self._provider, "unknown")
        try:
            from harness.providers.registry import resolve_model
            info = resolve_model(model_id)
            ok_items.append(f"Model: {info.display_name}")
        except Exception:
            issues.append(f"Model '{model_id}' not found in registry")

        # Check API key
        if self._has_api_key():
            ok_items.append("API key: configured")
        else:
            issues.append("API key: not set -- run /connect")

        # Check git
        cwd = self._cwd or os.getcwd()
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, cwd=cwd, timeout=5,
            )
            if r.returncode == 0:
                ok_items.append("Git: available")
            else:
                issues.append("Git: not a git repository")
        except FileNotFoundError:
            issues.append("Git: not installed")
        except subprocess.TimeoutExpired:
            issues.append("Git: timed out")

        # Check HARNESS.md
        harness_md = Path(cwd) / "HARNESS.md"
        if harness_md.exists():
            ok_items.append("HARNESS.md: found")
        else:
            issues.append("HARNESS.md: not found (run /init to create one)")

        # Check config file
        config_path = Path.home() / ".harness" / "config.toml"
        if config_path.exists():
            ok_items.append(f"Config: {config_path}")
        else:
            issues.append("Config: no ~/.harness/config.toml found")

        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print()
                c.print("  [bold]Doctor[/bold]")
                c.print()
                for item in ok_items:
                    c.print(f"  [green]OK[/green]   {item}")
                for item in issues:
                    c.print(f"  [yellow]!![/yellow]   {item}")
                c.print()
                if not issues:
                    c.print("  [green]Everything looks good![/green]")
                else:
                    c.print(f"  [yellow]{len(issues)} issue(s) found.[/yellow]")
                c.print()
                return
            except ImportError:
                pass

        print()
        print("  Doctor")
        print()
        for item in ok_items:
            print(f"  OK   {item}")
        for item in issues:
            print(f"  !!   {item}")
        print()
        if not issues:
            print("  Everything looks good!")
        else:
            print(f"  {len(issues)} issue(s) found.")
        print()

    def _handle_permission(self, arg: str) -> None:
        """View or change permission mode."""
        modes = {
            "default": "Read tools auto-allowed, writes ask for approval",
            "accept_edits": "File edits auto-allowed, shell commands ask",
            "plan": "Read-only -- nothing gets changed",
            "bypass": "Full auto-approve (for scripts/CI)",
        }

        if not arg:
            if self._use_rich:
                try:
                    from rich.console import Console
                    c = Console(stderr=True)
                    c.print()
                    c.print(f"  [bold]Current:[/bold] {self._permission_mode}")
                    c.print()
                    for mode, desc in modes.items():
                        marker = "[cyan]>[/cyan] " if mode == self._permission_mode else "  "
                        c.print(f"  {marker}[bold]{mode:<14}[/bold] [dim]{desc}[/dim]")
                    c.print()
                    c.print("  [dim]Usage: /permission <mode>[/dim]")
                    c.print()
                    return
                except ImportError:
                    pass

            print(f"\n  Current: {self._permission_mode}")
            print()
            for mode, desc in modes.items():
                marker = "> " if mode == self._permission_mode else "  "
                print(f"  {marker}{mode:<14} {desc}")
            print()
            print("  Usage: /permission <mode>")
            print()
            return

        arg = arg.lower().strip()
        if arg not in modes:
            print(f"  Unknown mode: {arg}. Options: {', '.join(modes)}")
            return

        old = self._permission_mode
        self._permission_mode = arg
        print(f"\n  Permission: {old} -> {arg}\n")

    # -- Connect flow ----------------------------------------------------------

    PROVIDERS = {
        "1": "anthropic",
        "2": "openai",
        "3": "google",
    }

    def _handle_connect(self) -> None:
        """Interactive flow to set up an API key."""
        print("\n  Select a provider:")
        print("    (1) Anthropic   https://console.anthropic.com/settings/keys")
        print("    (2) OpenAI      https://platform.openai.com/api-keys")
        print("    (3) Google      https://aistudio.google.com/apikey")
        print()

        try:
            choice = input("  Enter choice [1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return

        provider = self.PROVIDERS.get(choice)
        if not provider:
            print(f"  Invalid choice: {choice}")
            return

        try:
            api_key = getpass.getpass(f"  API key for {PROVIDER_DISPLAY.get(provider, provider)}: ")
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return

        if not api_key.strip():
            print("  No key entered. Cancelled.")
            return

        api_key = api_key.strip()

        from harness.core.config import save_api_key

        config_path = save_api_key(provider, api_key)

        self._provider = provider
        self._api_key = api_key

        print(f"\n  Connected to {PROVIDER_DISPLAY.get(provider, provider)}.")
        print(f"  Model: {self._display_model}")
        print(f"  Key saved to {config_path}")
        print()

    # -- Banner & guides -------------------------------------------------------

    def _print_no_key_guide(self) -> None:
        """Print a friendly guide when no API key is configured."""
        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print()
                c.print("  [yellow]No API key found.[/yellow] Let's fix that in 30 seconds:")
                c.print()
                c.print("  [bold]Option 1:[/bold] Type [cyan]/connect[/cyan] right here")
                c.print("  [bold]Option 2:[/bold] Run [cyan]harness connect[/cyan] from another terminal")
                c.print("  [bold]Option 3:[/bold] Set an environment variable:")
                c.print("             [dim]export ANTHROPIC_API_KEY=sk-ant-...[/dim]")
                c.print()
                c.print("  [dim]Need a key? Get one at:[/dim]")
                c.print("    [dim]Anthropic:[/dim]  https://console.anthropic.com/settings/keys")
                c.print("    [dim]OpenAI:[/dim]     https://platform.openai.com/api-keys")
                c.print("    [dim]Google:[/dim]     https://aistudio.google.com/apikey")
                c.print()
                return
            except ImportError:
                pass
        print()
        print("  No API key found. Let's fix that in 30 seconds:")
        print()
        print("  Option 1: Type /connect right here")
        print("  Option 2: Run `harness connect` from another terminal")
        print("  Option 3: Set an environment variable:")
        print("            export ANTHROPIC_API_KEY=sk-ant-...")
        print()
        print("  Need a key? Get one at:")
        print("    Anthropic:  https://console.anthropic.com/settings/keys")
        print("    OpenAI:     https://platform.openai.com/api-keys")
        print("    Google:     https://aistudio.google.com/apikey")
        print()

    def _print_banner(self) -> None:
        """Print the welcome banner with current model info."""
        model = self._display_model
        provider = self._display_provider
        cwd = Path(self._cwd or os.getcwd()).name or "~"

        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print()
                c.print("  [bold cyan]Harness[/bold cyan]", highlight=False)
                c.print(f"  [dim]{provider} / {model}  |  {cwd}[/dim]")
                c.print()
                c.print("  [dim]Type what you need, or press [/dim][cyan]/[/cyan][dim] for commands.[/dim]")
                c.print()
                return
            except ImportError:
                pass
        print()
        print("  Harness")
        print(f"  {provider} / {model}  |  {cwd}")
        print()
        print("  Type what you need, or press / for commands.")
        print()
