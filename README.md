# Harness

Multi-provider coding agent CLI + SDK. Run coding tasks against Claude, GPT, Gemini, or local models via Ollama — all through one unified interface.

## Installation

```bash
# With uv (recommended)
uv pip install -e ".[dev]"

# With pip
pip install -e ".[dev]"
```

## Quick Start

### CLI

```bash
# Basic usage — default provider is Anthropic
harness "Fix the typo in README.md"

# Specify a provider and model
harness --provider openai --model gpt-4o "Refactor this function"

# Use an alias
harness -m sonnet "Add error handling to auth.py"

# Rich terminal output
harness --rich "Read and explain main.py"

# Resume a previous session
harness --session abc123 "Continue where we left off"

# Local models via Ollama
harness --provider ollama --model llama3.3 "Write unit tests for utils.py"
```

### SDK

```python
import harness

async for msg in harness.run("Fix the bug in auth.py"):
    match msg:
        case harness.TextMessage(text=t, is_partial=False):
            print(t)
        case harness.ToolUse(name=name):
            print(f"Using tool: {name}")
        case harness.Result(text=t, total_tokens=tok):
            print(f"Done ({tok} tokens): {t}")
```

### SDK with Configuration

```python
import harness

async for msg in harness.run(
    "Refactor the database module",
    provider="openai",
    model="gpt-4.1",
    permission_mode="accept_edits",
    max_turns=50,
    hooks=[
        harness.Hook(
            event=harness.HookEvent.POST_TOOL_USE,
            command="echo 'Tool {tool_name} completed'",
        )
    ],
):
    ...
```

## Providers

| Provider | Models | Config |
|----------|--------|--------|
| **Anthropic** | Claude Opus, Sonnet, Haiku | `ANTHROPIC_API_KEY` |
| **OpenAI** | GPT-4o, GPT-4.1, o3, o4-mini | `OPENAI_API_KEY` |
| **Google** | Gemini 2.5 Pro/Flash, 2.0 Flash | `GOOGLE_API_KEY` |
| **Ollama** | Llama, Mistral, Qwen, Phi, etc. | Local (no key needed) |
| **OpenAI-compatible** | DeepSeek, Groq, OpenRouter | `--base-url` + `OPENAI_API_KEY` |

```bash
# List all available models
harness models list

# Get info on a specific model
harness models info sonnet
```

## Features

### Tools (Built-in)

| Tool | Description |
|------|-------------|
| **Read** | Read file contents with offset/limit |
| **Write** | Create or overwrite files |
| **Edit** | Exact string replacement in files |
| **Bash** | Execute shell commands |
| **Glob** | Find files by pattern |
| **Grep** | Search file contents with regex |
| **Task** | Spawn sub-agents for parallel work |
| **WebFetch** | Fetch and extract web page content |
| **AskUser** | Ask the user a question mid-task |
| **Checkpoint** | Save/restore file snapshots |

### MCP (Model Context Protocol)

Connect external tool servers via MCP:

```python
import harness

async for msg in harness.run(
    "Search our Jira board",
    mcp_servers={
        "jira": {
            "command": "npx",
            "args": ["-y", "@anthropic/mcp-server-jira"],
            "env": {"JIRA_TOKEN": "..."},
        }
    },
):
    ...
```

### Skills

Drop `.md` files in `.harness/skills/` to teach the agent custom workflows:

```markdown
---
name: deploy
description: Deploy to production
user_invocable: true
---

1. Run the test suite: `pytest tests/ -v`
2. Build the Docker image: `docker build -t myapp .`
3. Push to registry and deploy
```

### Hooks

Execute shell commands before/after tool use:

```python
import harness

hooks = [
    harness.Hook(
        event=harness.HookEvent.PRE_TOOL_USE,
        command="echo 'About to run {tool_name}'",
        matcher="Bash",  # Only for Bash tool
    ),
    harness.Hook(
        event=harness.HookEvent.POST_TOOL_USE,
        command="echo 'Tool result: {result}'",
    ),
]

async for msg in harness.run("Fix the tests", hooks=hooks):
    ...
```

### Sub-Agents

Spawn specialized sub-agents for parallel work:

- **general** — Full tool access, can read/write/execute
- **explore** — Read-only, fast codebase exploration
- **plan** — Read-only, architecture planning

The model can use the `Task` tool to spawn sub-agents automatically, or use the SDK:

