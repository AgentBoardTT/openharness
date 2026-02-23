# 01 - Market Landscape: Agent Harness Ecosystem

## Executive Summary

The coding agent harness market has consolidated around three major architectural patterns: **minimalist** (pi-mono/OpenClaw), **full-featured** (Claude Code/Agent SDK), and **multi-provider** (Aider, Goose, OpenHands). Our opportunity lies in combining the best of each: pi-mono's minimalism and multi-provider support with Claude Code's performance and tool sophistication.

---

## 1. OpenClaw (powered by pi-mono)

### Overview
- **GitHub**: github.com/openclaw/openclaw — **212k+ stars** (fastest-growing repo in GitHub history)
- **Engine**: pi-mono by Mario Zechner (github.com/badlogic/pi-mono — 14.6k stars)
- **License**: MIT
- **Language**: TypeScript (96.5%)
- **Contributors**: 753 (OpenClaw), 120+ (pi-mono)

### Architecture

OpenClaw is a **multi-channel AI assistant** (WhatsApp, Telegram, Slack, Discord, etc.) built on pi-mono's **minimal coding agent core**. For our purposes, pi-mono's architecture is more relevant.

#### pi-mono Package Stack
```
pi-ai          → Unified LLM API (16+ providers, 4 wire protocols)
pi-agent-core  → Minimal agent loop + tool execution + event streaming
pi-tui         → Custom terminal UI with differential rendering
pi-coding-agent → Full CLI wrapper with session management
```

#### OpenClaw Layer (on top of pi-mono)
```
Gateway Control Plane → WebSocket hub routing messages from all channels
Channel Adapters      → Normalize messaging platform quirks
Agent Runtime         → Wraps pi-agent-core with OpenClaw tools
Memory System         → SQLite + vector embeddings
Session Manager       → JSONL-based append-only DAGs
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **4 core tools only** (read, write, edit, bash) | Frontier models understand coding agents inherently; more tools = more tokens, not more capability |
| **System prompt < 1,000 tokens** | Efficiency: every token spent on system prompt is stolen from user context |
| **No built-in MCP** | MCP servers add 13-18k tokens per server; prefer self-extension model |
| **File-based workflows** | All artifacts live in files — version-controllable, human-readable |
| **Trust frontier models** | No need for extensive specialized tools or scaffolding |
| **Differential TUI rendering** | Only redraw changed terminal lines — flicker-free |
| **Sessions as append-only DAGs** | Enable branching, compaction, and restoration |

### LLM Provider Support (pi-ai)

pi-mono normalizes around **4 wire protocols** supporting 16+ providers:

| Protocol | Providers |
|----------|-----------|
| OpenAI Completions API | OpenAI, Azure, Groq, xAI, OpenRouter, Ollama, vLLM, LM Studio |
| OpenAI Responses API | OpenAI (newer endpoints) |
| Anthropic Messages API | Anthropic (Claude family) |
| Google Generative AI API | Google (Gemini family) |

**Model catalogue**: 300+ definitions auto-generated from models.dev and OpenRouter metadata.

### Tool System

```typescript
// Tools use TypeBox schemas for type safety
// Automatic validation via AJV
// Tool results split: LLM consumption vs UI display
registerTool({
  name: "read",
  schema: Type.Object({ path: Type.String() }),
  execute: async (args) => { /* ... */ }
})
```

**Core tools**: read, write, edit, bash
**Optional read-only**: grep, find, ls
**Extension tools**: Custom via `registerTool()` + TypeBox schemas

### Performance (Terminal-Bench 2.0)

pi-mono with Claude Opus 4.5 is **competitive with or exceeding Codex, Cursor, and Windsurf** — despite having fewer tools. This validates the minimalist philosophy.

### Key Takeaways for Our Project

1. **Minimalism works**: 4 tools + <1k system prompt matches bloated alternatives
2. **Multi-provider via wire protocol normalization** is the right abstraction
3. **TypeBox + AJV** for tool schema validation is elegant
4. **Append-only DAG sessions** enable branching without file proliferation
5. **Differential TUI rendering** is worth implementing

---

## 2. Anthropic Agent SDK

### Overview
- **GitHub**: anthropics/claude-agent-sdk-python (4.9k stars), anthropics/claude-agent-sdk-typescript
- **License**: MIT (code), Anthropic Commercial ToS (usage)
- **Language**: Python + TypeScript
- **Status**: Production-ready, actively maintained

### Architecture

The Agent SDK **exposes Claude Code's internal agent harness as a library**. Same engine, different interface.

```
┌─────────────────────────────┐
│   Claude Code (VS Code UI)  │  ← Interactive IDE interface
├─────────────────────────────┤
│   Agent Harness (Core)      │  ← Shared engine
├─────────────────────────────┤
│   Claude Agent SDK          │  ← Programmable library
├─────────────────────────────┤
│   Anthropic API / Bedrock   │  ← Model inference
└─────────────────────────────┘
```

### Core API

```python
from claude_agent_sdk import query, ClaudeAgentOptions

