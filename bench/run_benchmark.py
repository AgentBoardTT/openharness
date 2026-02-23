#!/usr/bin/env python3
"""Unified Harness-Bench runner for comparing multiple coding agents.

Runs the same 8 Harness-Bench tasks against 4 agents x 2 models, collects
results, and generates a comparison report.

Usage:
    # Load env and run
    cd /Users/huetuanthi/dev/agents/harness
    uv run python bench/run_benchmark.py

    # Run a single agent/model combo
    uv run python bench/run_benchmark.py --agent harness --model opus

    # Dry run (setup only, no API calls)
    uv run python bench/run_benchmark.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# Load .env from project root
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# Add src to path for harness imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harness.eval.harness_bench import HARNESS_BENCH_TASKS  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODELS = {
    "opus": {
        "harness": {"provider": "anthropic", "model": "claude-opus-4-6"},
        "claude-code": {"model": "opus"},
        "opencode": {"provider": "anthropic", "model": "claude-opus-4-6"},
        "pi-mono": {"provider": "anthropic", "model": "claude-opus-4-6"},
    },
    "gpt52": {
        "harness": {"provider": "openai", "model": "gpt-5.2"},
        # Claude Code only supports Anthropic models — skip for GPT-5.2
        "opencode": {"provider": "openai", "model": "gpt-5.2"},
        "pi-mono": {"provider": "openai", "model": "gpt-5.2"},
    },
}

AGENTS = ["harness", "claude-code", "opencode", "pi-mono"]
TIMEOUT_SECONDS = 180  # Per task timeout (3 min for complex tasks)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class TaskRun:
    agent: str
    model_alias: str
    task_id: str
    task_category: str
    task_difficulty: str
    resolved: bool = False
    duration_seconds: float = 0.0
    error: str = ""
    output: str = ""


@dataclass
class BenchmarkResults:
    started_at: str = ""
    completed_at: str = ""
    runs: list[TaskRun] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Task setup & verification
# ---------------------------------------------------------------------------


def setup_task_dir(task: dict, base_dir: Path) -> Path:
    """Create a temp directory with the task's setup files."""
    task_dir = base_dir / task["id"]
    task_dir.mkdir(parents=True, exist_ok=True)

    for filepath, content in task.get("setup_files", {}).items():
        full_path = task_dir / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    return task_dir


def verify_task(task: dict, task_dir: Path) -> bool:
    """Run the verification command and return True if it passes."""
    verify_cmd = task.get("verify")
    if not verify_cmd:
        return True  # No verification = assume pass if no errors

    try:
        result = subprocess.run(
            verify_cmd,
            shell=True,
            cwd=str(task_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


# ---------------------------------------------------------------------------
# Agent runners
# ---------------------------------------------------------------------------


def run_harness_agent(task: dict, task_dir: Path, model_cfg: dict) -> tuple[bool, str, str]:
    """Run our Harness agent on a task."""
    provider = model_cfg["provider"]
    model = model_cfg["model"]
    project_root = Path(__file__).parent.parent

    cmd = [
        "uv", "run", "harness",
        "--provider", provider,
        "--model", model,
        "--permission", "bypass",
        "--cwd", str(task_dir),
        "--no-rich",
        "--no-interactive",
        task["description"],
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(project_root),
            env=os.environ,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output, ""
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)


def run_claude_code(task: dict, task_dir: Path, model_cfg: dict) -> tuple[bool, str, str]:
    """Run Claude Code on a task."""
    model = model_cfg["model"]

    cmd = [
        "claude",
        "--print",
        "--model", model,
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
        "--output-format", "text",
        task["description"],
    ]

    # Remove CLAUDECODE env var to allow launching from within Claude Code
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(task_dir),
            env=env,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output, ""
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)


def run_opencode(task: dict, task_dir: Path, model_cfg: dict) -> tuple[bool, str, str]:
    """Run OpenCode on a task."""
    provider = model_cfg["provider"]
    model = model_cfg["model"]

    # OpenCode needs a full config with agent definition
    model_key = model.replace(".", "-")  # e.g. gpt-5.2 -> gpt-5-2
    config = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"{provider}/{model_key}",
        "provider": {
            provider: {
                "models": {
                    model_key: {
                        "name": model,
                        "limit": {"context": 200000, "output": 16384},
                    }
                }
            }
        },
        "agent": {
            "coder": {
                "description": "Coding agent",
                "model": f"{provider}/{model_key}",
            }
        },
    }
    config_path = task_dir / ".opencode.json"
    config_path.write_text(json.dumps(config))

    cmd = [
        "opencode",
        "--cwd", str(task_dir),
        "--quiet",
        "--prompt", task["description"],
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env=os.environ,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output, ""
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)


