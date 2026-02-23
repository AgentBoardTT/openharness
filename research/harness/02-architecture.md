# 02 - Deep Architecture Analysis

## Reference Architecture Comparison

This document analyzes the internal architecture of the three primary reference implementations to inform our design.

---

## 1. Agent Loop Patterns

### pi-mono: Minimal Loop
```
User Input → LLM Call → Tool Calls? → Execute Tools → Feed Results → Repeat
                          ↓ No
                        Response to User
```
- Single-threaded, synchronous loop
- No real-time steering (simpler but less interactive)
- Tool results split between LLM consumption and UI display
- Session stored as JSONL append-only DAG

### Claude Code: Master Loop (nO) + Steering Queue (h2A)
```
User Input ──→ Agent Loop (nO) ──→ LLM Call ──→ Tool Execution ──→ Loop
                    ↑                                                  |
                    └──── h2A Queue (real-time user interjection) ─────┘
```
- Single-threaded master loop with **async steering queue**
- h2A queue: dual-buffer, >10k msg/sec, zero-latency
- User can inject instructions mid-task without restart
- Three blended phases: gather → action → verify

### Anthropic Agent SDK: Async Iterator Loop
```python
async for message in query(prompt, options):
    # Stream of typed messages
    # SystemMessage → AssistantMessage → (ToolUse → ToolResult)* → ResultMessage
```
- Async-native via anyio/asyncio
- Typed message stream (7+ message types)
- Stop reasons: end_turn, tool_use, max_tokens, stop_sequence
- Context compaction via CompactBoundaryMessage

### Our Design: Hybrid Loop

```
┌─────────────────────────────────────────────┐
│                Agent Loop                    │
│                                             │
│  User Input ─→ Context Assembly             │
│                     ↓                       │
│              LLM Call (streaming)            │
│                     ↓                       │
│              Tool Dispatch                   │
│              ├─ Built-in tools              │
│              ├─ MCP tools                   │
│              └─ Skill-provided tools        │
│                     ↓                       │
│              Result Integration              │
│                     ↓                       │
│              Continue / Stop decision        │
│                                             │
│  ← Steering Channel (user interjection) ←   │
└─────────────────────────────────────────────┘
```

**Design choices**:
- Async iterator API (like Agent SDK) — `async for msg in harness.run(prompt):`
- Steering channel (like h2A) — enable mid-task user input
- Tool result splitting (like pi-mono) — separate LLM data from UI data
- Typed message stream — strongly typed events

---

## 2. Provider Abstraction Patterns

### pi-mono: Wire Protocol Normalization (4 protocols)

```
Provider Layer
├── OpenAI Completions API adapter
├── OpenAI Responses API adapter
├── Anthropic Messages API adapter
└── Google Generative AI API adapter

Each adapter:
- Normalizes request format
- Normalizes response format
- Normalizes streaming events
- Normalizes tool calling format
- Handles provider-specific auth
```

**Model catalogue**: 300+ models auto-generated from models.dev + OpenRouter metadata.

**Key insight**: Most providers speak OpenAI-compatible API. Only Anthropic and Google have truly distinct protocols.

### Aider: LiteLLM-based Abstraction