```python
from harness.agents.manager import AgentManager

mgr = AgentManager(provider=provider, tools=tools, cwd=".")
result = await mgr.spawn("explore", "Find all API endpoints")

# Parallel execution
results = await mgr.spawn_parallel([
    ("explore", "Find all API endpoints"),
    ("explore", "Find all database models"),
    ("explore", "Find all test files"),
])
```

### Permissions

Control what tools the agent can use:

| Mode | Behavior |
|------|----------|
| `default` | Read tools auto-allowed, write tools require approval |
| `accept_edits` | File edits auto-allowed, Bash requires approval |
| `plan` | Read-only — all write tools blocked |
| `bypass` | Everything auto-allowed (for scripting/CI) |

```bash
harness --permission bypass "Run all tests and fix failures"
```

### Memory

Harness supports project-level memory via `HARNESS.md`:

```markdown
# Project Instructions

- Use pytest for testing
- Follow PEP 8 style
- Always run `ruff check` before committing
```

Auto-memory persists learnings across sessions in `~/.harness/memory/`.

### Rich Terminal UI

```bash
# Enable rich output (auto-detected for TTY)
harness --rich "Read and explain main.py"

# Force plain output (for piping)
harness --no-rich "List all files" | head -20
```

Features: colored output, tool execution spinners, syntax-highlighted diffs, token/cost tracking.

## Evaluation

Run benchmarks to measure agent performance:

```bash
# Run custom Harness-Bench
harness eval harness-bench --provider anthropic --model sonnet

# Run SWE-bench (requires datasets package)
harness eval swe-bench --split lite --max-tasks 10

# List available benchmark tasks
harness eval list
```

### Available Benchmarks

| Benchmark | Tasks | Description |
|-----------|-------|-------------|
| **Harness-Bench** | 8 | Custom tasks testing multi-file editing, error recovery, refactoring, etc. |
| **SWE-bench Lite** | 300 | Curated subset of real GitHub issues |
| **SWE-bench Verified** | 500 | Human-verified solvable issues |
| **SWE-bench Full** | 2,294 | Complete benchmark of real-world GitHub issues |

### Current Landscape: SWE-bench Verified Scores

How existing coding agents and models perform (as of Feb 2026):

**Top Models (Raw Model Scores)**

| Model | Provider | SWE-bench Verified | Cost (in/out per Mtok) |
|-------|----------|-------------------|------------------------|
| Claude Opus 4.6 | Anthropic | ~80.8% | $15.00 / $75.00 |
| GPT-5.2 | OpenAI | ~80.0% | $1.75 / $14.00 |
| Claude Sonnet 4.6 | Anthropic | ~79.6% | $3.00 / $15.00 |
| Gemini 2.5 Pro | Google | ~65% | $1.25 / $10.00 |
| o3 | OpenAI | ~69-72% | $2.00 / $8.00 |
| GPT-4.1 | OpenAI | ~54.6% | $2.00 / $8.00 |
| GPT-4o | OpenAI | ~45% | $2.50 / $10.00 |

**Coding Agent Implementations**

| Agent | Underlying Model | SWE-bench Verified | Notes |
|-------|-----------------|-------------------|-------|
| Claude Code | Opus 4.6 | ~72-80% | Anthropic's official CLI |
| Cursor | Opus 4.5 | ~72% | Proprietary scaffold |
| OpenCode | Various | ~8% (Mobile) | Open-source CLI, 60K+ GitHub stars |
| pi-mono | Various | N/A | Minimalist 4-tool agent, competitive on Terminal-Bench |
| Aider | GPT-4o + Opus | ~26% (Lite) | Open-source, last published May 2024 |
| Devin | Internal | ~14% | Cognition's autonomous agent |

**Key Insight:** Scaffold design matters enormously — the same Claude Opus 4.5 model
achieves ~79% in optimized scaffolds but only ~58% in simpler ones. This is why Harness
exists: to build a competitive scaffold.

### Recommended Models for Evaluation

Based on current benchmarks, the best models to evaluate with:

| Role | Model | Why |
|------|-------|-----|
| Best overall | `claude-opus-4-6` | Highest SWE-bench score (~80.8%) |
| Best value | `claude-sonnet-4-6` | 98% of Opus quality at 1/5 cost |
| Best OpenAI | `gpt-5.2` | Matches Opus at ~80%, purpose-built for coding |
| Best OpenAI (agentic) | `gpt-5.2-codex` | Optimized for multi-step agent tasks |
| Budget reasoning | `o3` | ~70% at $2/$8, good for cost-constrained runs |

