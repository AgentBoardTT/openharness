# 03 - Harness: CLI + SDK Implementation Plan

## Project Overview

**Harness** is an open-source, multi-provider coding agent CLI and SDK. It combines pi-mono's minimalist multi-provider design with Claude Code's harness sophistication to deliver top-tier agent performance across any LLM.

### Design Principles

1. **Performance first** — The harness contributes +36% to agent performance; invest heavily here
2. **Design simplicity** — Minimal core, extensible periphery (pi-mono philosophy)
3. **Provider-agnostic** — Same harness, any LLM (Claude, Gemini, GPT, local)
4. **MCP-native** — First-class Model Context Protocol support
5. **Python-first** — SDK in Python, CLI as a thin wrapper (broader ecosystem reach than TypeScript)

---

## 1. Project Structure

```
harness/
├── pyproject.toml              # uv-managed project
├── HARNESS.md                  # Project config (like CLAUDE.md)
├── src/
│   └── harness/
│       ├── __init__.py         # Public SDK API
│       ├── core/
│       │   ├── loop.py         # Agent loop (main engine)
│       │   ├── context.py      # Context window management
│       │   ├── session.py      # Session persistence (JSONL DAG)
│       │   └── steering.py     # Real-time user interjection channel
│       ├── providers/
│       │   ├── base.py         # ProviderAdapter protocol
│       │   ├── openai.py       # OpenAI + compatible APIs
│       │   ├── anthropic.py    # Claude family
│       │   ├── google.py       # Gemini family
│       │   └── registry.py     # Provider/model registry
│       ├── tools/
│       │   ├── base.py         # Tool protocol + ToolResult
│       │   ├── read.py         # Read file contents
│       │   ├── write.py        # Create/overwrite files
│       │   ├── edit.py         # Surgical string replacement
│       │   ├── bash.py         # Shell execution (persistent)
│       │   ├── glob.py         # File pattern matching
│       │   ├── grep.py         # Content search
│       │   ├── web.py          # WebFetch + WebSearch (optional)
│       │   ├── task.py         # Sub-agent spawning (optional)
│       │   └── manager.py      # Tool registry + dispatch
│       ├── mcp/
│       │   ├── client.py       # MCP client implementation
│       │   ├── manager.py      # Multi-server management
│       │   └── tool_search.py  # Progressive tool loading
│       ├── skills/
│       │   ├── loader.py       # SKILL.md parser + loader
│       │   └── manager.py      # Skill lifecycle management
│       ├── permissions/
│       │   ├── manager.py      # Permission evaluation
│       │   └── rules.py        # Deny/allow/ask rules
│       ├── hooks/
│       │   ├── manager.py      # Hook execution engine
│       │   └── events.py       # Hook event types
│       ├── memory/
│       │   ├── auto.py         # Auto-memory persistence
│       │   └── project.py      # HARNESS.md loading
│       ├── agents/
│       │   ├── registry.py     # Sub-agent definitions
│       │   └── manager.py      # Sub-agent lifecycle
│       ├── ui/
│       │   ├── terminal.py     # Rich terminal UI
│       │   ├── streaming.py    # Streaming output handler
│       │   └── diff.py         # Diff display for edits
│       └── cli/
│           ├── main.py         # CLI entry point
│           ├── commands.py     # CLI commands
│           └── config.py       # CLI configuration
├── tests/
│   ├── unit/
│   ├── integration/
│   └── eval/                   # Evaluation harness
│       ├── swe_bench.py
│       ├── terminal_bench.py
│       └── harness_bench.py    # Our custom benchmark
└── skills/                     # Built-in skills
    ├── commit/SKILL.md
    ├── review-pr/SKILL.md
    └── debug/SKILL.md
```

---

## 2. SDK API Design

### Primary API: `harness.run()`

```python
import harness

# Minimal usage — works out of the box
async for msg in harness.run("Fix the bug in auth.py"):
    print(msg)

# Full configuration
async for msg in harness.run(
    prompt="Fix the bug in auth.py",
    provider="anthropic",           # or "openai", "google", "ollama"
    model="claude-sonnet-4-6",      # model identifier
    tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    mcp_servers={
        "postgres": {"command": "mcp-postgres", "args": ["--conn", "..."]},
    },
    skills_dir=".harness/skills",
    permission_mode="accept_edits",
    hooks=[
        Hook(event="post_tool_use", matcher="Edit|Write", command="ruff format {file}"),
    ],
    cwd="/path/to/project",
    session_id=None,                # None = new session, str = resume
    max_turns=100,
    system_prompt=None,             # Override system prompt
):
    match msg:
        case harness.TextMessage(text=text):
            print(text)
        case harness.ToolUse(name=name, args=args):
            print(f"Using tool: {name}")
        case harness.ToolResult(content=content):
            print(f"Tool result: {content[:100]}")
        case harness.Result(text=text):
            print(f"Final: {text}")
```

