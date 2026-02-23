#!/usr/bin/env python3
"""Generate terminal screenshots as SVG files using Rich Console.

Runs offline — no API key or network access needed.
Produces pixel-perfect terminal renderings for the README.

Usage:
    python docs/generate_screenshots.py
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

OUTPUT_DIR = Path(__file__).parent / "screenshots"

# Palette colours (must match repl.py)
V = "#a78bfa"  # violet
B = "#60a5fa"  # blue
G = "#34d399"  # green
A = "#fbbf24"  # amber
M = "#7c7c8a"  # muted
L = "#94a3b8"  # slate
W = "#e2e8f0"  # bright


def _save(console: Console, name: str) -> None:
    """Export the console recording to an SVG file."""
    path = OUTPUT_DIR / name
    svg = console.export_svg(title="Harness", clear=True)
    path.write_text(svg)
    print(f"  wrote {path}")


def generate_banner() -> None:
    """Generate the REPL banner screenshot."""
    c = Console(record=True, width=72)
    c.print()
    c.print(f"  [bold {V}]\u25c8 Harness[/]  [dim]v0.5.0[/dim]", highlight=False)
    c.print(f"  [{M}]Anthropic \u2215 Claude Sonnet 4.6  \u2502  myproject[/]")
    c.print()
    c.print(f"  [{M}]Type what you need, or press[/] [{V}]/[/] [{M}]for commands.[/]")
    c.print()
    _save(c, "banner.svg")


def generate_palette() -> None:
    """Generate the interactive command palette screenshot."""
    c = Console(record=True, width=72)
    c.print()
    c.print(f"  [bold {V}]\u25c8 Harness[/]  [dim]v0.5.0[/dim]", highlight=False)
    c.print(f"  [{M}]Anthropic \u2215 Claude Sonnet 4.6  \u2502  myproject[/]")
    c.print()
    c.print(f"  [{W}]sonnet > [/][{V}]/[/]")
    c.print()

    # Simulated palette dropdown
    commands = [
        ("/help", "Show available commands and tips"),
        ("/connect", "Set up or change your API key"),
        ("/model", "Switch model (e.g. /model gpt-5.2)"),
        ("/models", "List available models"),
        ("/plan", "Plan implementation with a read-only agent"),
        ("/review", "Review code changes or a specific file"),
        ("/team", "Decompose a task and run agents in parallel"),
        ("/status", "Show provider, model, session, and cost"),
        ("/cost", "Show token usage and cost for this session"),
        ("/compact", "Summarize conversation to free up context"),
    ]
    for i, (name, desc) in enumerate(commands):
        if i == 0:
            c.print(f"    [bold {V}]\u25b8 {name:<14}[/] [{M}]{desc}[/]")
        else:
            c.print(f"      [{V}]{name:<14}[/] [{M}]{desc}[/]")
    c.print(f"      [{M}]\u2026 6 more[/]")
    c.print()
    _save(c, "palette.svg")


def generate_agent_run() -> None:
    """Generate a simulated agent execution screenshot."""
    c = Console(record=True, width=80)
    c.print()
    c.print(f"  [{W}]sonnet > [/][{W}]Build a tic-tac-toe game in Python[/]")
    c.print()

    # Simulated tool calls
    c.print(f"  [{V}]\u25b8 Write[/] [{M}]tictactoe.py[/]")
    c.print(f"    [{G}]\u2713[/] [{M}]Created tictactoe.py (87 lines)[/]")
    c.print()
    c.print(f"  [{V}]\u25b8 Bash[/]  [{M}]python tictactoe.py --test[/]")
    c.print(f"    [{G}]\u2713[/] [{M}]All 9 tests passed[/]")
    c.print()

    # Simulated response
    c.print(
        f"  [{W}]Created a complete tic-tac-toe game with:[/]"
    )
    c.print(f"    [{M}]\u2022 3\u00d73 board with row/column input[/]")
    c.print(f"    [{M}]\u2022 Win detection (rows, columns, diagonals)[/]")
    c.print(f"    [{M}]\u2022 Draw detection[/]")
    c.print(f"    [{M}]\u2022 Input validation and error handling[/]")
    c.print()
    c.print(f"  [{M}]Run it with:[/] [{V}]python tictactoe.py[/]")
    c.print()
    c.print(f"  [{M}]\u2500\u2500 2 tool calls \u2502 1,247 tokens \u2502 $0.0041 \u2502 4.2s[/]")
    c.print()
    _save(c, "agent-run.svg")


def generate_status() -> None:
    """Generate the /status command output screenshot."""
    c = Console(record=True, width=72)
    c.print()
    c.print(f"  [{W}]sonnet > [/][{V}]/status[/]")
    c.print()
    c.print(f"  [bold {V}]\u2501\u2501 Status[/]")
    c.print()
    c.print(f"    [{L}]{'Provider':<13}[/] [{W}]Anthropic[/]")
    c.print(f"    [{L}]{'Model':<13}[/] [{W}]Claude Sonnet 4.6[/]")
    c.print(f"    [{L}]{'API key':<13}[/] [{G}]connected[/]")
    c.print(f"    [{L}]{'Session':<13}[/] [{M}]a1b2c3d4[/]")
    c.print()
    c.print(f"    [{L}]{'Turns':<13}[/] [{W}]12[/]")
    c.print(f"    [{L}]{'Tokens':<13}[/] [{W}]24,531[/]")
    c.print(f"    [{L}]{'Cost':<13}[/] [{G}]$0.0847[/]")
    c.print()
    c.print(f"    [{L}]{'Directory':<13}[/] [{M}]/home/user/myproject[/]")
    c.print(f"    [{L}]{'Permission':<13}[/] [{W}]default[/]")
    c.print()
    _save(c, "status.svg")


def generate_models() -> None:
    """Generate the /models command output screenshot."""
    c = Console(record=True, width=72)
    c.print()
    c.print(f"  [{W}]sonnet > [/][{V}]/models[/]")
    c.print()
    c.print(f"  [bold {V}]\u2501\u2501 Available models[/]  [dim]use /model <name> to switch[/dim]")
    c.print()
    c.print(f"    [{B}]Anthropic[/]  [{W}]sonnet[/] [dim](default)[/dim][{M}],[/] [{W}]opus[/][{M}],[/] [{W}]haiku[/]")
    c.print(f"    [{B}]OpenAI[/]     [{W}]gpt-5.2[/][{M}],[/] [{W}]gpt-4o[/][{M}],[/] [{W}]gpt-4.1[/][{M}],[/] [{W}]o3[/]")
    c.print(f"    [{B}]Google[/]     [{W}]gemini-2.5-pro[/][{M}],[/] [{W}]gemini-2.5-flash[/][{M}],[/] [{W}]gemini-2.0-flash[/]")
    c.print(f"    [{B}]Ollama[/]     [{W}]llama3.3[/][{M}],[/] [{W}]mistral[/][{M}],[/] [{W}]qwen[/][{M}],[/] [{W}]phi[/]  [dim]local, no key[/dim]")
    c.print()
    c.print(f"  [dim]Run [/dim][{V}]harness models list[/][dim] for the full catalogue (50+ models).[/dim]")
    c.print()
    _save(c, "models.svg")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating screenshots to {OUTPUT_DIR}/\n")
    generate_banner()
    generate_palette()
    generate_agent_run()
    generate_status()
    generate_models()
    print(f"\nDone. {len(list(OUTPUT_DIR.glob('*.svg')))} SVGs generated.")


if __name__ == "__main__":
    main()
