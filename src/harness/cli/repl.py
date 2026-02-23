"""Interactive REPL for Harness."""

from __future__ import annotations

import asyncio
import getpass
import signal
import sys
from typing import Any

from harness.types.messages import Message, Result, SystemEvent, TextMessage


class Repl:
    """Interactive read-eval-print loop for Harness.

    Enters a loop: read prompt -> run agent -> print output -> repeat.
    Supports session continuity, Ctrl+C cancellation, and slash commands.
    """

    SLASH_COMMANDS = {
        "/help": "Show available commands",
        "/exit": "Exit the REPL",
        "/session": "Show current session ID",
        "/clear": "Clear the screen",
        "/connect": "Set up API key for a provider",
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

    async def run(self) -> None:
        """Main REPL loop."""
        self._print_banner()

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
                if prompt == "/exit":
                    break

            # Run the prompt through the agent
            await self._run_prompt(prompt)

    async def _read_prompt(self) -> str:
        """Read a prompt from stdin asynchronously."""
        loop = asyncio.get_running_loop()
        try:
            line = await loop.run_in_executor(None, lambda: input("> "))
        except EOFError:
            raise
        except KeyboardInterrupt:
            raise
        return line.strip()

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
        cmd = cmd.strip().lower()

        if cmd == "/help":
            print("\nAvailable commands:")
            for name, desc in self.SLASH_COMMANDS.items():
                print(f"  {name:<12} {desc}")
            print()
            return True

        if cmd == "/exit":
            print("Goodbye!")
            return False  # Signal the loop to break

        if cmd == "/session":
            sid = self._session_id or "(none — will be created on first prompt)"
            print(f"Session: {sid}")
            return True

        if cmd == "/clear":
            print("\033[2J\033[H", end="")
            return True

        if cmd == "/connect":
            self._handle_connect()
            return True

        print(f"Unknown command: {cmd}. Type /help for available commands.")
        return True

    PROVIDERS = {
        "1": "anthropic",
        "2": "openai",
        "3": "google",
    }

    def _handle_connect(self) -> None:
        """Interactive flow to set up an API key."""
        print("\nSelect a provider:")
        print("  (1) Anthropic")
        print("  (2) OpenAI")
        print("  (3) Google")
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
            api_key = getpass.getpass(f"API key for {provider}: ")
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

        print(f"\nConnected to {provider}. Your key is saved to {config_path}")

    def _print_banner(self) -> None:
        """Print the welcome banner."""
        if self._use_rich:
            try:
                from rich.console import Console
                console = Console(stderr=True)
                console.print("[bold]Harness[/bold] interactive mode", style="cyan")
                console.print("[dim]Type /help for commands, Ctrl+D to exit[/dim]")
                console.print()
                return
            except ImportError:
                pass
        print("Harness interactive mode")
        print("Type /help for commands, Ctrl+D to exit")
        print()
