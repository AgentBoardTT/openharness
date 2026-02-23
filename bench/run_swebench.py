#!/usr/bin/env python3
"""SWE-bench Lite prediction generator.

Runs Harness and/or Claude Code against real GitHub issues from SWE-bench Lite,
collects git diffs, and saves predictions in the standard SWE-bench JSONL format.

Grading is done separately via the official swebench harness (requires Docker):
    python -m swebench.harness.run_evaluation \
      --dataset_name princeton-nlp/SWE-bench_Lite \
      --predictions_path eval-results/swebench-lite-harness-sonnet.jsonl \
      --max_workers 4 --run_id harness-sonnet

Usage:
    # Smoke test (5 tasks, both agents)
    uv run python bench/run_swebench.py --max-tasks 5

    # Full run, single agent
    uv run python bench/run_swebench.py --agent harness --max-tasks 100
    uv run python bench/run_swebench.py --agent claude-code --max-tasks 100
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Load .env from project root
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMEOUT_SECONDS = 600  # 10 min per task (SWE-bench tasks are complex)
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "eval-results"
REPO_CACHE_DIR = PROJECT_ROOT / ".swebench-repos"

AGENTS = ["harness", "claude-code"]

MODEL_NAMES = {
    "harness": "harness/claude-sonnet-4-6",
    "claude-code": "claude-code/claude-sonnet-4-6",
}

OUTPUT_FILES = {
    "harness": "swebench-lite-harness-sonnet.jsonl",
    "claude-code": "swebench-lite-claude-code-sonnet.jsonl",
}


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def load_swebench_lite(max_tasks: int | None = None) -> list[dict]:
    """Load SWE-bench Lite dataset from HuggingFace."""
    from datasets import load_dataset

    print("Loading SWE-bench Lite dataset...")
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    tasks = list(ds)
    print(f"  Loaded {len(tasks)} tasks total")
    if max_tasks and max_tasks < len(tasks):
        tasks = tasks[:max_tasks]
        print(f"  Limited to first {max_tasks} tasks")
    return tasks


# ---------------------------------------------------------------------------
# Repo management (clone once, checkout per task)
# ---------------------------------------------------------------------------


def get_repo_dir(repo: str) -> Path:
    """Get the cached clone directory for a repo (e.g. 'django/django')."""
    safe_name = repo.replace("/", "__")
    return REPO_CACHE_DIR / safe_name


def ensure_repo_cloned(repo: str) -> Path:
    """Clone repo if not already cached. Returns the repo directory."""
    repo_dir = get_repo_dir(repo)
    if repo_dir.exists() and (repo_dir / ".git").exists():
        return repo_dir

    repo_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{repo}.git"
    print(f"  Cloning {url}...")
    subprocess.run(
        ["git", "clone", "--quiet", url, str(repo_dir)],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return repo_dir


def checkout_commit(repo_dir: Path, commit: str) -> None:
    """Hard-reset repo to a specific commit, discarding any changes."""
    subprocess.run(
        ["git", "checkout", "--force", commit],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "clean", "-fdx"],
        cwd=str(repo_dir),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def get_diff(repo_dir: Path) -> str:
    """Get the git diff (staged + unstaged + untracked) from the repo."""
    # Stage everything so we capture new files too
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=30,
    )
    result = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Agent runners
# ---------------------------------------------------------------------------


def run_harness(problem_statement: str, repo_dir: Path) -> tuple[str, str]:
    """Run Harness agent. Returns (output, error)."""
    cmd = [
        "uv", "run", "harness",
        "--provider", "anthropic",
        "--model", "claude-sonnet-4-6",
        "--permission", "bypass",
        "--cwd", str(repo_dir),
        "--no-rich",
        "--no-interactive",
        problem_statement,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(PROJECT_ROOT),
            env=os.environ,
        )
        return result.stdout + result.stderr, ""
    except subprocess.TimeoutExpired:
        return "", "timeout"
    except Exception as e:
        return "", str(e)


def run_claude_code(problem_statement: str, repo_dir: Path) -> tuple[str, str]:
    """Run Claude Code agent. Returns (output, error)."""
    cmd = [
        "claude",
        "--print",
        "--model", "claude-sonnet-4-6",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
        "--output-format", "text",
        problem_statement,
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(repo_dir),
            env=env,
        )
        return result.stdout + result.stderr, ""
    except subprocess.TimeoutExpired:
        return "", "timeout"
    except Exception as e:
        return "", str(e)


AGENT_RUNNERS = {
    "harness": run_harness,
    "claude-code": run_claude_code,
}


# ---------------------------------------------------------------------------
# Resume support
# ---------------------------------------------------------------------------


def load_existing_predictions(output_path: Path) -> set[str]:
    """Load instance_ids already in the output JSONL."""
    done = set()
    if output_path.exists():
        for line in output_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    pred = json.loads(line)
                    done.add(pred["instance_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return done


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_predictions(agent: str, tasks: list[dict]) -> Path:
    """Run an agent on all tasks and save predictions to JSONL."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / OUTPUT_FILES[agent]
    model_name = MODEL_NAMES[agent]
    runner = AGENT_RUNNERS[agent]

    # Resume: skip tasks already done
    done_ids = load_existing_predictions(output_path)
    remaining = [t for t in tasks if t["instance_id"] not in done_ids]

    if done_ids:
        print(f"  Resuming: {len(done_ids)} already done, {len(remaining)} remaining")

    if not remaining:
        print(f"  All {len(tasks)} tasks already completed!")
        return output_path

    total = len(remaining)
    for i, task in enumerate(remaining, 1):
        instance_id = task["instance_id"]
        repo = task["repo"]
        base_commit = task["base_commit"]
        problem_statement = task["problem_statement"]

        print(f"\n[{i}/{total}] {instance_id}")
        print(f"  Repo: {repo} @ {base_commit[:10]}")

        # Prepare repo
        try:
            repo_dir = ensure_repo_cloned(repo)
            checkout_commit(repo_dir, base_commit)
        except Exception as e:
            print(f"  ERROR setting up repo: {e}")
            # Save empty patch so we don't retry
            prediction = {
                "instance_id": instance_id,
                "model_name_or_path": model_name,
                "model_patch": "",
            }
            with open(output_path, "a") as f:
                f.write(json.dumps(prediction) + "\n")
            continue

        # Run agent
        start = time.time()
        output, error = runner(problem_statement, repo_dir)
        duration = time.time() - start

        if error:
            print(f"  ERROR: {error} ({duration:.1f}s)")
            patch = ""
        else:
            # Collect diff
            patch = get_diff(repo_dir)
            patch_lines = len(patch.splitlines()) if patch else 0
            print(f"  Done: {patch_lines} lines of diff ({duration:.1f}s)")

        # Save prediction
        prediction = {
            "instance_id": instance_id,
            "model_name_or_path": model_name,
            "model_patch": patch,
        }
        with open(output_path, "a") as f:
            f.write(json.dumps(prediction) + "\n")

    return output_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Generate SWE-bench Lite predictions for Harness vs Claude Code"
    )
    parser.add_argument(
        "--agent",
        choices=AGENTS,
        help="Run only this agent (default: both)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=100,
        help="Max number of tasks to run (default: 100)",
    )
    args = parser.parse_args()

    agents = [args.agent] if args.agent else AGENTS

    # Verify API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Load dataset
    tasks = load_swebench_lite(args.max_tasks)

    print(f"\nSWE-bench Lite Prediction Generator")
    print(f"Agents: {', '.join(agents)}")
    print(f"Tasks: {len(tasks)}")
    print(f"Timeout: {TIMEOUT_SECONDS}s per task")
    print()

    for agent in agents:
        print(f"\n{'='*60}")
        print(f"Agent: {agent} ({MODEL_NAMES[agent]})")
        print(f"{'='*60}")

        output_path = run_predictions(agent, tasks)
        print(f"\nPredictions saved to {output_path}")

        # Summary
        done_ids = load_existing_predictions(output_path)
        with_patch = 0
        for line in output_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    pred = json.loads(line)
                    if pred.get("model_patch", "").strip():
                        with_patch += 1
                except (json.JSONDecodeError, KeyError):
                    pass
        print(f"  Total predictions: {len(done_ids)}")
        print(f"  With non-empty patch: {with_patch}")

    print(f"\n{'='*60}")
    print("Done! To grade with the official SWE-bench harness:")
    for agent in agents:
        output_file = OUTPUT_FILES[agent]
        run_id = agent + "-sonnet"
        print(f"""
  python -m swebench.harness.run_evaluation \\
    --dataset_name princeton-nlp/SWE-bench_Lite \\
    --predictions_path eval-results/{output_file} \\
    --max_workers 4 --run_id {run_id}""")


if __name__ == "__main__":
    main()
