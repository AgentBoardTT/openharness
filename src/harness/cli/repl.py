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
        # --- Agents ---
        "/plan": "Plan implementation with a read-only agent",
        "/review": "Review code changes or a specific file",
        "/team": "Decompose a task and run agents in parallel",
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

        # Eagerly resolve API key from config if not passed via CLI.
        # This covers the case where the user previously ran /connect
        # and the key is saved in ~/.harness/config.toml.
        self._load_saved_api_key()

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

    def _load_saved_api_key(self) -> None:
        """Try to load an API key from saved config into self._api_key.

        If no key is found for the current provider, check whether *any*
        saved provider has a key and auto-switch to it.  This handles the
        common case where a user ran ``/connect`` once and expects it to
        Just Work on next launch.
        """
        if self._api_key:
            return  # Already have an explicit key
        if self._provider == "ollama":
            return

        from harness.core.config import resolve_api_key

        # 1. Check current provider
        key = resolve_api_key(self._provider)
        if key:
            self._api_key = key
            return

        # 2. No key for current provider — scan saved providers
        try:
            from pathlib import Path
            import tomllib
            config_path = Path.home() / ".harness" / "config.toml"
            if not config_path.exists():
                return
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            for prov, prov_conf in data.get("providers", {}).items():
                saved_key = prov_conf.get("api_key") if isinstance(prov_conf, dict) else None
                if saved_key:
                    self._provider = prov
                    self._api_key = saved_key
                    # Also resolve the default model for this provider
                    if not self._model:
                        self._model = DEFAULT_MODELS.get(prov)
                    return
        except Exception:
            pass

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
                if await self._handle_slash_command(prompt):
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

    async def _handle_slash_command(self, cmd: str) -> bool:
        """Handle a slash command. Returns True if handled (continue loop)."""
        parts = cmd.strip().split(maxsplit=1)
        base = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Sync handlers — called directly
        sync_handlers = {
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

        # Async handlers — awaited
        async_handlers = {
            "/plan": lambda: self._handle_plan(arg),
            "/review": lambda: self._handle_review(arg),
            "/team": lambda: self._handle_team(arg),
        }

        if base == "/exit":
            print("Goodbye!")
            return False

        handler = sync_handlers.get(base)
        if handler:
            handler()
            return True

        async_handler = async_handlers.get(base)
        if async_handler:
            await async_handler()
            return True

        # Fuzzy suggestion
        matches = [c for c in self.SLASH_COMMANDS if c.startswith(base)]
        if matches:
            print(f"  Unknown command: {base}. Did you mean: {', '.join(matches)}?")
        else:
            print(f"  Unknown command: {base}. Type / to see all commands.")
        return True

    # -- Rich console helper ----------------------------------------------------

    def _rc(self) -> Any | None:
        """Return a Rich Console writing to stderr, or None if unavailable."""
        if not self._use_rich:
            return None
        try:
            from rich.console import Console
            return Console(stderr=True)
        except ImportError:
            return None

    # ── Palette colours (referenced in Rich markup) ──────────────────────────
    # Primary accent:  #a78bfa (violet)     Command names / brand
    # Secondary:       #60a5fa (blue)        Interactive / hints
    # Success:         #34d399 (green)       OK / connected
    # Warning:         #fbbf24 (amber)       Caution / missing
    # Error:           #f87171 (red)         Errors
    # Muted:           #7c7c8a (grey)        Secondary info
    # Label:           #94a3b8 (slate)       Key-value labels
    # Bright:          #e2e8f0 (near-white)  Values
    _V = "#a78bfa"   # violet
    _B = "#60a5fa"   # blue
    _G = "#34d399"   # green
    _A = "#fbbf24"   # amber
    _R = "#f87171"   # red
    _M = "#7c7c8a"   # muted
    _L = "#94a3b8"   # slate / label
    _W = "#e2e8f0"   # bright

    # -- Command palette -------------------------------------------------------

    def _show_command_palette(self) -> None:
        """Show all commands in a clean, grouped palette — triggered by bare '/'."""
        c = self._rc()
        if c:
            _V, _M = self._V, self._M

            def _cmd(name: str, desc: str, note: str = "") -> None:
                n = f"  [{_V} bold]{name:<14}[/]"
                d = f"[{_M}]{desc}[/]"
                tail = f"  [dim]{note}[/dim]" if note else ""
                c.print(f"{n} {d}{tail}")

            c.print()
            c.print(f"  [bold {_V}]\u2501\u2501 Commands[/]")
            c.print()
            _cmd("/connect", "Set up or change your API key")
            _cmd("/model", "Switch model", "e.g. /model opus")
            _cmd("/models", "List available models")
            c.print()
            c.print(f"  [dim {_M}]\u250a Agents[/]")
            _cmd("/plan", "Plan implementation", "read-only")
            _cmd("/review", "Review code changes or a file")
            _cmd("/team", "Decompose task & run agents in parallel")
            c.print()
            c.print(f"  [dim {_M}]\u250a Session[/]")
            _cmd("/status", "Provider, model, session & cost")
            _cmd("/cost", "Token usage and cost")
            _cmd("/compact", "Summarize conversation to free context")
            _cmd("/session", "Show or switch session")
            c.print()
            c.print(f"  [dim {_M}]\u250a Project[/]")
            _cmd("/diff", "Show uncommitted changes", "git diff")
            _cmd("/init", "Create HARNESS.md project config")
            _cmd("/doctor", "Check your setup")
            _cmd("/permission", "View or change permission mode")
            c.print()
            c.print(f"  [dim {_M}]\u250a Other[/]")
            _cmd("/clear", "Clear the screen")
            _cmd("/help", "Show help with examples")
            _cmd("/exit", "Exit", "or Ctrl+D")
            c.print()
            return

        print()
        print("  == Commands")
        print()
        print("  /connect       Set up or change your API key")
        print("  /model         Switch model (e.g. /model opus)")
        print("  /models        List available models")
        print()
        print("  : Agents")
        print("  /plan          Plan implementation (read-only)")
        print("  /review        Review code changes or a file")
        print("  /team          Decompose task & run agents in parallel")
        print()
        print("  : Session")
        print("  /status        Provider, model, session & cost")
        print("  /cost          Token usage and cost")
        print("  /compact       Summarize conversation to free context")
        print("  /session       Show or switch session")
        print()
        print("  : Project")
        print("  /diff          Show uncommitted changes (git diff)")
        print("  /init          Create HARNESS.md project config")
        print("  /doctor        Check your setup")
        print("  /permission    View or change permission mode")
        print()
        print("  : Other")
        print("  /clear         Clear the screen")
        print("  /help          Show help with examples")
        print("  /exit          Exit (or Ctrl+D)")
        print()

    # -- Command handlers -------------------------------------------------------

    def _handle_help(self) -> None:
        """Show help with commands and getting-started tips."""
        self._show_command_palette()
        c = self._rc()
        if c:
            _V, _B, _M = self._V, self._B, self._M
            c.print(f"  [bold {_V}]\u2501\u2501 Getting started[/]")
            c.print()
            c.print(f"  [{_M}]Just type what you want in plain English:[/]")
            c.print()
            c.print(f'    [{_M}]\u25b8[/] [italic {_M}]"Fix the bug in auth.py"[/]')
            c.print(f'    [{_M}]\u25b8[/] [italic {_M}]"Write unit tests for the utils module"[/]')
            c.print(f'    [{_M}]\u25b8[/] [italic {_M}]"Explain how the login flow works"[/]')
            c.print(f'    [{_M}]\u25b8[/] [italic {_M}]"Refactor this function to use async/await"[/]')
            c.print()
            c.print(f"  [bold {_V}]\u2501\u2501 Keyboard shortcuts[/]")
            c.print()
            c.print(f"    [{_B}]Ctrl+C[/]   [{_M}]Cancel the current response[/]")
            c.print(f"    [{_B}]Ctrl+D[/]   [{_M}]Exit Harness[/]")
            c.print(f"    [{_B}]/[/]        [{_M}]Show command palette[/]")
            c.print()
            return

        print("  == Getting started")
        print()
        print("  Just type what you want in plain English:")
        print()
        print('    > "Fix the bug in auth.py"')
        print('    > "Write unit tests for the utils module"')
        print('    > "Explain how the login flow works"')
        print('    > "Refactor this function to use async/await"')
        print()
        print("  == Keyboard shortcuts")
        print()
        print("    Ctrl+C   Cancel the current response")
        print("    Ctrl+D   Exit Harness")
        print("    /        Show command palette")
        print()

    def _handle_models(self) -> None:
        """List popular models grouped by provider."""
        c = self._rc()
        if c:
            _V, _B, _M, _W = self._V, self._B, self._M, self._W
            c.print()
            c.print(f"  [bold {_V}]\u2501\u2501 Available models[/]  [dim]use /model <name> to switch[/dim]")
            c.print()
            c.print(f"    [{_B}]Anthropic[/]  [{_W}]sonnet[/] [dim](default)[/dim][{_M}],[/] [{_W}]opus[/][{_M}],[/] [{_W}]haiku[/]")
            c.print(f"    [{_B}]OpenAI[/]     [{_W}]gpt-5.2[/][{_M}],[/] [{_W}]gpt-4o[/][{_M}],[/] [{_W}]gpt-4.1[/][{_M}],[/] [{_W}]o3[/]")
            c.print(f"    [{_B}]Google[/]     [{_W}]gemini-2.5-pro[/][{_M}],[/] [{_W}]gemini-2.5-flash[/][{_M}],[/] [{_W}]gemini-2.0-flash[/]")
            c.print(f"    [{_B}]Ollama[/]     [{_W}]llama3.3[/][{_M}],[/] [{_W}]mistral[/][{_M}],[/] [{_W}]qwen[/][{_M}],[/] [{_W}]phi[/]  [dim]local, no key[/dim]")
            c.print()
            c.print(f"  [dim]Run [/dim][{_V}]harness models list[/][dim] for the full catalogue (50+ models).[/dim]")
            c.print()
            return

        print()
        print("  == Available models  (use /model <name> to switch)")
        print()
        print("    Anthropic  sonnet (default), opus, haiku")
        print("    OpenAI     gpt-5.2, gpt-4o, gpt-4.1, o3")
        print("    Google     gemini-2.5-pro, gemini-2.5-flash, gemini-2.0-flash")
        print("    Ollama     llama3.3, mistral, qwen, phi  (local, no key)")
        print()
        print("  Run `harness models list` for the full catalogue (50+ models).")
        print()

    def _handle_model(self, arg: str) -> None:
        """Switch to a different model."""
        c = self._rc()
        if not arg:
            if c:
                c.print()
                c.print(f"  [bold {self._V}]Current:[/] [{self._W}]{self._display_model}[/]  [{self._M}]({self._display_provider})[/]")
                c.print(f"  [{self._M}]Usage:[/] [{self._V}]/model <name>[/]  [dim]e.g. /model opus, /model gpt-5.2[/dim]")
                c.print(f"  [{self._M}]Type[/] [{self._V}]/models[/] [{self._M}]to see what's available.[/]")
                c.print()
            else:
                print(f"\n  Current: {self._display_model} ({self._display_provider})")
                print("  Usage: /model <name>    e.g. /model opus, /model gpt-5.2")
                print("  Type /models to see what's available.\n")
            return

        try:
            from harness.providers.registry import resolve_model
            info = resolve_model(arg)
        except KeyError:
            if c:
                c.print(f"  [{self._R}]\u2717[/] Unknown model: [{self._W}]{arg}[/]. Type [{self._V}]/models[/] to see available models.")
            else:
                print(f"  Unknown model: {arg}. Type /models to see available models.")
            return

        old_display = self._display_model
        self._model = info.id
        self._provider = info.provider

        # Persist choice for next launch
        from harness.core.config import save_defaults
        save_defaults(provider=info.provider, model=info.id)

        if not self._has_api_key():
            if c:
                c.print(f"\n  [{self._A}]\u26a0[/]  [{self._W}]{info.display_name}[/] [{self._M}]selected, but no API key for {self._display_provider}.[/]")
                c.print(f"     Run [{self._V}]/connect[/] to set one up.\n")
            else:
                print(f"\n  {info.display_name} selected, but no API key for {self._display_provider}.")
                print("  Run /connect to set one up.\n")
        else:
            if c:
                c.print(f"\n  [{self._M}]{old_display}[/] [{self._M}]\u2192[/] [{self._W} bold]{info.display_name}[/]\n")
            else:
                print(f"\n  {old_display} -> {info.display_name}\n")

    def _handle_status(self) -> None:
        """Show current configuration status."""
        has_key = self._has_api_key()
        key_status = "connected" if has_key else "not set \u2014 run /connect"
        sid = self._session_id or "(new session)"
        cwd = self._cwd or os.getcwd()

        c = self._rc()
        if c:
            _V, _G, _A, _L, _W, _M = self._V, self._G, self._A, self._L, self._W, self._M
            key_col = _G if has_key else _A

            c.print()
            c.print(f"  [bold {_V}]\u2501\u2501 Status[/]")
            c.print()

            def _row(label: str, value: str, style: str = _W) -> None:
                c.print(f"    [{_L}]{label:<13}[/] [{style}]{value}[/]")

            _row("Provider", self._display_provider)
            _row("Model", self._display_model)
            _row("API key", key_status, key_col)
            _row("Session", sid, _M)
            c.print()
            _row("Turns", str(self._turn_count))
            _row("Tokens", f"{self._total_tokens:,}")
            _row("Cost", f"${self._total_cost:.4f}", _G)
            c.print()
            _row("Directory", cwd, _M)
            _row("Permission", self._permission_mode)
            c.print()
            return

        print()
        print(f"  == Status")
        print()
        print(f"    Provider      {self._display_provider}")
        print(f"    Model         {self._display_model}")
        print(f"    API key       {key_status}")
        print(f"    Session       {sid}")
        print()
        print(f"    Turns         {self._turn_count}")
        print(f"    Tokens        {self._total_tokens:,}")
        print(f"    Cost          ${self._total_cost:.4f}")
        print()
        print(f"    Directory     {cwd}")
        print(f"    Permission    {self._permission_mode}")
        print()

    def _handle_cost(self) -> None:
        """Show token usage and cost for the current session."""
        c = self._rc()
        if self._turn_count == 0:
            if c:
                c.print(f"\n  [{self._M}]No usage yet. Start a conversation to see costs.[/]\n")
            else:
                print("\n  No usage yet. Start a conversation to see costs.\n")
            return

        if c:
            _V, _L, _W, _G = self._V, self._L, self._W, self._G
            c.print()
            c.print(f"  [bold {_V}]\u2501\u2501 Session cost[/]")
            c.print()
            c.print(f"    [{_L}]Turns[/]    [{_W}]{self._turn_count}[/]")
            c.print(f"    [{_L}]Tokens[/]   [{_W}]{self._total_tokens:,}[/]")
            c.print(f"    [{_L}]Cost[/]     [{_G} bold]${self._total_cost:.4f}[/]")
            c.print()
            return

        print()
        print(f"  == Session cost")
        print(f"    Turns    {self._turn_count}")
        print(f"    Tokens   {self._total_tokens:,}")
        print(f"    Cost     ${self._total_cost:.4f}")
        print()

    def _handle_compact(self) -> None:
        """Hint to the user about compaction."""
        c = self._rc()
        if c:
            _V, _M, _W = self._V, self._M, self._W
            c.print()
            c.print(f"  [{_M}]Context compaction happens automatically when the conversation[/]")
            c.print(f"  [{_M}]approaches the model's context limit. Harness summarizes earlier[/]")
            c.print(f"  [{_M}]messages to free up space while preserving key information.[/]")
            c.print()
            if self._turn_count > 0:
                c.print(f"  [{_W}]Current session:[/] [{_V}]{self._turn_count}[/] turns, [{_V}]{self._total_tokens:,}[/] tokens.")
            c.print(f"  [{_M}]To start fresh, use[/] [{_V}]/session new[/]")
            c.print()
            return

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
        c = self._rc()
        if not arg:
            sid = self._session_id or "(none \u2014 will be created on first prompt)"
            if c:
                c.print()
                c.print(f"  [bold {self._V}]Session:[/] [{self._M}]{sid}[/]")
                c.print(f"    [{self._V}]/session new[/]   [{self._M}]Start a fresh session[/]")
                c.print(f"    [{self._V}]/session <id>[/]  [{self._M}]Resume a previous session[/]")
                c.print()
            else:
                print(f"\n  Session: {sid}")
                print("  /session new     Start a fresh session")
                print("  /session <id>    Resume a previous session\n")
            return

        if arg == "new":
            self._session_id = None
            self._total_tokens = 0
            self._total_cost = 0.0
            self._turn_count = 0
            if c:
                c.print(f"\n  [{self._G}]\u2713[/] [{self._W}]New session started.[/] [{self._M}]Previous context cleared.[/]\n")
            else:
                print("\n  New session started. Previous context cleared.\n")
            return

        # Resume an existing session
        self._session_id = arg
        self._total_tokens = 0
        self._total_cost = 0.0
        self._turn_count = 0
        if c:
            c.print(f"\n  [{self._G}]\u2713[/] [{self._W}]Resuming session:[/] [{self._M}]{arg}[/]\n")
        else:
            print(f"\n  Resuming session: {arg}\n")

    def _handle_diff(self) -> None:
        """Show git diff of working directory."""
        cwd = self._cwd or os.getcwd()
        c = self._rc()
        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, cwd=cwd, timeout=10,
            )
            if result.returncode != 0:
                if c:
                    c.print(f"\n  [{self._A}]\u26a0[/] [{self._M}]Not a git repository, or git is not installed.[/]\n")
                else:
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
                    if c:
                        c.print(f"\n  [bold {self._V}]\u2501\u2501 Staged changes[/]")
                        c.print(f"[dim]{staged.stdout}[/dim]")
                    else:
                        print(f"\n  Staged changes:\n{staged.stdout}")
                else:
                    if c:
                        c.print(f"\n  [{self._M}]No uncommitted changes.[/]\n")
                    else:
                        print("\n  No uncommitted changes.\n")
                return

            # Show stat + abbreviated diff
            if c:
                c.print(f"\n  [bold {self._V}]\u2501\u2501 Uncommitted changes[/]")
                c.print(f"[dim]{stat}[/dim]\n")
            else:
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
                remaining = len(lines) - 60
                if c:
                    c.print(f"\n  [dim]\u2026 {remaining} more lines, run `git diff` to see all[/dim]")
                else:
                    print(f"\n  ... ({remaining} more lines, run `git diff` to see all)")
            print()

        except FileNotFoundError:
            if c:
                c.print(f"\n  [{self._R}]\u2717[/] [{self._M}]git is not installed.[/]\n")
            else:
                print("\n  git is not installed.\n")
        except subprocess.TimeoutExpired:
            if c:
                c.print(f"\n  [{self._A}]\u26a0[/] [{self._M}]git diff timed out.[/]\n")
            else:
                print("\n  git diff timed out.\n")

    def _handle_init(self) -> None:
        """Create a HARNESS.md project config file."""
        cwd = Path(self._cwd or os.getcwd())
        harness_md = cwd / "HARNESS.md"

        c = self._rc()
        if harness_md.exists():
            if c:
                c.print(f"\n  [{self._M}]HARNESS.md already exists at[/] [dim]{harness_md}[/dim]")
                c.print(f"  [{self._M}]Edit it to customize project instructions for the agent.[/]\n")
            else:
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
        if c:
            c.print(f"\n  [{self._G}]\u2713[/] [{self._W}]Created[/] [dim]{harness_md}[/dim]")
            c.print(f"  [{self._M}]Edit this file to give the agent context about your project.[/]")
            c.print(f"  [{self._M}]The agent reads it automatically at the start of every session.[/]\n")
        else:
            print(f"\n  Created {harness_md}")
            print("  Edit this file to give the agent context about your project.")
            print("  The agent reads it automatically at the start of every session.\n")

    def _handle_doctor(self) -> None:
        """Check setup and report issues."""
        issues: list[str] = []
        ok_items: list[str] = []

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
            issues.append("API key: not set \u2014 run /connect")

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

        c = self._rc()
        if c:
            _V, _G, _A, _M, _W = self._V, self._G, self._A, self._M, self._W
            c.print()
            c.print(f"  [bold {_V}]\u2501\u2501 Doctor[/]")
            c.print()
            for item in ok_items:
                c.print(f"    [{_G}]\u2713[/]  [{_W}]{item}[/]")
            for item in issues:
                c.print(f"    [{_A}]\u26a0[/]  [{_A}]{item}[/]")
            c.print()
            if not issues:
                c.print(f"  [{_G}]All checks passed.[/]")
            else:
                c.print(f"  [{_A}]{len(issues)} issue(s) found.[/]")
            c.print()
            return

        print()
        print("  == Doctor")
        print()
        for item in ok_items:
            print(f"    OK  {item}")
        for item in issues:
            print(f"    !!  {item}")
        print()
        if not issues:
            print("  All checks passed.")
        else:
            print(f"  {len(issues)} issue(s) found.")
        print()

    def _handle_permission(self, arg: str) -> None:
        """View or change permission mode."""
        modes = {
            "default": "Read tools auto-allowed, writes ask for approval",
            "accept_edits": "File edits auto-allowed, shell commands ask",
            "plan": "Read-only \u2014 nothing gets changed",
            "bypass": "Full auto-approve (for scripts/CI)",
        }

        c = self._rc()
        if not arg:
            if c:
                _V, _B, _M, _W = self._V, self._B, self._M, self._W
                c.print()
                c.print(f"  [bold {_V}]\u2501\u2501 Permission mode[/]")
                c.print()
                for mode, desc in modes.items():
                    active = mode == self._permission_mode
                    marker = f"[{_B}]\u25b8[/]" if active else " "
                    name_style = f"bold {_W}" if active else _M
                    c.print(f"    {marker} [{name_style}]{mode:<14}[/] [{_M}]{desc}[/]")
                c.print()
                c.print(f"  [dim]Usage:[/dim] [{_V}]/permission <mode>[/]")
                c.print()
            else:
                print(f"\n  == Permission mode")
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
            if c:
                c.print(f"  [{self._R}]\u2717[/] Unknown mode: [{self._W}]{arg}[/]. Options: [{self._M}]{', '.join(modes)}[/]")
            else:
                print(f"  Unknown mode: {arg}. Options: {', '.join(modes)}")
            return

        old = self._permission_mode
        self._permission_mode = arg
        if c:
            c.print(f"\n  [{self._M}]{old}[/] [{self._M}]\u2192[/] [{self._W} bold]{arg}[/]\n")
        else:
            print(f"\n  Permission: {old} -> {arg}\n")

    # -- Agent commands (/plan, /review, /team) --------------------------------

    async def _run_prompt_with_overrides(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        permission_mode: str | None = None,
    ) -> None:
        """Run a prompt through the engine with overrides, in a fresh session.

        Like ``_run_prompt`` but accepts overrides for system prompt, tools,
        and permission mode.  Uses ``session_id=None`` so it doesn't pollute
        the main conversation.  Token/cost tracking still feeds the REPL
        counters.
        """
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
                session_id=None,
                max_turns=self._max_turns,
                cwd=self._cwd,
                api_key=self._api_key,
                base_url=self._base_url,
                permission_mode=permission_mode or self._permission_mode,
                system_prompt=system_prompt,
                tools=tools,
                interactive=True,
                approval_callback=self._approval_callback,
            ):
                if self._cancelled:
                    print("\n[cancelled]")
                    break

                if isinstance(msg, Result):
                    self._total_tokens += getattr(msg, "total_tokens", 0) or 0
                    self._total_cost += getattr(msg, "cost", 0.0) or 0.0
                    self._turn_count += 1

                output_fn(msg)

        finally:
            signal.signal(signal.SIGINT, original_handler)

        print()

    async def _handle_plan(self, arg: str) -> None:
        """Run a read-only planning agent."""
        if not arg:
            c = self._rc()
            if c:
                _V, _M = self._V, self._M
                c.print()
                c.print(f"  [bold {_V}]\u2501\u2501 /plan[/]  [{_M}]<task description>[/]")
                c.print()
                c.print(f"  [{_M}]Runs a read-only agent that explores the codebase and[/]")
                c.print(f"  [{_M}]produces a structured implementation plan.[/]")
                c.print()
                c.print(f"    [{_M}]\u25b8[/] [dim]/plan refactor the auth module to use JWT[/dim]")
                c.print(f"    [{_M}]\u25b8[/] [dim]/plan add pagination to the /users endpoint[/dim]")
                c.print(f"    [{_M}]\u25b8[/] [dim]/plan migrate from SQLite to PostgreSQL[/dim]")
                c.print()
            else:
                print()
                print("  Usage: /plan <task description>")
                print()
                print("  Examples:")
                print('    > /plan refactor the auth module to use JWT')
                print('    > /plan add pagination to the /users endpoint')
                print('    > /plan migrate from SQLite to PostgreSQL')
                print()
            return

        if not self._has_api_key():
            self._print_no_key_guide()
            return

        system_prompt = (
            "You are a planning agent. Analyze the codebase and produce a detailed "
            "implementation plan. Structure your response as:\n\n"
            "## Analysis\nWhat you found in the codebase relevant to the task.\n\n"
            "## Proposed Changes\nFile-by-file list of what needs to change and why.\n\n"
            "## Sequence\nThe order in which changes should be made.\n\n"
            "## Risks\nPotential issues, edge cases, or breaking changes to watch for.\n\n"
            "## Testing\nHow to verify the changes work correctly.\n\n"
            "Do NOT make any changes — only read and analyze."
        )

        prompt = f"Plan the following task:\n\n{arg}"
        await self._run_prompt_with_overrides(
            prompt,
            system_prompt=system_prompt,
            tools=["Read", "Glob", "Grep"],
            permission_mode="plan",
        )

    async def _handle_review(self, arg: str) -> None:
        """Review uncommitted changes or a specific file/path."""
        if not self._has_api_key():
            self._print_no_key_guide()
            return

        review_system_prompt = (
            "You are a code review agent. Provide a structured review with:\n\n"
            "## Summary\nBrief overview of what the code does.\n\n"
            "## Issues Found\nFor each issue:\n"
            "- **Severity**: critical / warning / info\n"
            "- **Location**: file path and line\n"
            "- **Description**: what the issue is\n"
            "- **Suggestion**: how to fix it\n\n"
            "## Strengths\nWhat the code does well.\n\n"
            "## Suggestions\nGeneral improvements.\n\n"
            "Do NOT make any changes — only read and analyze."
        )

        if arg:
            # Review a specific file or path
            prompt = f"Review the following file or path: {arg}"
        else:
            # Gather git diff for uncommitted changes
            cwd = self._cwd or os.getcwd()
            diff_text = ""
            try:
                unstaged = subprocess.run(
                    ["git", "diff"],
                    capture_output=True, text=True, cwd=cwd, timeout=10,
                )
                staged = subprocess.run(
                    ["git", "diff", "--cached"],
                    capture_output=True, text=True, cwd=cwd, timeout=10,
                )
                diff_text = ""
                if staged.stdout.strip():
                    diff_text += f"=== Staged changes ===\n{staged.stdout}\n"
                if unstaged.stdout.strip():
                    diff_text += f"=== Unstaged changes ===\n{unstaged.stdout}\n"
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            if not diff_text:
                c = self._rc()
                if c:
                    c.print(f"\n  [{self._M}]No uncommitted changes to review.[/]")
                    c.print(f"  [{self._M}]Usage:[/] [{self._V}]/review[/] [{self._M}][file_or_path][/]\n")
                else:
                    print("\n  No uncommitted changes to review.")
                    print("  Usage: /review [file_or_path]\n")
                return

            prompt = (
                "Review the following uncommitted git changes:\n\n"
                f"```diff\n{diff_text}```"
            )

        await self._run_prompt_with_overrides(
            prompt,
            system_prompt=review_system_prompt,
            tools=["Read", "Glob", "Grep"],
            permission_mode="plan",
        )

    async def _handle_team(self, arg: str) -> None:
        """Dynamically decompose a task and run sub-agents in parallel.

        The LLM decides how many agents to spawn, what type each is, and
        what each should do — there is no fixed roster.
        """
        if not arg:
            c = self._rc()
            if c:
                _V, _B, _M, _W = self._V, self._B, self._M, self._W
                c.print()
                c.print(f"  [bold {_V}]\u2501\u2501 /team[/]  [{_M}]<task description>[/]")
                c.print()
                c.print(f"  [{_M}]The LLM breaks the task into subtasks and runs them[/]")
                c.print(f"  [{_M}]in parallel. Agent count and roles are chosen dynamically.[/]")
                c.print()
                c.print(f"    [{_B}]explore[/]   [{_M}]find relevant code/files[/]")
                c.print(f"    [{_B}]plan[/]      [{_M}]design an implementation approach[/]")
                c.print(f"    [{_B}]review[/]    [{_M}]assess code quality[/]")
                c.print(f"    [{_B}]general[/]   [{_M}]read/write/run commands[/]")
                c.print()
                c.print(f"    [{_M}]\u25b8[/] [dim]/team investigate API performance bottlenecks[/dim]")
                c.print(f"    [{_M}]\u25b8[/] [dim]/team add auth middleware and write tests for it[/dim]")
                c.print(f"    [{_M}]\u25b8[/] [dim]/team refactor the database layer to use async[/dim]")
                c.print()
            else:
                print()
                print("  Usage: /team <task description>")
                print()
                print("  The LLM breaks the task into subtasks and runs them")
                print("  in parallel. Agent count and roles are chosen dynamically.")
                print()
                print("    explore   find relevant code/files")
                print("    plan      design an implementation approach")
                print("    review    assess code quality")
                print("    general   read/write/run commands")
                print()
                print("    > /team investigate API performance bottlenecks")
                print("    > /team add auth middleware and write tests for it")
                print("    > /team refactor the database layer to use async")
                print()
            return

        if not self._has_api_key():
            self._print_no_key_guide()
            return

        import json as _json

        from harness.agents.manager import AgentManager
        from harness.core.config import resolve_api_key
        from harness.core.engine import _create_tools
        from harness.providers.registry import create_provider, resolve_model
        from harness.types.providers import ChatMessage, StreamEvent

        # --- resolve provider -------------------------------------------------
        model_id = self._model or DEFAULT_MODELS.get(self._provider, "unknown")
        try:
            info = resolve_model(model_id)
            model_id = info.id
        except KeyError:
            pass

        api_key = resolve_api_key(self._provider, self._api_key)
        provider = create_provider(model_id, api_key=api_key, base_url=self._base_url)

        # --- step 1: ask the LLM to decompose the task -----------------------
        c_team = self._rc()
        if c_team:
            c_team.print(f"\n  [{self._M}]Decomposing task into subtasks \u2026[/]")
        else:
            print("\n  Decomposing task into subtasks ...")

        decompose_system = (
            "You are a task decomposition engine. Given a task, break it into "
            "2-5 independent subtasks that can be executed in parallel by "
            "separate agents.\n\n"
            "Available agent types:\n"
            "  explore — find relevant files and code (read-only)\n"
            "  plan    — design implementation approach (read-only)\n"
            "  review  — assess code quality and find issues (read-only)\n"
            "  general — full tool access, can read/write/run commands\n\n"
            "Return ONLY a JSON array (no markdown fences, no commentary):\n"
            '[{"agent_type":"explore","title":"short title","prompt":"detailed instructions"}]\n\n'
            "Choose the number and types of agents based on what the task "
            "actually needs. Not every task needs explore+plan+review — "
            "use your judgment."
        )
        decompose_msg = ChatMessage(role="user", content=arg)

        raw_response = ""
        async for event in provider.chat_completion_stream(
            messages=[decompose_msg],
            tools=[],
            system=decompose_system,
            max_tokens=2048,
        ):
            event: StreamEvent
            if event.type == "text_delta" and event.text:
                raw_response += event.text

        # Parse the JSON subtask list
        raw_response = raw_response.strip()
        # Strip markdown fences if the model wrapped them
        if raw_response.startswith("```"):
            raw_response = raw_response.split("\n", 1)[-1]
        if raw_response.endswith("```"):
            raw_response = raw_response.rsplit("```", 1)[0]
        raw_response = raw_response.strip()

        try:
            subtasks = _json.loads(raw_response)
        except _json.JSONDecodeError:
            if c_team:
                c_team.print(f"  [{self._A}]Could not parse decomposition. Running as single agent.[/]\n")
            else:
                print("  Failed to parse task decomposition. Running as single agent.\n")
            await self._run_prompt_with_overrides(arg)
            return

        if not isinstance(subtasks, list) or not subtasks:
            if c_team:
                c_team.print(f"  [{self._A}]No subtasks generated. Running as single agent.[/]\n")
            else:
                print("  No subtasks generated. Running as single agent.\n")
            await self._run_prompt_with_overrides(arg)
            return

        # Validate and normalise entries
        valid_types = {"explore", "plan", "review", "general"}
        validated: list[dict[str, str]] = []
        for st in subtasks:
            if not isinstance(st, dict):
                continue
            agent_type = st.get("agent_type", "general")
            if agent_type not in valid_types:
                agent_type = "general"
            prompt = st.get("prompt", "")
            title = st.get("title", prompt[:50])
            if prompt:
                validated.append({"agent_type": agent_type, "title": title, "prompt": prompt})

        if not validated:
            if c_team:
                c_team.print(f"  [{self._A}]No valid subtasks. Running as single agent.[/]\n")
            else:
                print("  No valid subtasks. Running as single agent.\n")
            await self._run_prompt_with_overrides(arg)
            return

        # --- step 2: show decomposition & spawn agents in parallel ------------
        n = len(validated)
        if c_team:
            c_team.print(f"  [{self._W}]Spawning {n} agent{'s' if n != 1 else ''}:[/]\n")
            for i, st in enumerate(validated, 1):
                c_team.print(f"    [{self._B}]{i}.[/] [{self._V}]{st['agent_type']:<8}[/] [{self._M}]{st['title']}[/]")
            c_team.print()
        else:
            print(f"  Spawning {n} agent{'s' if n != 1 else ''}:\n")
            for i, st in enumerate(validated, 1):
                print(f"    {i}. [{st['agent_type']}] {st['title']}")
            print()

        # Build tools — include Write/Edit/Bash for general agents
        all_tool_names = ["Read", "Glob", "Grep", "Write", "Edit", "Bash"]
        tools = _create_tools(all_tool_names)
        cwd = self._cwd or os.getcwd()

        mgr = AgentManager(provider=provider, tools=tools, cwd=cwd)

        task_tuples = [(st["agent_type"], st["prompt"]) for st in validated]
        try:
            results = await mgr.spawn_parallel(task_tuples)
        except Exception as e:
            if c_team:
                c_team.print(f"  [{self._R}]\u2717 Agent team failed:[/] [{self._M}]{e}[/]\n")
            else:
                print(f"  Agent team failed: {e}\n")
            return

        # --- step 3: display results ------------------------------------------
        if c_team:
            try:
                from rich.markdown import Markdown
                from rich.panel import Panel

                for st, text in zip(validated, results):
                    title = f"[bold {self._W}]{st['title']}[/]  [{self._M}]{st['agent_type']}[/]"
                    c_team.print(Panel(
                        Markdown(text),
                        title=title,
                        border_style=self._V,
                        expand=True,
                        padding=(1, 2),
                    ))
                c_team.print()
                return
            except ImportError:
                pass

        # Plain text fallback
        for st, text in zip(validated, results):
            label = f"{st['title']}  ({st['agent_type']})"
            print(f"\n  == {label} {'=' * max(1, 56 - len(label))}")
            for line in text.splitlines():
                print(f"  {line}")
        print()

    # -- Connect flow ----------------------------------------------------------

    PROVIDERS = {
        "1": "anthropic",
        "2": "openai",
        "3": "google",
    }

    def _handle_connect(self) -> None:
        """Interactive flow to set up an API key."""
        c = self._rc()
        _V = self._V
        _M = self._M
        _B = self._B

        if c:
            c.print()
            c.print(f"  [bold {_V}]\u2501\u2501 Connect[/]")
            c.print()
            c.print(f"    [{_B}]1[/]  Anthropic   [dim]console.anthropic.com/settings/keys[/dim]")
            c.print(f"    [{_B}]2[/]  OpenAI      [dim]platform.openai.com/api-keys[/dim]")
            c.print(f"    [{_B}]3[/]  Google      [dim]aistudio.google.com/apikey[/dim]")
            c.print()
        else:
            print("\n  == Connect")
            print()
            print("    1  Anthropic   console.anthropic.com/settings/keys")
            print("    2  OpenAI      platform.openai.com/api-keys")
            print("    3  Google      aistudio.google.com/apikey")
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

        from harness.core.config import save_api_key, save_defaults

        config_path = save_api_key(provider, api_key)
        save_defaults(provider=provider)

        self._provider = provider
        self._api_key = api_key

        if c:
            _G, _W = self._G, self._W
            c.print()
            c.print(f"  [{_G}]\u2713[/] [{_W}]Connected to {PROVIDER_DISPLAY.get(provider, provider)}[/]")
            c.print(f"    [{_M}]Model:[/]  [{_W}]{self._display_model}[/]")
            c.print(f"    [{_M}]Saved:[/]  [dim]{config_path}[/dim]")
            c.print(f"    [{_M}]Provider will be remembered for next launch.[/]")
            c.print()
        else:
            print(f"\n  Connected to {PROVIDER_DISPLAY.get(provider, provider)}.")
            print(f"    Model:  {self._display_model}")
            print(f"    Saved:  {config_path}")
            print("    Provider will be remembered for next launch.")
            print()

    # -- Banner & guides -------------------------------------------------------

    def _print_no_key_guide(self) -> None:
        """Print a friendly guide when no API key is configured."""
        c = self._rc()
        if c:
            _V, _A, _B, _M, _W = self._V, self._A, self._B, self._M, self._W
            c.print()
            c.print(f"  [{_A}]\u26a0  No API key found.[/] [{_M}]Let's fix that in 30 seconds:[/]")
            c.print()
            c.print(f"    [{_W}]1.[/]  Type [{_V}]/connect[/] [{_M}]right here[/]")
            c.print(f"    [{_W}]2.[/]  Run  [{_V}]harness connect[/] [{_M}]from another terminal[/]")
            c.print(f"    [{_W}]3.[/]  [{_M}]Set an environment variable:[/]")
            c.print(f"        [dim]export ANTHROPIC_API_KEY=sk-ant-...[/dim]")
            c.print()
            c.print(f"  [{_M}]Need a key?[/]")
            c.print(f"    [{_B}]Anthropic[/]  [dim]console.anthropic.com/settings/keys[/dim]")
            c.print(f"    [{_B}]OpenAI[/]     [dim]platform.openai.com/api-keys[/dim]")
            c.print(f"    [{_B}]Google[/]     [dim]aistudio.google.com/apikey[/dim]")
            c.print()
            return

        print()
        print("  !! No API key found. Let's fix that in 30 seconds:")
        print()
        print("    1.  Type /connect right here")
        print("    2.  Run  `harness connect` from another terminal")
        print("    3.  Set an environment variable:")
        print("        export ANTHROPIC_API_KEY=sk-ant-...")
        print()
        print("  Need a key?")
        print("    Anthropic  console.anthropic.com/settings/keys")
        print("    OpenAI     platform.openai.com/api-keys")
        print("    Google     aistudio.google.com/apikey")
        print()

    def _print_banner(self) -> None:
        """Print the welcome banner with current model info."""
        model = self._display_model
        provider = self._display_provider
        cwd = Path(self._cwd or os.getcwd()).name or "~"

        c = self._rc()
        if c:
            _V, _M, _B = self._V, self._M, self._B
            c.print()
            c.print(f"  [bold {_V}]\u25c8 Harness[/]", highlight=False)
            c.print(f"  [{_M}]{provider} \u2215 {model}  \u2502  {cwd}[/]")
            c.print()
            c.print(f"  [{_M}]Type what you need, or press[/] [{_V}]/[/] [{_M}]for commands.[/]")
            c.print()
            return

        print()
        print("  * Harness")
        print(f"  {provider} / {model}  |  {cwd}")
        print()
        print("  Type what you need, or press / for commands.")
        print()