# Minimal usage — single function call
async for message in query(
    prompt="Fix the bug in auth.py",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
    ),
):
    if hasattr(message, "result"):
        print(message.result)
```

### Key Features

| Feature | Details |
|---------|---------|
| **Built-in Tools** | Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch, Task |
| **MCP Support** | Full — stdio, HTTP/SSE, in-process servers |
| **Sub-agents** | Parallel specialists via Task tool with context isolation |
| **Hooks** | PreToolUse, PostToolUse, Stop, SessionStart, SessionEnd, UserPromptSubmit |
| **Permissions** | 4 modes: default, acceptEdits, plan, bypassPermissions |
| **Sessions** | Persistent JSONL, resume/fork support, file checkpointing |
| **Context Compaction** | Automatic summarization when approaching limits |
| **Skills** | AgentSkills standard format (.claude/skills/SKILL.md) |

### Permission Evaluation Order
```
PreToolUse Hook → Deny Rules → Allow Rules → Ask Rules →
Permission Mode Check → canUseTool Callback → PostToolUse Hook
```

### Multi-Agent Pattern
```python
agents={
    "code-reviewer": AgentDefinition(
        description="Expert code reviewer",
        prompt="Analyze code quality and suggest improvements.",
        tools=["Read", "Glob", "Grep"],
    ),
    "security-auditor": AgentDefinition(
        description="Security vulnerability scanner",
        prompt="Find security issues.",
        tools=["Read", "Grep", "Bash"],
    ),
}
```

### Performance Impact

**Critical finding from CORE benchmark**:
- Opus 4.5 + Claude Code harness = **78%**
- Opus 4.5 + smolagents harness = **42%**
- **The harness contributes +36 percentage points** to agent performance

### Key Takeaways for Our Project

1. **`query()` as the primary API** — simple async iterator is the right abstraction
2. **Hook system** is powerful for extensibility without modifying core
3. **Permission layering** (deny → allow → ask → mode → callback) is well-designed
4. **AgentDefinition** for sub-agents is a clean pattern
5. **The harness matters enormously** — invest heavily in harness quality
6. **Claude-only limitation** — opportunity for multi-provider version

---

## 3. Claude Code (Reference Implementation)

### Overview
- **Technology**: Node.js + TypeScript, 10.5MB CLI
- **Runtime Components**: Vendored ripgrep, Tree-sitter WASM, React + Ink UI
- **Key Fact**: 90% of Claude Code is written by Claude itself

### Agent Loop (Master Loop "nO")

```
WHILE model_response.stop_reason == "tool_use":
    1. Execute tool call
    2. Feed result back to model
    3. Get next model decision
WHEN stop_reason != "tool_use":
    Loop terminates → return results to user