### Message Types

```python
from dataclasses import dataclass

@dataclass
class TextMessage:
    """Streaming text from the model."""
    text: str
    is_partial: bool = False

@dataclass
class ToolUse:
    """Model requested a tool call."""
    id: str
    name: str
    args: dict

@dataclass
class ToolResult:
    """Result of tool execution."""
    tool_use_id: str
    content: str
    display: str | None
    is_error: bool

@dataclass
class Result:
    """Final result of agent execution."""
    text: str
    session_id: str
    total_tokens: int
    total_cost: float
    tool_calls: int
    turns: int

@dataclass
class CompactionEvent:
    """Context was compacted."""
    tokens_before: int
    tokens_after: int

@dataclass
class SystemEvent:
    """System-level events (init, error, etc.)."""
    type: str
    data: dict
```

### Sub-Agent API

```python
# Define custom sub-agents
async for msg in harness.run(
    prompt="Review this codebase for security issues",
    agents={
        "security-scanner": harness.AgentDef(
            description="Scans code for OWASP top 10 vulnerabilities",
            system_prompt="You are a security expert...",
            tools=["Read", "Grep", "Glob"],
            model="claude-haiku-4-5",  # Use cheaper model
        ),
        "dependency-checker": harness.AgentDef(
            description="Checks dependencies for known CVEs",
            system_prompt="You analyze package dependencies...",
            tools=["Read", "Bash"],
        ),
    },
):
    print(msg)
```

### Session Management

```python
# Start a new session
session_id = None
async for msg in harness.run("Analyze the auth module", session_id=session_id):
    if isinstance(msg, harness.SystemEvent) and msg.type == "init":
        session_id = msg.data["session_id"]

# Resume later with full context
async for msg in harness.run("Now fix the bug you found", session_id=session_id):
    print(msg)

# Fork for alternative approach
async for msg in harness.run(
    "Try a different approach",
    session_id=session_id,
    fork=True,  # Creates new session branching from this point
):
    print(msg)
```

### Low-Level Client

```python
# For advanced use cases
async with harness.Client(
    provider="anthropic",
    model="claude-opus-4-6",
    tools=["Read", "Write", "Edit", "Bash"],
) as client:
    await client.send("Fix the authentication bug")

    async for msg in client.stream():
        # Full control over message handling
        process(msg)

    # Send follow-up
    await client.send("Now add tests")
    async for msg in client.stream():
        process(msg)
```

---

## 3. CLI Design

### Command Structure

```bash
# Interactive mode (default)
harness

# One-shot mode
harness "Fix the bug in auth.py"

# With specific provider/model
harness --provider anthropic --model claude-sonnet-4-6 "Fix the bug"
harness --provider openai --model gpt-5.1 "Fix the bug"
harness --provider google --model gemini-3-pro "Fix the bug"
harness --provider ollama --model llama-3.3 "Fix the bug"

# Resume session
harness --resume <session-id>

# Configuration
harness config set default_provider anthropic
harness config set default_model claude-sonnet-4-6
harness config list

# Model management
harness models list                    # List available models
harness models set <provider/model>    # Set default
harness models test <provider/model>   # Test connection

# Session management
harness sessions list
harness sessions show <id>
harness sessions delete <id>

# Skills management
harness skills list
harness skills search <query>
harness skills install <name>

# MCP management
harness mcp list                       # List connected servers
harness mcp add <name> <command>       # Add MCP server
harness mcp remove <name>

# Project initialization
harness init                           # Generate HARNESS.md

# Slash commands (in interactive mode)
/help                                  # Show help
/compact                               # Force context compaction
/model <name>                          # Switch model mid-session
/clear                                 # Clear conversation
/cost                                  # Show token usage and cost
/diff                                  # Show pending changes
/undo                                  # Revert last edit
```

### Configuration File: `HARNESS.md`