def run_pi_mono(task: dict, task_dir: Path, model_cfg: dict) -> tuple[bool, str, str]:
    """Run pi-mono on a task."""
    provider = model_cfg["provider"]
    model = model_cfg["model"]

    cmd = [
        "pi",
        "--provider", provider,
        "--model", model,
        "--print",
        "--no-session",
        task["description"],
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(task_dir),
            env=os.environ,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output, ""
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)


AGENT_RUNNERS = {
    "harness": run_harness_agent,
    "claude-code": run_claude_code,
    "opencode": run_opencode,
    "pi-mono": run_pi_mono,
}


# ---------------------------------------------------------------------------
# Main benchmark loop
# ---------------------------------------------------------------------------


def run_single(
    agent: str,
    model_alias: str,
    task: dict,
    base_dir: Path,
) -> TaskRun:
    """Run a single agent/model/task combination."""
    task_dir = setup_task_dir(task, base_dir / agent / model_alias)

    run = TaskRun(
        agent=agent,
        model_alias=model_alias,
        task_id=task["id"],
        task_category=task.get("category", ""),
        task_difficulty=task.get("difficulty", "medium"),
    )

    model_cfg = MODELS[model_alias][agent]
    runner = AGENT_RUNNERS[agent]

    print(f"  Running {agent}/{model_alias} on {task['id']}...", end=" ", flush=True)
    start = time.time()

    _ok, output, error = runner(task, task_dir, model_cfg)
    run.duration_seconds = round(time.time() - start, 1)
    run.output = output[:2000]  # Truncate for storage
    run.error = error

    # Verify result regardless of agent exit code
    if not error:
        run.resolved = verify_task(task, task_dir)

    status = "PASS" if run.resolved else "FAIL"
    print(f"{status} ({run.duration_seconds}s)")

    return run


