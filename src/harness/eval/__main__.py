"""CLI entry point for evaluation: python -m harness.eval"""

from __future__ import annotations

import asyncio

import click

from harness.eval.types import EvalConfig


@click.group()
def eval_cli() -> None:
    """Harness evaluation framework."""


@eval_cli.command("swe-bench")
@click.option("--split", default="lite", type=click.Choice(["lite", "verified", "full"]))
@click.option("--provider", "-p", default="anthropic")
@click.option("--model", "-m", default=None)
@click.option("--max-tasks", default=None, type=int)
@click.option("--max-turns", default=100, type=int)
@click.option("--output", "-o", default=None, help="Output report path")
def run_swebench(
    split: str,
    provider: str,
    model: str | None,
    max_tasks: int | None,
    max_turns: int,
    output: str | None,
) -> None:
    """Run SWE-bench evaluation."""
    from harness.eval.report import ReportGenerator
    from harness.eval.swe_bench import SWEBenchRunner

    config = EvalConfig(
        provider=provider,
        model=model,
        benchmark="swe-bench",
        split=split,
        max_tasks=max_tasks,
        max_turns=max_turns,
    )

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


@eval_cli.command("harness-bench")
@click.option("--provider", "-p", default="anthropic")
@click.option("--model", "-m", default=None)
@click.option("--max-tasks", default=None, type=int)
@click.option("--max-turns", default=50, type=int)
@click.option("--output", "-o", default=None, help="Output report path")
def run_harness_bench(
    provider: str,
    model: str | None,
    max_tasks: int | None,
    max_turns: int,
    output: str | None,
) -> None:
    """Run Harness-Bench custom evaluation."""
    from harness.eval.harness_bench import HarnessBenchRunner
    from harness.eval.report import ReportGenerator

    config = EvalConfig(
        provider=provider,
        model=model,
        benchmark="harness-bench",
        max_tasks=max_tasks,
        max_turns=max_turns,
    )

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


@eval_cli.command("list")
def list_benchmarks() -> None:
    """List available benchmarks."""
    click.echo("Available benchmarks:")
    click.echo("  swe-bench    — SWE-bench (lite/verified/full)")
    click.echo("  harness-bench — Custom harness capability benchmark")


def main() -> None:
    eval_cli()


if __name__ == "__main__":
    main()