```markdown
# Project: My App

## Build & Test
- Build: `uv run pytest`
- Lint: `ruff check .`
- Format: `ruff format .`

## Architecture
- Python 3.12+ with uv
- FastAPI backend in src/api/
- React frontend in frontend/
- PostgreSQL database

## Conventions
- Use type hints everywhere
- Write tests for new features
- Keep functions under 50 lines
```

### Configuration Hierarchy

```
~/.harness/config.toml      # Global config (default provider, model, etc.)
~/.harness/memory/           # Auto-memory across sessions
~/.harness/skills/           # Global skills
.harness/config.toml         # Project-local config
.harness/skills/             # Project-local skills
HARNESS.md                   # Project instructions (loaded into context)
```

### Terminal UI

```
┌─ Harness ─── claude-sonnet-4-6 ─── tokens: 12.4k ─── $0.03 ───┐
│                                                                  │
│  You: Fix the authentication bug in src/auth.py                  │
│                                                                  │
│  ▶ Reading src/auth.py...                                       │
│  ▶ Searching for related tests...                               │
│  ▶ Editing src/auth.py (line 42-48)                             │
│    - token = jwt.decode(raw, key)                               │
│    + token = jwt.decode(raw, key, algorithms=["HS256"])         │
│  ▶ Running tests...                                            │
│  ✓ All 23 tests passed                                          │
│                                                                  │
│  Fixed the JWT decode vulnerability by specifying the algorithm. │
│  Without explicit algorithm, jwt.decode accepts any algorithm    │
│  including 'none', which is a known security issue.              │
│                                                                  │
│  > _                                                             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Implementation Phases

### Phase 1: Core Engine (Week 1-2)

**Goal**: Basic agent loop working with one provider.

- [ ] Provider adapter protocol + Anthropic adapter
- [ ] Core agent loop with tool dispatch
- [ ] 4 core tools: Read, Write, Edit, Bash
- [ ] Basic session persistence (JSONL)
- [ ] Minimal CLI (interactive + one-shot)
- [ ] Basic terminal output (no fancy UI yet)

**Milestone**: `harness "Fix the typo in README.md"` works with Claude.

### Phase 2: Multi-Provider + Search Tools (Week 3-4)

**Goal**: Support all major providers, add search tools.

- [ ] OpenAI adapter (covers GPT + compatible APIs)
- [ ] Google adapter (Gemini)
- [ ] Ollama adapter (local models)
- [ ] Model registry with 50+ models
- [ ] Glob tool (ripgrep-powered)
- [ ] Grep tool (ripgrep-powered)
- [ ] Context window management + compaction
- [ ] Configuration system (config files, env vars)

**Milestone**: `harness --provider openai "Refactor this function"` works.

### Phase 3: MCP + Skills (Week 5-6)

**Goal**: Full MCP client, skills system, permissions.

- [ ] MCP client (stdio + HTTP transports)
- [ ] MCP server manager (connect, list, call)
- [ ] Progressive tool loading (tool search)
- [ ] Skills loader (SKILL.md parser)
- [ ] Skill auto-detection and loading
- [ ] Permission system (deny/allow/ask rules)
- [ ] HARNESS.md loading and parsing
- [ ] Auto-memory system

**Milestone**: `harness` with MCP servers and custom skills working.

### Phase 4: Sub-Agents + Advanced Features (Week 7-8)

**Goal**: Sub-agent system, hooks, rich UI.

- [ ] Sub-agent spawning and management
- [ ] Parallel sub-agent execution
- [ ] Hook system (pre/post tool use)
- [ ] Session branching and forking
- [ ] Rich terminal UI (diffs, progress, token counter)
- [ ] WebFetch + WebSearch tools
- [ ] File checkpointing (undo/redo)
- [ ] Streaming channel for real-time steering

**Milestone**: Full-featured CLI with sub-agents and hooks.

### Phase 5: Evaluation + Polish (Week 9-10)

**Goal**: Benchmark against Claude Code, optimize performance.

- [ ] SWE-bench evaluation harness
- [ ] Terminal-Bench evaluation
- [ ] Custom Harness-Bench (our benchmark)
- [ ] Performance profiling and optimization
- [ ] Token efficiency optimization
- [ ] Documentation
- [ ] PyPI package publication
- [ ] GitHub Actions CI/CD

**Milestone**: Published benchmarks showing competitive performance.

---

## 5. Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python 3.12+ | Broadest SDK reach, async-native, type hints |
| **Package Manager** | uv | Fast, modern, user preference |
| **LLM SDKs** | anthropic, openai, google-genai | Official SDKs for each provider |
| **MCP Client** | mcp (official Python SDK) | Standard protocol implementation |
| **File Search** | ripgrep (vendored binary) | 10-100x faster than Python alternatives |
| **Terminal UI** | Rich + Textual | Beautiful terminal output, diff display |
| **CLI Framework** | Click | Simple, well-tested, composable |
| **Config Format** | TOML | Human-readable, Python-native |
| **Session Format** | JSONL | Append-only, streamable, human-readable |
| **Testing** | pytest + pytest-asyncio | Standard Python testing |
| **Type Checking** | pyright | Strict type safety |
| **Linting** | ruff | Fast, comprehensive |

### Dependencies (Minimal)

```toml
[project]
dependencies = [
    "anthropic>=0.40",     # Claude provider
    "openai>=1.50",        # OpenAI + compatible providers
    "google-genai>=1.0",   # Gemini provider
    "mcp>=1.0",            # MCP client
    "rich>=13.0",          # Terminal UI
    "click>=8.0",          # CLI framework
    "anyio>=4.0",          # Async runtime
    "httpx>=0.27",         # HTTP client
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "pyright", "ruff"]
eval = ["swebench", "datasets"]
```

---

## 6. System Prompt Strategy

Following pi-mono's philosophy: **keep it under 1,000 tokens**.

```python
SYSTEM_PROMPT = """You are Harness, a coding agent. You help users with software engineering tasks.

## Tools
Use the provided tools to accomplish tasks. Prefer dedicated tools over bash:
- Read files with Read (not cat)
- Edit files with Edit (not sed)
- Search files with Glob/Grep (not find/grep)
- Only use Bash for commands that require shell execution

## Workflow
1. Understand the request
2. Gather context (read files, search code)
3. Make changes (edit files, run commands)
4. Verify results (run tests, check output)

## Guidelines
- Read files before modifying them
- Make minimal, focused changes
- Run tests after making changes
- Explain what you did and why

{project_config}
{active_skills}
"""
```

**Key design choices**:
- < 1,000 tokens total (including project config and skills)
- No extensive tool descriptions (models understand tools via schema)
- Focus on behavior guidelines, not tool enumeration
- Project config injected from HARNESS.md
- Active skills injected on-demand

---

## 7. Provider-Specific Optimizations

### Anthropic (Claude)
- Use extended thinking for complex tasks
- Leverage prompt caching for repeated system prompts
- Use haiku for sub-agent routing, opus for complex reasoning
- Convert thinking traces to `<thinking>` tags for cross-provider compatibility

### OpenAI (GPT)
- Use structured outputs for tool calling
- Leverage function calling with strict mode
- Use o3/o4 reasoning models for complex tasks
- Use gpt-4o-mini for sub-agents

### Google (Gemini)
- Use grounding for web search tasks
- Leverage 2M token context for large codebases
- Use Flash models for sub-agents

### Local (Ollama/vLLM)
- Detect available models automatically
- Adjust tool calling format for model capabilities
- Fall back to text-based tool calling if native not supported

---

## 8. Key Differentiators

### vs Claude Code
- **Multi-provider**: Works with any LLM, not just Claude
- **Open source**: MIT license, fully transparent
- **Python SDK**: Native Python library, not just CLI
- **Customizable**: Full control over system prompt, tools, and behavior

### vs pi-mono
- **More tools**: 6 core + MCP + skills (vs 4)
- **Python-native**: SDK for Python ecosystem (vs TypeScript)
- **Sub-agents**: Built-in multi-agent support
- **Permission system**: Layered security (vs YOLO mode)
- **Hooks**: Pre/post tool execution hooks

### vs Aider
- **Agent-native**: Full agentic loop (vs pair programming)
- **MCP support**: Standard tool protocol
- **Sub-agents**: Parallel specialist agents
- **SDK**: Programmable library, not just CLI
- **Skills**: Extensible capability system

### vs Goose
- **Python-native**: SDK for Python ecosystem (vs Rust)
- **Proven architecture**: Based on Claude Code patterns
- **Benchmark-driven**: Performance validated via SWE-bench
- **Simpler**: Direct tool system + MCP (vs everything-is-MCP)
