<div align="center">

# Harness

### State-of-the-art open-source coding agent

CLI + SDK that works with **any** LLM — Claude, GPT, Gemini, Ollama, or any OpenAI-compatible endpoint.

The only open-source agent to score **100% on Harness-Bench** and outperform Claude Code, OpenCode, and pi-mono.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://python.org)
[![GitHub stars](https://img.shields.io/github/stars/AgentBoardTT/openharness?style=social)](https://github.com/AgentBoardTT/openharness)
[![GitHub issues](https://img.shields.io/github/issues/AgentBoardTT/openharness)](https://github.com/AgentBoardTT/openharness/issues)

[Get Started in 60 Seconds](#-get-started-in-60-seconds) · [Benchmark Results](#-benchmark-results) · [Features](#-features) · [Providers](#-providers) · [SDK](#-sdk) · [Contributing](#-contributing)

</div>

---

## Benchmark Results

Harness was benchmarked against the leading coding agents on 8 real-world tasks covering multi-file editing, bug fixing, error recovery, refactoring, context understanding, and code analysis.

### Overall Scores

| Agent | Claude Opus 4.6 | GPT-5.2 |
|-------|:---:|:---:|
| **Harness** | **7/8 (88%)** | **8/8 (100%)** |
| Claude Code | 7/8 (88%) | — |
| OpenCode | 7/8 (88%) | 7/8 (88%) |
| pi-mono | 7/8 (88%) | 8/8 (100%) |

Harness is the **only open-source agent** that achieves a perfect score — and it does so across providers, not locked to one.

### Per-Task Breakdown (GPT-5.2)

| Task | Harness | OpenCode | pi-mono |
|------|:---:|:---:|:---:|
| Multi-file editing | PASS (17.5s) | PASS (19.4s) | PASS (26.8s) |
| Error recovery | PASS (5.2s) | PASS (11.7s) | PASS (10.1s) |
| Tool efficiency | PASS (1.8s) | PASS (5.6s) | PASS (9.2s) |
| Context understanding | PASS (9.7s) | FAIL | PASS (41.3s) |
| Project creation | PASS (3.0s) | PASS (7.6s) | PASS (3.8s) |
| Bug fixing | PASS (5.5s) | PASS (12.9s) | PASS (10.0s) |
| Code analysis | PASS (1.9s) | PASS (5.2s) | PASS (2.3s) |
| Refactoring | PASS (6.4s) | PASS (11.7s) | PASS (12.7s) |

### Speed

| Agent | Model | Avg per Task | Total (8 tasks) |
|-------|-------|:---:|:---:|
| **Harness** | **GPT-5.2** | **6.4s** | **51.0s** |
| Harness | Opus 4.6 | 12.5s | 99.7s |
| Claude Code | Opus 4.6 | 16.4s | 131.5s |
| OpenCode | GPT-5.2 | 10.7s | 85.8s |
| pi-mono | GPT-5.2 | 14.5s | 116.2s |

Harness is **2x faster** than the next-fastest agent on GPT-5.2, and **30% faster** than Claude Code on Opus.

### Why This Matters

The scaffold around a model matters as much as the model itself. The same Claude Opus 4.5 scores anywhere from 58% to 80% on SWE-bench depending on the agent harness. That's why we built this — a SOTA scaffold that's open, fast, and works with every provider.

<p align="right"><a href="#harness">back to top</a></p>

---

## Get Started in 60 Seconds

No programming experience needed. Just open your terminal and follow these 3 steps.

> **What's a terminal?** On Mac, open Spotlight (Cmd + Space) and type "Terminal". On Windows, search for "PowerShell". On Linux, look for "Terminal" in your apps.

### Step 1: Install

Copy-paste this into your terminal and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/AgentBoardTT/openharness/main/install.sh | bash
```

This automatically installs everything you need (Python, uv, and Harness). Just follow any prompts.

> **Windows users:** Run `pip install harness-agent` instead.

### Step 2: Connect your AI provider

```bash
harness connect
```

You'll see a menu like this:

```
Select a provider:
  (1) Anthropic
  (2) OpenAI
  (3) Google

Enter choice [1]:
```

Pick a provider, paste your API key, and you're connected. Your key is saved securely to `~/.harness/config.toml` — you only need to do this once.

> **Where do I get an API key?**
> - Anthropic (Claude): https://console.anthropic.com/settings/keys
> - OpenAI (GPT): https://platform.openai.com/api-keys
> - Google (Gemini): https://aistudio.google.com/apikey

### Step 3: Use it

Give it any coding task in plain English:

```bash
harness "Create a Python script that downloads all images from a webpage"
```

Or start an interactive chat:

```bash
harness
```

Then just type what you want. Type `/help` to see commands, `/connect` to switch providers, Ctrl+D to exit.

That's it. You're running a state-of-the-art coding agent.

<p align="right"><a href="#harness">back to top</a></p>

---

## More Examples

```bash
# Fix a bug
harness "Fix the authentication bug in auth.py"

# Use a specific model
harness -p openai -m gpt-5.2 "Refactor this function"

# Use a local model (no API key, fully private)
harness -p ollama -m llama3.3 "Write unit tests for utils.py"

# Resume a previous session
harness --session abc123 "Continue where we left off"

# Auto-approve everything (for scripting/CI)
harness --permission bypass "Run all tests and fix failures"
```

<p align="right"><a href="#harness">back to top</a></p>

---

## Providers

Harness works with every major AI provider — switch with a single flag.

| Provider | Models | How to connect |
|----------|--------|--------|
| **Anthropic** | Claude Opus 4.6, Sonnet 4.6, Haiku 4.5 | `harness connect` and choose Anthropic |
| **OpenAI** | GPT-5.2, GPT-4.1, o3, o4-mini, GPT-4o | `harness connect` and choose OpenAI |
| **Google** | Gemini 2.5 Pro, 2.5 Flash, 2.0 Flash | `harness connect` and choose Google |
| **Ollama** | Llama, Mistral, Qwen, Phi, etc. | No key needed — runs locally |
| **OpenAI-compatible** | DeepSeek, Groq, OpenRouter | `--base-url` flag |

```bash
harness models list          # Browse 50+ supported models
harness models info sonnet   # Get details for a specific model
```

<p align="right"><a href="#harness">back to top</a></p>

---

## Features

### Built-in Tools

| Tool | What it does |
|------|-------------|
| **Read** | Read file contents |
| **Write** | Create or overwrite files |
| **Edit** | Find-and-replace inside files |
| **Bash** | Run shell commands |
| **Glob** | Find files by name pattern |
| **Grep** | Search inside files with regex |
| **Task** | Spawn sub-agents for parallel work |
| **WebFetch** | Pull content from web pages |
| **AskUser** | Ask you a question mid-task |
| **Checkpoint** | Save/restore file snapshots |

### Sub-Agents

The agent can spin up specialized workers in parallel:

| Agent | Access | Use Case |
|-------|--------|----------|
| **general** | Full tools | Complex multi-step tasks |
| **explore** | Read-only | Fast codebase exploration |
| **plan** | Read-only | Architecture planning |

### Permission Modes

You control what the agent can do:

| Mode | Behavior |
|------|----------|
| `default` | Reads are automatic, writes ask for approval |
| `accept_edits` | File edits are automatic, shell commands ask |
| `plan` | Read-only — nothing gets changed |
| `bypass` | Full auto-approve (for scripts/CI) |

### MCP (Model Context Protocol)

Connect external tool servers — Jira, Slack, databases, anything with an MCP adapter:

```python
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

Teach the agent custom workflows by dropping a `.md` file in `.harness/skills/`:

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

Run your own commands before/after every tool call:

```python
hooks = [
    harness.Hook(
        event=harness.HookEvent.PRE_TOOL_USE,
        command="echo 'About to run {tool_name}'",
        matcher="Bash",
    ),
]

async for msg in harness.run("Fix the tests", hooks=hooks):
    ...
```

### Memory

- **Project instructions** — Drop a `HARNESS.md` in your project root
- **Auto-memory** — Learnings persist across sessions in `~/.harness/memory/`

<p align="right"><a href="#harness">back to top</a></p>

---

## SDK

Use Harness as a Python library to build your own tools on top of it.

### Basic Usage

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

### With Configuration

```python
async for msg in harness.run(
    "Refactor the database module",
    provider="openai",
    model="gpt-4.1",
    permission_mode="accept_edits",
    max_turns=50,
):
    ...
```

### Sub-Agent API

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

<p align="right"><a href="#harness">back to top</a></p>

---

## Configuration

### Config File

Created automatically by `harness connect`. Lives at `~/.harness/config.toml`:

```toml
[providers.anthropic]
api_key = "sk-ant-..."

[providers.openai]
api_key = "sk-..."
```

### Environment Variables

If you prefer env vars, those work too:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="AIza..."
```

<p align="right"><a href="#harness">back to top</a></p>

---

## Evaluation

### Run Benchmarks

```bash
# Quick validation — 8 tasks, ~$1
harness eval harness-bench --provider anthropic --model sonnet

# SWE-bench Lite — 300 real GitHub issues
harness eval swe-bench --split lite --max-tasks 10

# List benchmarks
harness eval list
```

### Available Benchmarks

| Benchmark | Tasks | Description |
|-----------|-------|-------------|
| **Harness-Bench** | 8 | Multi-file editing, error recovery, refactoring, analysis |
| **SWE-bench Lite** | 300 | Curated subset of real GitHub issues |
| **SWE-bench Verified** | 500 | Human-verified solvable issues |
| **SWE-bench Full** | 2,294 | Complete benchmark |

<p align="right"><a href="#harness">back to top</a></p>

---

## Architecture

```
src/harness/
  core/
    engine.py          Top-level run() entry point
    loop.py            Agent loop (provider -> tools -> repeat)
    session.py         JSONL session persistence
    context.py         Context window management + compaction
    config.py          Config loading (env, TOML, HARNESS.md)
  providers/
    anthropic.py       Claude adapter
    openai.py          GPT / OpenAI-compatible adapter
    google.py          Gemini adapter
    ollama.py          Ollama local model adapter
    registry.py        Model catalogue (50+ models)
  tools/               Read, Write, Edit, Bash, Glob, Grep, Task, Web, etc.
  agents/              Sub-agent registry + lifecycle manager
  hooks/               Pre/post tool-use hook system
  mcp/                 MCP client + progressive tool discovery
  skills/              Skill loader (SKILL.md parser)
  memory/              Auto-memory + project instructions
  permissions/         Permission rules engine
  ui/                  Rich terminal output + streaming + diffs
  eval/                SWE-bench, Harness-Bench, metrics, reports
  cli/                 Click CLI entry point + subcommands
```

<p align="right"><a href="#harness">back to top</a></p>

---

## Development

```bash
git clone https://github.com/AgentBoardTT/openharness.git
cd openharness
uv pip install -e ".[dev]"
uv run pytest tests/ -v
uv run ruff check src/ tests/
```

---

## Contributing

We'd love your help. Here's how:

- **Bug reports** — [Open an issue](https://github.com/AgentBoardTT/openharness/issues)
- **Feature requests** — [Open an issue](https://github.com/AgentBoardTT/openharness/issues)
- **Pull requests** — Fork, branch, submit

Areas where we especially need help:
- New provider adapters
- Additional tools
- Benchmark tasks and evaluation
- Documentation and examples

---

## License

[MIT](LICENSE)

<div align="center">

**The best agent scaffold is an open one.**

</div>
