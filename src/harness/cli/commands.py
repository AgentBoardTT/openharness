"""CLI subcommands for Harness (config, models, sessions, connect)."""

from __future__ import annotations

import getpass

import click


@click.group()
def config_cmd() -> None:
    """Manage Harness configuration."""


@config_cmd.command("list")
def config_list() -> None:
    """Show current configuration."""
    from harness.core.config import load_env_config, load_toml_config

    click.echo("Environment:")
    env = load_env_config()
    if env:
        for k, v in sorted(env.items()):
            display = v if "key" not in k.lower() else v[:8] + "..."
            click.echo(f"  {k}: {display}")
    else:
        click.echo("  (no environment variables set)")

    click.echo("\nTOML config:")
    toml = load_toml_config()
    if toml:
        for k, v in sorted(toml.items()):
            click.echo(f"  {k}: {v}")
    else:
        click.echo("  (no config.toml found)")


@click.group()
def models_cmd() -> None:
    """Manage models."""


@models_cmd.command("list")
@click.option("--provider", "-p", default=None, help="Filter by provider")
def models_list(provider: str | None) -> None:
    """List available models."""
    from harness.providers.registry import ALIASES, MODELS

    header = (
        f"{'Model ID':<30} {'Provider':<12} {'Context':<10} "
        f"{'$/M in':<8} {'$/M out':<8} {'Aliases'}"
    )
    click.echo(header)
    click.echo("-" * 95)

    for model_id, info in sorted(MODELS.items()):
        if provider and info.provider != provider:
            continue
        ctx = f"{info.context_window // 1000}K"
        aliases = ", ".join(info.aliases) if info.aliases else ""
        click.echo(
            f"{model_id:<30} {info.provider:<12} {ctx:<10} "
            f"${info.input_cost_per_mtok:<7.2f} "
            f"${info.output_cost_per_mtok:<7.2f} {aliases}"
        )

    click.echo(f"\n{len(MODELS)} models, {len(ALIASES)} aliases")


@models_cmd.command("info")
@click.argument("name")
def models_info(name: str) -> None:
    """Show details for a specific model."""
    from harness.providers.registry import resolve_model

    try:
        info = resolve_model(name)
    except KeyError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    click.echo(f"Model:          {info.id}")
    click.echo(f"Display Name:   {info.display_name}")
    click.echo(f"Provider:       {info.provider}")
    click.echo(f"Context Window: {info.context_window:,} tokens")
    click.echo(f"Max Output:     {info.max_output_tokens:,} tokens")
    click.echo(f"Tools:          {'Yes' if info.supports_tools else 'No'}")
    click.echo(f"Streaming:      {'Yes' if info.supports_streaming else 'No'}")
    click.echo(f"Vision:         {'Yes' if info.supports_vision else 'No'}")
    click.echo(f"Input Cost:     ${info.input_cost_per_mtok:.2f}/M tokens")
    click.echo(f"Output Cost:    ${info.output_cost_per_mtok:.2f}/M tokens")
    if info.aliases:
        click.echo(f"Aliases:        {', '.join(info.aliases)}")


@click.group()
def sessions_cmd() -> None:
    """Manage sessions."""


@sessions_cmd.command("list")
@click.option("--limit", "-n", default=20, help="Max sessions to show")
def sessions_list(limit: int) -> None:
    """List recent sessions."""
    from harness.core.session import list_sessions

    sessions = list_sessions()[:limit]
    if not sessions:
        click.echo("No sessions found.")
        return

    click.echo(f"{'Session ID':<14} {'Provider':<12} {'Model':<25} {'Turns':<7} {'Updated'}")
    click.echo("-" * 80)
    for s in sessions:
        updated = s.updated_at.strftime("%Y-%m-%d %H:%M")
        click.echo(
            f"{s.session_id:<14} {s.provider:<12} "
            f"{s.model:<25} {s.turns:<7} {updated}"
        )


@sessions_cmd.command("show")
@click.argument("session_id")
def sessions_show(session_id: str) -> None:
    """Show details of a session."""
    from harness.core.session import Session

    try:
        s = Session(session_id=session_id)
    except Exception as e:
        click.echo(f"Error loading session: {e}", err=True)
        raise SystemExit(1)

    info = s.get_info()
    click.echo(f"Session:   {info.session_id}")
    click.echo(f"Provider:  {info.provider}")
    click.echo(f"Model:     {info.model}")
    click.echo(f"CWD:       {info.cwd}")
    click.echo(f"Turns:     {info.turns}")
    click.echo(f"Tokens:    {info.total_tokens:,}")
    click.echo(f"Cost:      ${info.total_cost:.4f}")
    click.echo(f"Created:   {info.created_at}")
    click.echo(f"Updated:   {info.updated_at}")

    click.echo(f"\nMessages ({len(s.messages)}):")
    for i, msg in enumerate(s.messages):
        role = msg.role
        if isinstance(msg.content, str):
            preview = msg.content[:100]
            if len(msg.content) > 100:
                preview += "..."
        else:
            preview = f"[{len(msg.content)} content blocks]"
        click.echo(f"  {i + 1}. [{role}] {preview}")