Aider uses [LiteLLM](https://github.com/BerriAI/litellm) for provider abstraction:
- 100+ providers through a single interface
- Handles auth, rate limits, retries
- Translates tool calling across providers
- Heavy dependency but comprehensive coverage

### Our Design: Lightweight Protocol Adapters

```python
class ProviderAdapter(Protocol):
    """Normalize any LLM provider to a common interface."""

    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        model: str,
        stream: bool = True,
    ) -> AsyncIterator[StreamEvent]:
        """Send messages and get streaming response with tool calls."""
        ...

    def format_tool_result(self, tool_use_id: str, result: ToolResult) -> Message:
        """Format tool result for this provider's expected format."""
        ...

# Implementations
class OpenAIAdapter(ProviderAdapter): ...      # OpenAI + all compatible APIs
class AnthropicAdapter(ProviderAdapter): ...    # Claude family
class GoogleAdapter(ProviderAdapter): ...       # Gemini family

# Provider registry
providers = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "google": GoogleAdapter,
    "ollama": OpenAIAdapter,     # OpenAI-compatible
    "groq": OpenAIAdapter,       # OpenAI-compatible
    "openrouter": OpenAIAdapter, # OpenAI-compatible
}
```

**Key differences from pi-mono**:
- Python instead of TypeScript (for broader SDK adoption)
- Simpler adapter interface (3 methods vs full protocol normalization)
- Model registry as data file, not code-generated

---

## 3. Tool System Architecture

### Claude Code: Rich Built-in Tools (9+)

```
File Operations:  Read, Write, Edit, MultiEdit
Search:           Glob (ripgrep), Grep (ripgrep)
Execution:        Bash (persistent session)
Web:              WebFetch, WebSearch
Planning:         TodoWrite/TodoRead, Task
Code Intelligence: LSP (go-to-def, find-refs, hover)
```

### pi-mono: Minimal Core (4 tools)

```
Core:     read, write, edit, bash
Optional: grep, find, ls
Custom:   via registerTool() with TypeBox schemas
```

### Our Design: Core 6 + Extensible

```python
# Core tools (always available):
CORE_TOOLS = [
    ReadTool,       # Read file contents with line control
    WriteTool,      # Create/overwrite files
    EditTool,       # Surgical string replacement
    BashTool,       # Shell execution with persistent session
    GlobTool,       # Fast file pattern matching (ripgrep)
    GrepTool,       # Content search with regex (ripgrep)
]

# Optional built-in tools (loaded on demand):
OPTIONAL_TOOLS = [
    WebFetchTool,   # Fetch and analyze web content
    WebSearchTool,  # Search the web
    TaskTool,       # Spawn sub-agents
]

# MCP tools: discovered at runtime from configured servers
# Skill tools: loaded from SKILL.md files when relevant
```

### Tool Definition Interface

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema

@dataclass
class ToolResult:
    content: str          # For LLM consumption
    display: str | None   # For UI display (optional, separate from LLM data)
    is_error: bool = False

class Tool(Protocol):
    """Base tool interface."""

    @property
    def definition(self) -> ToolDef: ...

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult: ...

@dataclass
class ToolContext:
    """Runtime context available to tools."""
    cwd: str
    session_id: str
    permissions: PermissionManager
    emit: Callable  # Emit events to UI
```

### Tool Permission System

Inspired by Claude Code's layered approach:

```
1. Deny rules      → Block regardless (e.g., rm -rf /)
2. Allow rules     → Permit if matched (e.g., git status)
3. Ask rules       → Prompt user (e.g., git push)
4. Permission mode → Global behavior (default/accept/plan/bypass)
5. Hook callback   → Custom runtime logic
```

```python
class PermissionMode(Enum):
    DEFAULT = "default"           # Ask for everything
    ACCEPT_EDITS = "accept_edits" # Auto-approve file ops
    PLAN = "plan"                 # Read-only, no execution
    BYPASS = "bypass"             # Full access (dangerous)

@dataclass
class PermissionConfig:
    mode: PermissionMode = PermissionMode.DEFAULT
    deny: list[str] = field(default_factory=list)   # Regex patterns
    allow: list[str] = field(default_factory=list)   # Regex patterns
    ask: list[str] = field(default_factory=list)     # Regex patterns
```

---

## 4. MCP Integration Architecture

### Protocol Overview

MCP (Model Context Protocol) defines three capability types:

| Capability | Description | Analog |
|------------|-------------|--------|
| **Tools** | Functions the LLM can call | Tool calling |
| **Resources** | Read-only data the LLM can reference | Context/files |
| **Prompts** | Reusable prompt templates | System prompt fragments |

### Transport Mechanisms

| Transport | Use Case | Protocol |
|-----------|----------|----------|
| **stdio** | Local process spawned by client | stdin/stdout JSON-RPC |
| **Streamable HTTP** | Remote servers | HTTP with SSE |
| **SSE** | Legacy remote servers | Server-Sent Events |

### Our MCP Client Design

```python
class MCPManager:
    """Manages connections to MCP servers."""

    async def connect(self, name: str, config: MCPServerConfig) -> None:
        """Connect to an MCP server."""
        if config.transport == "stdio":
            transport = StdioTransport(config.command, config.args)
        elif config.transport == "http":
            transport = HTTPTransport(config.url)
        self.servers[name] = await MCPClient(transport).connect()

    async def list_tools(self) -> list[ToolDef]:
        """Aggregate tools from all connected servers."""
        tools = []
        for name, server in self.servers.items():
            for tool in await server.list_tools():
                tools.append(ToolDef(
                    name=f"mcp__{name}__{tool.name}",
                    description=tool.description,
                    parameters=tool.input_schema,
                ))
        return tools

    async def call_tool(self, name: str, args: dict) -> ToolResult:
        """Route tool call to appropriate MCP server."""
        server_name, tool_name = self._parse_tool_name(name)
        result = await self.servers[server_name].call_tool(tool_name, args)
        return ToolResult(content=result.content, display=None)
```

### Progressive Tool Loading (Context Optimization)

When total MCP tool descriptions exceed 10% of context window:

```python
class ToolSearch:
    """On-demand tool discovery to save context tokens."""

    def __init__(self, all_tools: list[ToolDef]):
        self.index = self._build_search_index(all_tools)
        self.loaded_tools: set[str] = set()

    async def search(self, query: str, max_results: int = 5) -> list[ToolDef]:
        """Find tools matching query, load them into active set."""
        matches = self._search_index(query, max_results)
        for tool in matches:
            self.loaded_tools.add(tool.name)
        return matches

    def get_active_tools(self) -> list[ToolDef]:
        """Only return tools that have been explicitly loaded."""
        return [t for t in self.all_tools if t.name in self.loaded_tools]
```

---

## 5. Session & Context Management

### Session Storage: Append-Only JSONL DAG

Inspired by pi-mono's approach:

```python
@dataclass
class SessionEntry:
    id: str
    parent_id: str | None  # Enables branching
    timestamp: float
    type: str               # "user", "assistant", "tool_use", "tool_result", "system"
    content: Any
    metadata: dict | None = None

class Session:
    """Append-only DAG session with branching and compaction."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: list[SessionEntry] = []

    def append(self, entry: SessionEntry) -> None:
        """Append entry and persist to JSONL."""
        self.entries.append(entry)
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def branch(self, from_entry_id: str) -> str:
        """Create a new branch from a specific entry."""
        branch_id = generate_id()
        # New entries will have parent_id pointing to from_entry_id
        return branch_id

    def compact(self, keep_recent: int = 10) -> None:
        """Summarize old entries, keep recent ones."""
        old = self.entries[:-keep_recent]
        recent = self.entries[-keep_recent:]
        summary = self._summarize(old)
        self.entries = [summary] + recent
        self._rewrite_file()
```

### Context Window Management

```
┌─────────────── 200K Token Context ──────────────┐
│                                                   │
│  System Prompt (< 1K tokens)                     │
│  ├── Core instructions                           │
│  ├── Project config (HARNESS.md)                 │
│  └── Active skill instructions                   │
│                                                   │
│  Tool Definitions (dynamic)                       │
│  ├── Core tools (~500 tokens)                    │
│  ├── Loaded MCP tools (on-demand)                │
│  └── Skill tools (on-demand)                     │
│                                                   │
│  Conversation History (managed)                   │
│  ├── Compacted summary (if needed)               │
│  ├── Recent messages (preserved)                 │
│  └── Tool results (pruned if old)                │
│                                                   │
│  ──── 33K Buffer ────                            │
│  (Trigger compaction at 167K)                    │
│                                                   │
└───────────────────────────────────────────────────┘
```

### Context Compaction Strategy

```python
class ContextManager:
    COMPACTION_THRESHOLD = 0.85  # Compact at 85% of context window
    BUFFER_TOKENS = 33_000

    async def should_compact(self, messages: list, model: str) -> bool:
        total = self._count_tokens(messages)
        limit = self._get_context_limit(model)
        return total > (limit - self.BUFFER_TOKENS)

    async def compact(self, messages: list, model: str) -> list:
        """Summarize old messages, preserve recent context."""
        # 1. Identify compaction boundary
        recent_count = self._find_safe_boundary(messages)
        old = messages[:-recent_count]
        recent = messages[-recent_count:]

        # 2. Generate summary of old messages
        summary = await self._summarize_messages(old, model)

        # 3. Replace old messages with summary
        return [{"role": "system", "content": summary}] + recent
```

---

## 6. Skills System Architecture

### AgentSkills Standard Format (compatible with Claude Code)

```
.harness/skills/
├── code-review/
│   └── SKILL.md
├── deploy/
│   └── SKILL.md
└── test-runner/
    └── SKILL.md
```

### SKILL.md Format

```yaml
---
name: code-review
description: Expert code review with security and quality checks
emoji: 🔍
user-invocable: true
os: [darwin, linux]
---

## Instructions

When asked to review code, follow these steps:
1. Read the files to be reviewed
2. Check for security vulnerabilities (OWASP top 10)
3. Check for code quality issues
4. Provide actionable feedback with line references
```

### Skill Loading Strategy (Progressive Disclosure)

```python
class SkillManager:
    def __init__(self, skill_dirs: list[Path]):
        self.skills: dict[str, Skill] = {}
        self._load_metadata_only(skill_dirs)  # Load frontmatter, not full content

    def get_skill_descriptions(self) -> str:
        """Return compact descriptions for system prompt (~100 tokens total)."""
        return "\n".join(
            f"- {s.name}: {s.description}" for s in self.skills.values()
        )

    def load_skill(self, name: str) -> str:
        """Load full skill content when model requests it."""
        skill = self.skills[name]
        return skill.full_content  # Full markdown instructions

    def get_active_skills(self, context: str) -> list[Skill]:
        """Auto-detect relevant skills based on current context."""
        # Model decides which skills to activate based on descriptions
        return [s for s in self.skills.values() if s.auto_invoke]
```

---

## 7. Sub-Agent Architecture

### Design Pattern

```python
@dataclass
class AgentDef:
    name: str
    description: str           # When to use this agent
    system_prompt: str         # Specialized instructions
    tools: list[str]           # Allowed tools (subset of parent)
    model: str | None = None   # Override model (e.g., use haiku for simple tasks)
    max_turns: int = 50

class SubAgentManager:
    async def spawn(self, agent_def: AgentDef, prompt: str) -> AsyncIterator[Message]:
        """Spawn a sub-agent with isolated context."""
        # 1. Create fresh context (no parent history)
        # 2. Apply agent-specific system prompt
        # 3. Filter tools to allowed set
        # 4. Run agent loop
        # 5. Return result summary to parent
        async for msg in self.harness.run(
            prompt=prompt,
            system_prompt=agent_def.system_prompt,
            tools=agent_def.tools,
            model=agent_def.model,
            max_turns=agent_def.max_turns,
        ):
            yield msg
```

### Parallel Execution

```python
# Parent agent can spawn multiple sub-agents concurrently
async def handle_task_tool(self, args: dict) -> ToolResult:
    agent_type = args["subagent_type"]
    prompt = args["prompt"]

    agent_def = self.agent_registry[agent_type]
    result_parts = []

    async for msg in self.sub_agent_manager.spawn(agent_def, prompt):
        if isinstance(msg, ResultMessage):
            result_parts.append(msg.result)

    return ToolResult(
        content="\n".join(result_parts),
        display=f"Sub-agent '{agent_type}' completed",
    )
```

### Context Isolation

Each sub-agent gets:
- **Fresh context window** — no parent conversation history
- **Own system prompt** — specialized for its role
- **Filtered tools** — only what it needs
- **Optional model override** — use cheaper model for simple tasks
- **Independent token budget** — doesn't consume parent's context

---

## 8. Hook System

### Lifecycle Events

```python
class HookEvent(Enum):
    PRE_TOOL_USE = "pre_tool_use"       # Before tool execution
    POST_TOOL_USE = "post_tool_use"     # After tool execution
    SESSION_START = "session_start"     # Session initialization
    SESSION_END = "session_end"         # Session cleanup
    USER_PROMPT = "user_prompt"         # User submits prompt
    AGENT_STOP = "agent_stop"           # Agent decides to stop

@dataclass
class HookConfig:
    event: HookEvent
    matcher: str | None = None  # Regex for tool name matching
    command: str | None = None  # Shell command to run
    callback: Callable | None = None  # Python callback

@dataclass
class HookResult:
    action: str = "continue"  # "continue", "deny", "modify"
    reason: str | None = None
    modified_input: dict | None = None  # For input transformation
```

### Hook Execution

```python
class HookManager:
    async def run_hooks(self, event: HookEvent, context: dict) -> HookResult:
        """Run all matching hooks for an event."""
        results = []
        matching_hooks = [h for h in self.hooks if h.event == event]

        if event in (HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE):
            tool_name = context.get("tool_name", "")
            matching_hooks = [
                h for h in matching_hooks
                if h.matcher is None or re.match(h.matcher, tool_name)
            ]

        # Run all matching hooks in parallel
        tasks = [self._execute_hook(h, context) for h in matching_hooks]
        results = await asyncio.gather(*tasks)

        # Deny takes precedence
        for r in results:
            if r.action == "deny":
                return r

        return HookResult(action="continue")
```

### Common Hook Patterns

```python
# Auto-format after code edits
HookConfig(
    event=HookEvent.POST_TOOL_USE,
    matcher="Edit|Write",
    command="ruff format {file_path}",
)

# Block dangerous commands
HookConfig(
    event=HookEvent.PRE_TOOL_USE,
    matcher="Bash",
    callback=lambda ctx: HookResult(
        action="deny" if "rm -rf" in ctx["args"].get("command", "") else "continue"
    ),
)

# Audit logging
HookConfig(
    event=HookEvent.POST_TOOL_USE,
    matcher=".*",
    callback=lambda ctx: log_to_audit(ctx),
)
```