```

**Three-phase operation** (blended, not strict):
1. **Gather Context** — Read files, search patterns, run exploratory commands
2. **Take Action** — Execute edits, run tests
3. **Verify Results** — Check output, run tests again

**Real-time steering via h2A queue**:
- Dual-buffer implementation, >10k messages/second
- Users can inject instructions mid-task without restart
- Zero-latency message passing between components

### Tool Categories

| Category | Tools |
|----------|-------|
| File Operations | Read, Write, Edit, MultiEdit, NotebookRead/Edit |
| Search & Discovery | Glob, Grep, LS |
| Execution | Bash (persistent session) |
| Web & Research | WebFetch, WebSearch |
| Planning | TodoWrite/TodoRead, Task (sub-agents) |
| Code Intelligence | LSP (go-to-def, find-refs, hover docs, diagnostics) |

### Performance Optimizations

| Optimization | Impact |
|-------------|--------|
| **LSP integration** | 900x faster than text-based search (50ms vs 45s) |
| **Progressive skill loading** | Skills load on-demand, not at startup |
| **MCP tool search** | Dynamic loading when tools exceed 10% of context |
| **Context compaction** | 33K buffer, trigger at 167K tokens |
| **Prompt caching** | Reduces costs for repeated content |
| **Fast mode** | 2.5x faster output, same model |
| **Multi-model routing** | Opus for reasoning, Sonnet for code, Haiku for routine |

### Memory System
- **Auto Memory**: `~/.claude/projects/<project>/memory/` (first 200 lines loaded)
- **CLAUDE.md**: Project-specific instructions, loaded every session
- **Session Memory**: Automatic compaction/summarization

### Benchmarks

| Benchmark | Model | Score |
|-----------|-------|-------|
| SWE-bench Verified | Opus 4.5 | 80.9% |
| SWE-bench Verified | Sonnet 4.5 | 77.2% |
| Terminal-Bench 2.0 | Opus 4.6 | 65.4% |
| Scaled Tool Use | Opus | 62.3% (next: 43.8%) |

---

## 4. Competing Frameworks

### Aider (40.8k stars)
- **Type**: CLI pair programming tool
- **Language**: Python
- **Providers**: 100+ LLMs via LiteLLM (Claude, GPT, Gemini, DeepSeek, Ollama, OpenRouter)
- **Key Innovation**: Repository map — tree-sitter AST + PageRank graph-ranking of codebase symbols
- **Edit Formats**: 6 formats (whole, diff, diff-fenced, udiff, editor-diff, editor-whole) — auto-selects per model
- **Benchmark**: SWE-Bench Lite 26.3% SOTA (June 2024), Main SWE-Bench 18.9%
- **Token Usage**: ~15 billion tokens/week (indicating massive production adoption)
- **MCP**: Community-only (third-party servers, not built-in)
- **Strength**: Best multi-provider CLI tool, mature (40k+ stars), excellent repo mapping
- **Weakness**: No native MCP, no sub-agents, limited tool system

### Goose by Block (30.9k stars)
- **Type**: Extensible on-machine AI agent
- **Language**: Rust (58.9%) + TypeScript (33.4%)
- **Architecture**: Interface → Agent → Extensions (all via MCP)
- **Key Innovation**: Everything is an MCP server (even built-in tools)
- **Providers**: Anthropic, OpenAI, Gemini, OpenRouter, Groq, custom configs
- **Interfaces**: CLI + Desktop app
- **MCP**: Native first-class integration with built-in + custom servers
- **Strength**: MCP-first design, Rust core, concurrent agents, 400+ contributors
- **Weakness**: Less mature ecosystem, fewer benchmarks

### OpenHands (68.1k stars)
- **Type**: Full-featured coding agent platform (SDK + CLI + GUI)
- **Language**: Python (75.9%) + TypeScript (22%)
- **Architecture**: Modular workspace system — LocalWorkspace, DockerWorkspace, RemoteWorkspace
- **Providers**: Claude, GPT, Gemini
- **Benchmark**: SWE-Bench Verified **60.6%** SOTA (Nov 2025, with critic model), Multi-SWE-Bench Rank 1
- **Licensing**: MIT core + Commercial enterprise edition
- **Strength**: Most feature-rich, leading SWE-bench scores, Docker sandboxing
- **Weakness**: Heavy, cloud-focused, no native MCP

### Cline (4M+ users)
- **Type**: VS Code extension autonomous agent
- **Providers**: Anthropic, OpenAI, Gemini, AWS Bedrock, Azure, Vertex, OpenRouter, Cerebras, Groq, Ollama
- **Key Features**: Plan & Act mode separation, browser automation (headless Chrome), checkpoint system
- **MCP**: Native first-class integration
- **Strength**: VS Code integration, MCP marketplace, human-in-the-loop safety
- **Weakness**: VS Code-only, no CLI

### Cursor Agent
- **Type**: IDE-integrated coding agent (VS Code fork)
- **Key Innovation**: Parallel Agent Mode — up to 8 agents in git worktrees
- **Key Feature**: Auto-routing model selection, custom "Composer" model trained on action trajectories
- **MCP**: Native (1,800+ servers available)
- **Strength**: Parallel execution, fast (<30s per turn), auto model routing
- **Weakness**: Proprietary, IDE-only

### OpenAI Codex CLI
- **Type**: Multi-surface coding agent via App Server protocol
- **Architecture**: JSON-RPC over JSONL/stdio — one protocol serves CLI, VS Code, web, macOS, JetBrains, Xcode
- **Providers**: OpenAI models
- **MCP**: Rejected in favor of App Server protocol (MCP too tool-oriented for IDE semantics)
- **Strength**: Unified protocol across all surfaces, official OpenAI tool
- **Weakness**: OpenAI-only, rejected MCP standard

### smolagents (HuggingFace)
- **Type**: Lightweight agent framework (~1,000 lines of logic)
- **Key Innovation**: Code agents — agents write Python code to call tools (30% fewer steps than JSON tool-calling)
- **Providers**: 100+ via LiteLLM, Ollama, HF Inference
- **Sandbox**: E2B, Blaxel, Modal, Docker, Pyodide+Deno
- **Strength**: Simple, educational, multi-provider, code-based actions
- **Weakness**: Demonstrated 36% lower performance than Claude Code harness on CORE

### pydantic-ai (15k stars)
- **Type**: Type-safe agent framework ("FastAPI feeling for GenAI")
- **Language**: Python
- **Providers**: 20+ direct (OpenAI, Anthropic, Gemini, DeepSeek, Grok, Cohere, Mistral, Perplexity) + cloud platforms
- **Key Innovation**: Generic agents parameterized by dependency/output types, `@agent.tool` decorators
- **Features**: Structured output validation, dependency injection, Logfire observability, graph-based workflows
- **MCP**: Integrated support
- **Strength**: Type safety, IDE autocompletion, production-grade observability, massive provider support
- **Weakness**: SDK-only (no CLI), not specifically a coding agent

---

## 5. Competitive Positioning Matrix

| Feature | Claude Code | pi-mono | Aider | Goose | OpenHands | Cline | Cursor | **Harness (Ours)** |
|---------|-------------|---------|-------|-------|-----------|-------|--------|-------------------|
| Multi-provider | No (Claude) | Yes (16+) | Yes (100+) | Yes | Yes | Yes (10+) | Yes | **Yes (target)** |
| CLI | Yes | Yes | Yes | Yes | Yes | No | No | **Yes** |
| SDK | Yes | Yes | No | No | Yes | No | No | **Yes** |
| MCP native | Yes | No | Community | Yes | No | Yes | Yes (1800+) | **Yes** |
| Skills/plugins | Yes | Yes (extensions) | No | Yes (MCP) | No | Yes | Yes | **Yes** |
| Sub-agents | Yes | No | No | Yes | No | No | Yes (8) | **Yes** |
| Tool count | 9+ | 4 | 6 formats | MCP-based | 4+ | 4+ | N/A | **Core 6 + MCP** |
| SWE-bench | 80.9% | N/A | 26.3% (Lite) | N/A | 60.6% (Verified) | N/A | N/A | **Target: 70%+** |
| Open source | No | Yes (MIT) | Yes (MIT) | Yes (Apache) | Yes (MIT+Commercial) | Yes (MIT) | No | **Yes (MIT)** |
| Session persistence | Yes | Yes (JSONL DAG) | Git-based | Yes | Yes | Checkpoints | Yes | **Yes** |
| Context compaction | Yes | Yes | No | Yes | Yes | AST-based | Yes | **Yes** |
| Permission system | Sophisticated | YOLO | Basic | Basic | Basic | Human-in-loop | Basic | **Layered** |
| LSP integration | Yes | No | Tree-sitter | No | No | AST/ripgrep | Yes | **Yes (planned)** |
| Docker sandbox | No | No | No | Yes | Yes | No | Config | **Planned** |

---

## 6. Key Insights for Our Design

### What Works (Proven Patterns)
1. **Minimal core tools** (pi-mono) — 4-6 tools is the sweet spot
2. **Wire protocol normalization** (pi-mono) — abstract at protocol level, not provider level
3. **Async iterator API** (Agent SDK) — `query()` returning async stream is the right pattern
4. **Hook system** (Agent SDK) — extensibility without modifying core
5. **AgentSkills format** (Claude Code) — open standard for reusable capabilities
6. **Append-only DAG sessions** (pi-mono) — enable branching and compaction
7. **Progressive tool loading** (Claude Code) — load on demand to save context
8. **File checkpointing** (Agent SDK) — safety net for edits

### What to Avoid
1. **Over-engineering system prompts** — models already understand coding agents
2. **Too many built-in tools** — each tool costs tokens and adds complexity
3. **Provider-specific abstractions** — normalize at wire protocol level instead
4. **Ignoring harness quality** — the harness matters as much as the model (+36% on CORE)
5. **MCP as mandatory** — support it but don't require it (pi-mono's proxy pattern is smart)
6. **Cloud-only architecture** — must work fully local

### Our Unique Opportunity
- **Multi-provider** (like pi-mono) + **sophisticated harness** (like Claude Code)
- No one has combined minimalist multi-provider design with Claude Code-level tool sophistication
- The +36% harness effect means we can compete even without Claude-specific optimizations
