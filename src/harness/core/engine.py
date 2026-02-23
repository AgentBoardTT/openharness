"""Engine: wires providers + tools + session + config into a running agent."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from harness.core.config import load_harness_md, resolve_api_key
from harness.core.loop import AgentLoop
from harness.core.session import Session
from harness.permissions.manager import PermissionManager
from harness.permissions.rules import PermissionConfig
from harness.types.config import PermissionMode, RunConfig
from harness.types.hooks import Hook
from harness.types.messages import Message
from harness.types.providers import ProviderAdapter


async def run(
    prompt: str,
    *,
    provider: str = "anthropic",
    model: str | None = None,
    tools: list[str] | None = None,
    mcp_servers: dict[str, Any] | None = None,
    permission_mode: str | PermissionMode = "default",
    permission_rules: PermissionConfig | None = None,
    session_id: str | None = None,
    max_turns: int = 100,
    max_tokens: int = 16384,
    cwd: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    hooks: list[Hook] | None = None,
    interactive: bool = False,
    approval_callback: Any | None = None,
    steering: Any | None = None,
    _provider: ProviderAdapter | None = None,
    **kwargs: Any,
) -> AsyncIterator[Message]:
    """Run the Harness agent loop.

    This is the primary SDK entry point.

    Args:
        prompt: The user's instruction.
        provider: Provider name ("anthropic", "openai", "google").
        model: Model ID or alias. If None, uses provider default.
        tools: List of tool names to enable. Defaults to core tools.
        mcp_servers: MCP server configurations (name -> config dict).
        permission_mode: Permission level for tool execution.
        permission_rules: Explicit permission rules (allow/deny).
        session_id: Resume an existing session, or None for new.
        max_turns: Maximum agent loop iterations.
        max_tokens: Max tokens per model response.
        cwd: Working directory for tools.
        api_key: Provider API key (or set via env var).
        base_url: Override provider base URL.
        system_prompt: Override default system prompt.
        hooks: List of Hook definitions for lifecycle events.
        interactive: Whether to enable interactive tools (e.g. AskUser).
        steering: A SteeringChannel for injecting messages between turns.
        _provider: Injected provider for testing (private).
    """
    # Resolve working directory
    resolved_cwd = str(Path(cwd).resolve()) if cwd else str(Path.cwd())

    # Resolve permission mode
    if isinstance(permission_mode, str):
        perm = PermissionMode(permission_mode)
    else:
        perm = permission_mode

    # Build config
    config = RunConfig(
        provider=provider,
        model=model,
        tools=tools or ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode=perm,
        session_id=session_id,
        max_turns=max_turns,
        max_tokens=max_tokens,
        cwd=resolved_cwd,
        system_prompt=system_prompt,
        api_key=api_key,
        base_url=base_url,
    )

    # Create permission manager
    perm_manager = PermissionManager(mode=perm, config=permission_rules)

    # Load project instructions (HARNESS.md)
    harness_md = load_harness_md(resolved_cwd)

    # Create or resume session
    session = Session(session_id=session_id, cwd=resolved_cwd)

    # Create provider
    if _provider is not None:
        adapter = _provider
    else:
        adapter = _create_provider(config)

    session.save_metadata(provider=config.provider, model=adapter.model_id)

    # Create tool instances
    tool_instances = _create_tools(config.tools)

    # Register additional tools
    _register_extra_tools(tool_instances, adapter, resolved_cwd, interactive=interactive)

    # Set up MCP if configured
    mcp_manager = None
    if mcp_servers:
        mcp_manager = await _setup_mcp(mcp_servers, tool_instances)

    # Set up hooks
    hook_manager = None
    if hooks:
        from harness.hooks.manager import HookManager

        hook_manager = HookManager(hooks)

    # Discover skills
    skill_summary = _discover_skills(resolved_cwd)

    # Build system prompt
    if not config.system_prompt:
        from harness.core.loop import SYSTEM_PROMPT
        parts = [SYSTEM_PROMPT.format(cwd=resolved_cwd)]
        if harness_md:
            parts.append(f"\n# Project Instructions\n\n{harness_md}")
        if skill_summary:
            parts.append(f"\n# {skill_summary}")
        config.system_prompt = "\n".join(parts)

    # Resolve context window from model info
    context_window = 200_000
    try:
        from harness.providers.registry import resolve_model
        model_info = resolve_model(adapter.model_id)
        context_window = model_info.context_window
    except (KeyError, ImportError):
        pass

    # Create and run loop
    loop = AgentLoop(
        provider=adapter,
        tools=tool_instances,
        config=config,
        session=session,
        context_window=context_window,
        permission_manager=perm_manager,
        mcp_manager=mcp_manager,
        hook_manager=hook_manager,
        steering=steering,
        approval_callback=approval_callback,
    )

    try:
        async for msg in loop.run(prompt):
            yield msg
    finally:
        # Clean up MCP connections
        if mcp_manager is not None:
            await mcp_manager.disconnect_all()


def _create_provider(config: RunConfig) -> ProviderAdapter:
    """Create a provider adapter from config."""
    from harness.providers.registry import create_provider, resolve_model

    model_id = config.model
    if model_id:
        model_info = resolve_model(model_id)
        model_id = model_info.id
    else:
        # Default model per provider
        defaults = {
            "anthropic": "claude-sonnet-4-6",
            "openai": "gpt-4o",
            "google": "gemini-2.0-flash",
            "ollama": "llama3.3",
        }
        model_id = defaults.get(config.provider, "claude-sonnet-4-6")

    api_key = resolve_api_key(config.provider, config.api_key)
    return create_provider(model_id, api_key=api_key, base_url=config.base_url)


def _create_tools(tool_names: list[str]) -> dict[str, Any]:
    """Create tool instances for the given names."""
    from harness.tools.manager import ToolManager

    manager = ToolManager()
    manager.register_defaults()

    result = {}
    for name in tool_names:
        tool = manager.get(name)
        if tool is not None:
            result[name] = tool
    return result


def _register_extra_tools(
    tool_instances: dict[str, Any],
    adapter: ProviderAdapter,
    cwd: str,
    *,
    interactive: bool = False,
) -> None:
    """Register additional tools (Task, WebFetch, AskUser, Checkpoint)."""
    from harness.agents.manager import AgentManager
    from harness.tools.checkpoint import CheckpointTool
    from harness.tools.question import QuestionTool
    from harness.tools.task import TaskTool
    from harness.tools.web import WebFetchTool

    # Sub-agent support via Task tool
    agent_manager = AgentManager(
        provider=adapter,
        tools=tool_instances,
        cwd=cwd,
    )
    tool_instances["Task"] = TaskTool(agent_manager)

    # Web fetch
    tool_instances["WebFetch"] = WebFetchTool()

    # Agent-initiated user questions
    tool_instances["AskUser"] = QuestionTool(interactive=interactive)

    # File checkpoints
    tool_instances["Checkpoint"] = CheckpointTool()


async def _setup_mcp(
    mcp_configs: dict[str, Any],
    tool_instances: dict[str, Any],
) -> Any:
    """Set up MCP servers and register ToolSearch if needed."""
    from harness.mcp.manager import MCPManager
    from harness.mcp.tool_search import ToolSearchTool
    from harness.types.config import MCPServerConfig

    manager = MCPManager()

    for name, cfg in mcp_configs.items():
        if isinstance(cfg, MCPServerConfig):
            server_config = cfg
        elif isinstance(cfg, dict):
            server_config = MCPServerConfig(**cfg)
        else:
            continue
        try:
            await manager.add_server(name, server_config)
        except Exception:
            pass  # Logged by MCPManager

    if manager.tool_count > 0:
        # Register ToolSearch meta-tool for progressive discovery
        tool_search = ToolSearchTool(manager)
        tool_instances["ToolSearch"] = tool_search

    return manager


def _discover_skills(cwd: str) -> str:
    """Discover skills and return a summary for the system prompt."""
    from harness.skills.manager import SkillManager

    manager = SkillManager(cwd=cwd)
    manager.discover()
    return manager.get_skill_summary()