def run_benchmark(
    agents: list[str],
    model_aliases: list[str],
    dry_run: bool = False,
) -> BenchmarkResults:
    """Run the full benchmark matrix."""
    results = BenchmarkResults(started_at=datetime.now().isoformat())

    with tempfile.TemporaryDirectory(prefix="harness-bench-") as tmpdir:
        base_dir = Path(tmpdir)

        # Build list of valid (agent, model) combos
        combos = [
            (agent, model_alias)
            for model_alias in model_aliases
            for agent in agents
            if agent in MODELS.get(model_alias, {})
        ]
        total = len(combos) * len(HARNESS_BENCH_TASKS)
        done = 0

        for model_alias in model_aliases:
            for agent in agents:
                if agent not in MODELS.get(model_alias, {}):
                    print(f"\n  Skipping {agent}/{model_alias} (unsupported combo)")
                    continue

                print(f"\n{'='*60}")
                print(f"Agent: {agent} | Model: {model_alias}")
                print(f"{'='*60}")

                if dry_run:
                    print("  [DRY RUN] Skipping actual execution")
                    for task in HARNESS_BENCH_TASKS:
                        done += 1
                        print(f"  [{done}/{total}] Would run {task['id']}")
                    continue

                for task in HARNESS_BENCH_TASKS:
                    done += 1
                    print(f"  [{done}/{total}]", end=" ")
                    run = run_single(agent, model_alias, task, base_dir)
                    results.runs.append(run)

    results.completed_at = datetime.now().isoformat()
    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(results: BenchmarkResults) -> str:
    """Generate a markdown comparison report."""
    lines = []
    lines.append("# Harness-Bench Comparison Report")
    lines.append("")
    lines.append(f"**Date:** {results.started_at[:19]}")
    lines.append(f"**Tasks:** {len(HARNESS_BENCH_TASKS)}")
    lines.append("")

    # Build score matrix: agent -> model -> resolved_count
    agents_seen = []
    models_seen = []
    scores: dict[str, dict[str, list[bool]]] = {}

    for run in results.runs:
        if run.agent not in agents_seen:
            agents_seen.append(run.agent)
        if run.model_alias not in models_seen:
            models_seen.append(run.model_alias)
        scores.setdefault(run.agent, {}).setdefault(run.model_alias, []).append(run.resolved)

    # Summary table
    lines.append("## Overall Results")
    lines.append("")
    header = "| Agent |"
    separator = "|-------|"
    for m in models_seen:
        header += f" {m} |"
        separator += "------|"
    lines.append(header)
    lines.append(separator)

    for agent in agents_seen:
        row = f"| **{agent}** |"
        for model in models_seen:
            results_list = scores.get(agent, {}).get(model, [])
            resolved = sum(results_list)
            total = len(results_list)
            pct = (resolved / total * 100) if total > 0 else 0
            row += f" {resolved}/{total} ({pct:.0f}%) |"
        lines.append(row)

    lines.append("")

    # Detailed per-task results
    lines.append("## Per-Task Results")
    lines.append("")

    task_ids = [t["id"] for t in HARNESS_BENCH_TASKS]
    for model in models_seen:
        lines.append(f"### Model: {model}")
        lines.append("")
        header = "| Task |"
        separator = "|------|"
        for agent in agents_seen:
            header += f" {agent} |"
            separator += "------|"
        lines.append(header)
        lines.append(separator)

        for task_id in task_ids:
            row = f"| {task_id} |"
            for agent in agents_seen:
                matching = [
                    r for r in results.runs
                    if r.agent == agent and r.model_alias == model and r.task_id == task_id
                ]
                if matching:
                    r = matching[0]
                    status = "PASS" if r.resolved else "FAIL"
                    row += f" {status} ({r.duration_seconds}s) |"
                else:
                    row += " - |"
            lines.append(row)

        lines.append("")

    # Timing stats
    lines.append("## Timing")
    lines.append("")
    lines.append("| Agent | Model | Avg Duration | Total Duration |")
    lines.append("|-------|-------|-------------|----------------|")

    for agent in agents_seen:
        for model in models_seen:
            runs = [r for r in results.runs if r.agent == agent and r.model_alias == model]
            if runs:
                avg_dur = sum(r.duration_seconds for r in runs) / len(runs)
                total_dur = sum(r.duration_seconds for r in runs)
                lines.append(f"| {agent} | {model} | {avg_dur:.1f}s | {total_dur:.1f}s |")

    lines.append("")

    # Errors
    errors = [r for r in results.runs if r.error]
    if errors:
        lines.append("## Errors")
        lines.append("")
        for r in errors:
            lines.append(f"- **{r.agent}/{r.model_alias}/{r.task_id}**: {r.error}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Run Harness-Bench comparison")
    parser.add_argument(
        "--agent",
        choices=AGENTS,
        help="Run only this agent (default: all)",
    )
    parser.add_argument(
        "--model",
        choices=list(MODELS.keys()),
        help="Run only this model (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Set up tasks but don't make API calls",
    )
    args = parser.parse_args()

    agents = [args.agent] if args.agent else AGENTS
    models = [args.model] if args.model else list(MODELS.keys())

    # Verify API keys
    if not os.environ.get("ANTHROPIC_API_KEY") and "opus" in models:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("OPENAI_API_KEY") and "gpt52" in models:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    valid_combos = sum(1 for m in models for a in agents if a in MODELS.get(m, {}))
    total_runs = valid_combos * len(HARNESS_BENCH_TASKS)
    print(f"Harness-Bench Comparison")
    print(f"Agents: {', '.join(agents)}")
    print(f"Models: {', '.join(models)}")
    print(f"Tasks: {len(HARNESS_BENCH_TASKS)}")
    print(f"Total runs: {total_runs}")
    print()

    results = run_benchmark(agents, models, dry_run=args.dry_run)

    # Save raw results
    output_dir = Path(__file__).parent.parent / "eval-results"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Save JSON
    json_path = output_dir / f"harness-bench-{timestamp}.json"
    json_data = {
        "started_at": results.started_at,
        "completed_at": results.completed_at,
        "runs": [asdict(r) for r in results.runs],
    }
    json_path.write_text(json.dumps(json_data, indent=2))
    print(f"\nResults saved to {json_path}")

    # Generate and save report
    report = generate_report(results)
    report_path = output_dir / f"harness-bench-{timestamp}.md"
    report_path.write_text(report)
    print(f"Report saved to {report_path}")

    # Print report to stdout
    print("\n" + report)


if __name__ == "__main__":
    main()
