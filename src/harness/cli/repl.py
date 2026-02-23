"""Interactive REPL for Harness."""

from __future__ import annotations

import asyncio
import getpass
import os
import signal
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

    SLASH_COMMANDS = {
        "/help": "Show available commands and tips",
        "/connect": "Set up or change your API key",
        "/model": "Switch model (e.g. /model gpt-5.2)",
        "/models": "List available models",
        "/status": "Show current provider, model, and session",
        "/session": "Show current session ID",
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

    def _has_api_key(self) -> bool:
        """Check whether an API key is available for the current provider."""
        if self._api_key:
            return True
        if self._provider == "ollama":
            return True  # Ollama doesn't need a key
        from harness.core.config import resolve_api_key
        return resolve_api_key(self._provider) is not None

    async def run(self) -> None:
        """Main REPL loop."""
        self._print_banner()

        # If no API key, guide the user immediately
        if not self._has_api_key():
            self._print_no_key_guide()

        while True:
            try:
                prompt = await self._read_prompt()
            except EOFError:
                # Ctrl+D
                print("\nGoodbye!")
                break
            except KeyboardInterrupt:
                # Ctrl+C at prompt — just print newline and continue
                print()
                continue

            if not prompt:
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
        prompt_str = self._build_prompt_string()
        try:
            line = await loop.run_in_executor(None, lambda: input(prompt_str))
        except EOFError:
            raise
        except KeyboardInterrupt:
            raise
        return line.strip()

    def _build_prompt_string(self) -> str:
        """Build the input prompt showing current model."""
        model_id = self._model or DEFAULT_MODELS.get(self._provider, "?")
        # Use short alias if possible
        try:
            from harness.providers.registry import resolve_model
            info = resolve_model(model_id)
            short = info.aliases[0] if info.aliases else info.id
        except Exception:
            short = model_id
        return f"{short} > "

    async def _run_prompt(self, prompt: str) -> None:
        """Run a single prompt through the engine and print messages."""
        from harness.core.engine import run

        # Choose output printer
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

                # Capture session ID for continuity
                if isinstance(msg, SystemEvent) and msg.type == "session_start":
                    if self._session_id is None:
                        self._session_id = msg.data.get("session_id")
                elif isinstance(msg, Result):
                    if self._session_id is None:
                        self._session_id = msg.session_id

                output_fn(msg)

        finally:
            signal.signal(signal.SIGINT, original_handler)

        # Print a blank line after each response for spacing
        print()

    def _handle_slash_command(self, cmd: str) -> bool:
        """Handle a slash command. Returns True if handled (continue loop)."""
        parts = cmd.strip().split(maxsplit=1)
        base = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if base == "/help":
            self._handle_help()
            return True

        if base == "/exit":
            print("Goodbye!")
            return False  # Signal the loop to break

        if base == "/connect":
            self._handle_connect()
            return True

        if base == "/model":
            self._handle_model(arg)
            return True

        if base == "/models":
            self._handle_models()
            return True

        if base == "/status":
            self._handle_status()
            return True

        if base == "/session":
            sid = self._session_id or "(none -- will be created on first prompt)"
            print(f"Session: {sid}")
            return True

        if base == "/clear":
            print("\033[2J\033[H", end="")
            return True

        print(f"Unknown command: {base}. Type /help for available commands.")
        return True

    def _handle_help(self) -> None:
        """Show help with commands and getting-started tips."""
        print("\n  Commands:")
        for name, desc in self.SLASH_COMMANDS.items():
            print(f"    {name:<12} {desc}")

        print("\n  Tips:")
        print("    Just type what you want in plain English.")
        print('    Example: "Fix the bug in auth.py"')
        print('    Example: "Write unit tests for utils.py"')
        print('    Example: "Explain how the login flow works"')
        print()
        print("  Shortcuts:")
        print("    Ctrl+C     Cancel the current response")
        print("    Ctrl+D     Exit Harness")
        print()

    def _handle_models(self) -> None:
        """List popular models grouped by provider."""
        print("\n  Available models (use /model <name> to switch):\n")
        print("    Anthropic    sonnet (default), opus, haiku")
        print("    OpenAI       gpt-5.2, gpt-4o, gpt-4.1, o3")
        print("    Google       gemini-2.5-pro, gemini-2.5-flash, gemini-2.0-flash")
        print("    Ollama       llama3.3, mistral, qwen, phi  (local, no key)")
        print()
        print("  Run `harness models list` in your shell for the full list (50+ models).")
        print()

    def _handle_model(self, arg: str) -> None:
        """Switch to a different model."""
        if not arg:
            print(f"\n  Current model: {self._display_model} ({self._display_provider})")
            print("  Usage: /model <name>")
            print("  Example: /model gpt-5.2")
            print("  Example: /model opus")
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

        # Check if we have a key for the new provider
        if not self._has_api_key():
            print(f"\n  Switched to {info.display_name}, but no API key found for {self._display_provider}.")
            print("  Run /connect to set one up.\n")
        else:
            print(f"\n  Switched: {old_display} -> {info.display_name}\n")

    def _handle_status(self) -> None:
        """Show current configuration status."""
        has_key = self._has_api_key()
        key_status = "connected" if has_key else "not set -- run /connect"
        sid = self._session_id or "(new session)"
        cwd = self._cwd or os.getcwd()

        print(f"\n  Provider:   {self._display_provider}")
        print(f"  Model:      {self._display_model}")
        print(f"  API key:    {key_status}")
        print(f"  Session:    {sid}")
        print(f"  Directory:  {cwd}")
        print(f"  Permission: {self._permission_mode}")
        print()

    PROVIDERS = {
        "1": "anthropic",
        "2": "openai",
        "3": "google",
    }

    def _handle_connect(self) -> None:
        """Interactive flow to set up an API key."""
        print("\nSelect a provider:")
        print("  (1) Anthropic   https://console.anthropic.com/settings/keys")
        print("  (2) OpenAI      https://platform.openai.com/api-keys")
        print("  (3) Google      https://aistudio.google.com/apikey")
        print()

        try:
            choice = input("Enter choice [1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return

        provider = self.PROVIDERS.get(choice)
        if not provider:
            print(f"Invalid choice: {choice}")
            return

        try:
            api_key = getpass.getpass(f"API key for {PROVIDER_DISPLAY.get(provider, provider)}: ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return

        if not api_key.strip():
            print("No key entered. Cancelled.")
            return

        api_key = api_key.strip()

        from harness.core.config import save_api_key

        config_path = save_api_key(provider, api_key)

        # Update live REPL state so subsequent prompts use the new key
        self._provider = provider
        self._api_key = api_key

        print(f"\n  Connected to {PROVIDER_DISPLAY.get(provider, provider)}.")
        print(f"  Model: {self._display_model}")
        print(f"  Key saved to {config_path}")
        print()
        print("  You're all set! Type a prompt to get started.")
        print('  Example: "Explain how this project is structured"\n')

    def _print_no_key_guide(self) -> None:
        """Print a friendly guide when no API key is configured."""
        if self._use_rich:
            try:
                from rich.console import Console
                c = Console(stderr=True)
                c.print()
                c.print("  [yellow]No API key found.[/yellow] Let's fix that in 30 seconds:")
                c.print()
                c.print("  [bold]Option 1:[/bold] Run [cyan]/connect[/cyan] right here to set up your key")
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
        print("  Option 1: Run /connect right here to set up your key")
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
                c.print(f"  [dim]{provider} / {model}[/dim]")
                c.print(f"  [dim]{cwd}[/dim]")
                c.print()
                c.print("  [dim]Type your task in plain English. /help for commands, Ctrl+D to exit.[/dim]")
                c.print()
                return
            except ImportError:
                pass
        print()
        print(f"  Harness")
        print(f"  {provider} / {model}")
        print(f"  {cwd}")
        print()
        print("  Type your task in plain English. /help for commands, Ctrl+D to exit.")
        print()
