"""CLI subcommands for CI/CD integration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click


@click.group()
def ci_cmd() -> None:
    """CI/CD integration commands."""
    pass


@ci_cmd.command("run")
@click.option("--mode", default=None, help="CI mode (review, issue, general)")
@click.option("--prompt", default=None, help="Custom prompt")
@click.option("--provider", "-p", default="anthropic", help="LLM provider")
@click.option("--model", "-m", default=None, help="Model ID")
@click.option("--sandbox", default="process", help="Sandbox mode")
@click.option("--check-name", default="harness-agent", help="GitHub check run name")
def ci_run(
    mode: str | None,
    prompt: str | None,
    provider: str,
    model: str | None,
    sandbox: str,
    check_name: str,
) -> None:
    """Run the CI agent (auto-detects mode from GitHub event)."""
    from harness.ci.runner import run_ci

    result = asyncio.run(run_ci(
        mode=mode,
        prompt=prompt,
        provider=provider,
        model=model,
        sandbox=sandbox,
        check_name=check_name,
    ))

    status = result.get("status", "unknown")
    if status == "success":
        click.echo(f"CI completed successfully. Turns: {result.get('turns', 0)}")
    else:
        click.echo(f"CI failed: {result.get('error', 'unknown error')}", err=True)
        raise SystemExit(1)


@ci_cmd.command("review")
@click.argument("pr_number", type=int)
@click.option("--provider", "-p", default="anthropic", help="LLM provider")
@click.option("--model", "-m", default=None, help="Model ID")
def ci_review(pr_number: int, provider: str, model: str | None) -> None:
    """Review a pull request."""
    from harness.ci.runner import run_ci

    prompt = f"Review pull request #{pr_number}. Provide thorough code review with actionable feedback."
    result = asyncio.run(run_ci(
        mode="review",
        prompt=prompt,
        provider=provider,
        model=model,
    ))

    summary = result.get("summary", "")
    if summary:
        click.echo(summary)


@ci_cmd.command("init")
def ci_init() -> None:
    """Create a .harness/ci.yml template."""
    from harness.ci.config import generate_ci_template

    ci_dir = Path.cwd() / ".harness"
    ci_dir.mkdir(parents=True, exist_ok=True)
    ci_path = ci_dir / "ci.yml"

    if ci_path.exists():
        click.echo(f"CI config already exists at {ci_path}")
        return

    ci_path.write_text(generate_ci_template())
    click.echo(f"Created CI config at {ci_path}")