# --- eval subcommand (delegates to harness.eval.__main__) ---

@click.group()
def eval_cmd() -> None:
    """Run evaluation benchmarks."""


@eval_cmd.command("swe-bench")
@click.option("--split", default="lite", type=click.Choice(["lite", "verified", "full"]))
@click.option("--provider", "-p", default="anthropic")
@click.option("--model", "-m", default=None)
@click.option("--max-tasks", default=None, type=int)
@click.option("--output", "-o", default=None, help="Output report path")
def eval_swebench(
    split: str, provider: str, model: str | None, max_tasks: int | None, output: str | None,
) -> None:
    """Run SWE-bench evaluation."""
    import asyncio

    from harness.eval.report import ReportGenerator
    from harness.eval.swe_bench import SWEBenchRunner
    from harness.eval.types import EvalConfig

    config = EvalConfig(provider=provider, model=model, split=split, max_tasks=max_tasks)
    runner = SWEBenchRunner(config)

    async def _run() -> None:
        results = await runner.run()
        report = ReportGenerator().generate(results)
        if output:
            with open(output, "w") as f:
                f.write(report)
            click.echo(f"Report saved to {output}")
        else:
            click.echo(report)

    asyncio.run(_run())


@eval_cmd.command("harness-bench")
@click.option("--provider", "-p", default="anthropic")
@click.option("--model", "-m", default=None)
@click.option("--max-tasks", default=None, type=int)
@click.option("--output", "-o", default=None, help="Output report path")
def eval_harness_bench(
    provider: str, model: str | None, max_tasks: int | None, output: str | None,
) -> None:
    """Run Harness-Bench evaluation."""
    import asyncio

    from harness.eval.harness_bench import HarnessBenchRunner
    from harness.eval.report import ReportGenerator
    from harness.eval.types import EvalConfig

    config = EvalConfig(provider=provider, model=model, max_tasks=max_tasks)
    runner = HarnessBenchRunner(config)

    async def _run() -> None:
        results = await runner.run()
        report = ReportGenerator().generate(results)
        if output:
            with open(output, "w") as f:
                f.write(report)
            click.echo(f"Report saved to {output}")
        else:
            click.echo(report)

    asyncio.run(_run())


@eval_cmd.command("list")
def eval_list() -> None:
    """List available benchmarks."""
    click.echo("Available benchmarks:")
    click.echo("  swe-bench      SWE-bench (lite/verified/full)")
    click.echo("  harness-bench  Custom harness capability benchmark")


# --- connect subcommand ---

PROVIDER_CHOICES = {
    "1": "anthropic",
    "2": "openai",
    "3": "google",
}


@click.command("connect")
@click.option("--provider", "-p", default=None, help="Provider name (anthropic, openai, google)")
@click.option("--api-key", default=None, help="API key")
def connect_cmd(provider: str | None, api_key: str | None) -> None:
    """Set up API key for a provider.

    \b
    Interactive:      harness connect
    Non-interactive:  harness connect --provider anthropic --api-key sk-...
    """
    from harness.core.config import save_api_key

    if provider and api_key:
        # Non-interactive mode
        provider = provider.lower()
        if provider not in ("anthropic", "openai", "google"):
            click.echo(f"Unknown provider: {provider}", err=True)
            raise SystemExit(1)
        path = save_api_key(provider, api_key)
        click.echo(f"Connected to {provider}. Your key is saved to {path}")
        return

    # Interactive mode
    click.echo("\nSelect a provider:")
    click.echo("  (1) Anthropic")
    click.echo("  (2) OpenAI")
    click.echo("  (3) Google")
    click.echo()

    choice = click.prompt("Enter choice", default="1").strip()
    provider = PROVIDER_CHOICES.get(choice, choice.lower())
    if provider not in ("anthropic", "openai", "google"):
        click.echo(f"Unknown provider: {choice}", err=True)
        raise SystemExit(1)

    if not api_key:
        api_key = getpass.getpass(f"API key for {provider}: ").strip()
    if not api_key:
        click.echo("No key entered. Cancelled.")
        return

    path = save_api_key(provider, api_key)
    click.echo(f"\nConnected to {provider}. Your key is saved to {path}")