### Estimated Cost Per Model

Token usage estimates: ~50K input + ~10K output per SWE-bench task,
~20K input + ~5K output per Harness-Bench task. Actual costs vary by
difficulty, turn count, and early termination.

**Anthropic Models**

| Benchmark | Opus 4.6 ($15/$75) | Sonnet 4.6 ($3/$15) |
|-----------|--------------------|---------------------|
| Harness-Bench (8) | ~$5 | ~$1 |
| SWE-bench Lite (300) | ~$450 | ~$90 |
| SWE-bench Verified (500) | ~$750 | ~$150 |
| SWE-bench Full (2,294) | ~$3,450 | ~$690 |
| **All benchmarks** | **~$4,655** | **~$931** |

**OpenAI Models**

| Benchmark | GPT-5.2 ($1.75/$14) | o3 ($2/$8) | GPT-4o ($2.50/$10) |
|-----------|---------------------|------------|---------------------|
| Harness-Bench (8) | ~$1 | ~$1 | ~$1 |
| SWE-bench Lite (300) | ~$68 | ~$54 | ~$68 |
| SWE-bench Verified (500) | ~$114 | ~$90 | ~$113 |
| SWE-bench Full (2,294) | ~$522 | ~$414 | ~$518 |
| **All benchmarks** | **~$705** | **~$559** | **~$700** |

**Summary: Full Run (All Benchmarks, Top Models)**

| Scope | Anthropic (Opus + Sonnet) | OpenAI (GPT-5.2 + o3) | Grand Total |
|-------|---------------------------|------------------------|-------------|
| All benchmarks | ~$5,586 | ~$1,264 | **~$6,850** |

**Recommended Approach (phased):**

```bash
# Phase 1: Quick validation (~$8 total, 4 models x 8 tasks)
harness eval harness-bench --provider anthropic --model opus
harness eval harness-bench --provider anthropic --model sonnet
harness eval harness-bench --provider openai --model gpt-5.2
harness eval harness-bench --provider openai --model o3

# Phase 2: Publishable results (~$226 total, 2 best models x 300 tasks)
harness eval swe-bench --split lite --provider anthropic --model sonnet
harness eval swe-bench --split lite --provider openai --model gpt-5.2

# Phase 3: Full benchmark (only if targeting leaderboard, ~$5K+)
harness eval swe-bench --split verified --provider anthropic --model opus
```

## Configuration

### Config File

Create `.harness/config.toml` or `~/.harness/config.toml`:

```toml
[default]
provider = "anthropic"
model = "claude-sonnet-4-6"

[providers.anthropic]
api_key = "sk-..."

[providers.openai]
api_key = "sk-..."
```

### Environment Variables

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="AIza..."
export HARNESS_PROVIDER="anthropic"
export HARNESS_MODEL="sonnet"
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/

# Type check
uv run pyright src/
```

## Architecture

```
src/harness/
  __init__.py          # SDK public API
  core/
    engine.py          # Top-level run() entry point
    loop.py            # Agent loop (provider -> tools -> repeat)
    session.py         # JSONL session persistence
    context.py         # Context window management + compaction
    steering.py        # Real-time user interjection channel
    config.py          # Config loading (env, TOML, HARNESS.md)
  providers/
    base.py            # Abstract base provider
    anthropic.py       # Claude adapter
    openai.py          # GPT / OpenAI-compatible adapter
    google.py          # Gemini adapter
    ollama.py          # Ollama local model adapter
    registry.py        # Model catalogue (50+ models)
  tools/               # Read, Write, Edit, Bash, Glob, Grep, Task, Web, etc.
  agents/              # Sub-agent registry + lifecycle manager
  hooks/               # Pre/post tool-use hook system
  mcp/                 # MCP client + progressive tool discovery
  skills/              # Skill loader (SKILL.md parser)
  memory/              # Auto-memory + project instructions
  permissions/         # Permission rules engine
  ui/                  # Rich terminal output + streaming + diffs
  eval/                # SWE-bench, Harness-Bench, metrics, reports
  cli/                 # Click CLI entry point + subcommands
  types/               # Shared type definitions
```

## License

MIT
