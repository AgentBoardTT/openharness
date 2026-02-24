"""Engine: wires providers + tools + session + config into a running agent."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from harness.core.config import load_harness_md, load_toml_config, resolve_api_key
from harness.core.loop import AgentLoop
from harness.core.session import Session
from harness.permissions.manager import PermissionManager
from harness.permissions.rules import PermissionConfig
from harness.types.config import (
    AuditConfig,
    PermissionMode,
    PolicyConfig,
    RouterConfigData,
    RunConfig,
    SandboxConfig,
)
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
    sandbox_mode: str | None = None,
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
        sandbox_mode: Override sandbox mode ("none", "process", "docker").
        _provider: Injected provider for testing (private).
    """
    # Resolve working directory
    resolved_cwd = str(Path(cwd).resolve()) if cwd else str(Path.cwd())

    # Resolve permission mode
    if isinstance(permission_mode, str):
        perm = PermissionMode(permission_mode)
    else:
        perm = permission_mode

    # Load TOML config for enterprise features
    toml_config = load_toml_config(resolved_cwd)

    # Parse enterprise config sections
    audit_config = _parse_audit_config(toml_config)
    policy_config = _parse_policy_config(toml_config)
    router_config = _parse_router_config(toml_config)
    sandbox_config = _parse_sandbox_config(toml_config, sandbox_mode)

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
        audit=audit_config,
        policy=policy_config,
        router=router_config,
        sandbox=sandbox_config,
    )

    # Create permission manager (with optional policy engine)
    policy_engine = _init_policy_engine(policy_config, resolved_cwd)
    perm_manager = PermissionManager(mode=perm, config=permission_rules, policy_engine=policy_engine)

    # Init observability if configured
    otel_configured = _init_observability(toml_config)

    # Init audit logger
    audit_logger = _init_audit_logger(audit_config, session_id)

    # Init sandbox executor
    sandbox_executor = _init_sandbox_executor(sandbox_config, resolved_cwd)

    # Load project instructions (HARNESS.md)
    harness_md = load_harness_md(resolved_cwd)

    # Create or resume session
    session = Session(session_id=session_id, cwd=resolved_cwd)

    # Create provider
    if _provider is not None:
        adapter = _provider
    else:
        adapter = _create_provider(config)

    # Wrap with router if configured
    adapter = _init_model_router(router_config, adapter)

    session.save_metadata(provider=config.provider, model=adapter.model_id)

    # Log session start
    if audit_logger and audit_logger.enabled:
        audit_logger.log_session_start(config.provider, adapter.model_id)

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
        audit_logger=audit_logger,
        sandbox_executor=sandbox_executor,
    )

    try:
        async for msg in loop.run(prompt):
            yield msg
    finally:
        # Log session end and close handle
        if audit_logger and audit_logger.enabled:
            audit_logger.log_session_end()
            audit_logger.close()

        # Enforce retention
        if audit_config and audit_config.enabled:
            try:
                from harness.audit.retention import RetentionPolicy
                retention = RetentionPolicy(
                    max_age_days=audit_config.retention_days,
                    max_size_mb=audit_config.retention_max_size_mb,
                )
                retention.enforce_retention()
            except Exception:
                pass

        # Shutdown OTel
        if otel_configured:
            try:
                from harness.observability.exporters import shutdown
                shutdown()
            except Exception:
                pass

        # Cleanup sandbox
        if sandbox_executor is not None:
            try:
                await sandbox_executor.cleanup()
            except Exception:
                pass

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


# ---------------------------------------------------------------------------
# Enterprise feature initialization helpers
# ---------------------------------------------------------------------------


def _parse_audit_config(toml: dict[str, Any]) -> AuditConfig | None:
    """Parse [audit] section from TOML config."""
    section = toml.get("audit")
    if not isinstance(section, dict):
        # Check env var fallback
        if os.environ.get("HARNESS_AUDIT_ENABLED", "").lower() == "true":
            return AuditConfig(enabled=True)
        return None
    return AuditConfig(
        enabled=section.get("enabled", False),
        scan_pii=section.get("scan_pii", True),
        retention_days=section.get("retention_days", 90),
        retention_max_size_mb=section.get("retention_max_size_mb", 0),
        log_tool_args=section.get("log_tool_args", True),
    )


def _parse_policy_config(toml: dict[str, Any]) -> PolicyConfig | None:
    """Parse [policy] section from TOML config."""
    section = toml.get("policy")
    if not isinstance(section, dict):
        return None
    paths = section.get("policy_paths", [])
    if isinstance(paths, str):
        paths = [paths]
    return PolicyConfig(
        policy_paths=tuple(paths),
        simulation_mode=section.get("simulation_mode", False),
    )


def _parse_router_config(toml: dict[str, Any]) -> RouterConfigData | None:
    """Parse [router] section from TOML config."""
    section = toml.get("router")
    if not isinstance(section, dict):
        return None
    chain = section.get("fallback_chain", [])
    if isinstance(chain, str):
        chain = [chain]
    return RouterConfigData(
        strategy=section.get("strategy", "manual"),
        fallback_chain=tuple(chain),
        max_cost_per_session=float(section.get("max_cost_per_session", 0.0)),
        max_tokens_per_session=int(section.get("max_tokens_per_session", 0)),
        simple_task_model=section.get("simple_task_model"),
    )


def _parse_sandbox_config(
    toml: dict[str, Any], override_mode: str | None = None,
) -> SandboxConfig | None:
    """Parse [sandbox] section from TOML config."""
    section = toml.get("sandbox")
    if not isinstance(section, dict) and override_mode is None:
        return None

    if isinstance(section, dict):
        mode = override_mode or section.get("mode", "process")
        enabled = section.get("enabled", False) or override_mode is not None
        allowed = section.get("allowed_paths", [])
        blocked = section.get("blocked_commands", [])
        return SandboxConfig(
            enabled=enabled,
            mode=mode,
            allowed_paths=tuple(allowed) if isinstance(allowed, list) else (),
            blocked_commands=tuple(blocked) if isinstance(blocked, list) else (),
            max_memory_mb=section.get("max_memory_mb", 512),
            max_cpu_seconds=section.get("max_cpu_seconds", 30),
            network_access=section.get("network_access", False),
            docker_image=section.get("docker_image", "python:3.12-slim"),
        )

    # Override mode without config section
    if override_mode and override_mode != "none":
        return SandboxConfig(enabled=True, mode=override_mode)

    return None


def _init_observability(toml: dict[str, Any]) -> bool:
    """Initialize OTel if configured. Returns True if configured."""
    section = toml.get("observability")
    enabled = False
    if isinstance(section, dict):
        enabled = section.get("enabled", False)
    if not enabled:
        enabled = os.environ.get("HARNESS_OTEL_ENABLED", "").lower() == "true"
    if not enabled:
        return False

    try:
        from harness.observability.exporters import ObservabilityConfig, configure_exporters

        exporter = "console"
        endpoint = "http://localhost:4317"
        service_name = "harness-agent"

        if isinstance(section, dict):
            exporter = section.get("exporter", "console")
            endpoint = section.get("otlp_endpoint", endpoint)
            service_name = section.get("service_name", service_name)

        # Env var overrides
        exporter = os.environ.get("HARNESS_OTEL_EXPORTER", exporter)
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)

        otel_config = ObservabilityConfig(
            enabled=True,
            exporter=exporter,
            otlp_endpoint=endpoint,
            service_name=service_name,
        )
        return configure_exporters(otel_config)
    except ImportError:
        return False


def _init_audit_logger(
    config: AuditConfig | None, session_id: str | None,
) -> Any | None:
    """Initialize AuditLogger if configured."""
    if config is None or not config.enabled:
        return None
    try:
        from harness.audit.logger import AuditLogger
        return AuditLogger(
            session_id=session_id or "unknown",
            enabled=True,
            log_tool_args=config.log_tool_args,
        )
    except ImportError:
        return None


def _init_policy_engine(
    config: PolicyConfig | None, cwd: str,
) -> Any | None:
    """Initialize PolicyEngine if configured."""
    if config is None and not Path(cwd, ".harness", "policy.yml").exists():
        return None

    try:
        from harness.permissions.policy import PolicyEngine

        engine = PolicyEngine(
            simulation_mode=config.simulation_mode if config else False,
        )

        # Load configured paths
        if config and config.policy_paths:
            engine.load_files(list(config.policy_paths))

        # Auto-discover standard locations
        for candidate in [
            Path(cwd) / ".harness" / "policy.yml",
            Path(cwd) / ".harness" / "policy.toml",
            Path.home() / ".harness" / "policy.yml",
            Path.home() / ".harness" / "policy.toml",
        ]:
            if candidate.exists():
                engine.load_file(candidate)

        return engine
    except ImportError:
        return None


def _init_model_router(
    config: RouterConfigData | None, adapter: ProviderAdapter,
) -> ProviderAdapter:
    """Wrap the adapter with a ModelRouter if configured. Returns adapter unchanged if not."""
    if config is None or config.strategy == "manual":
        return adapter

    try:
        from harness.providers.budget import TokenBudgetTracker
        from harness.providers.router import ModelRouter, RoutingStrategy

        strategy = RoutingStrategy(config.strategy)
        budget = TokenBudgetTracker(
            max_tokens=config.max_tokens_per_session,
            max_cost=config.max_cost_per_session,
        )

        # Create simple task provider if specified
        simple_provider = None
        if config.simple_task_model:
            try:
                from harness.providers.registry import create_provider
                simple_provider = create_provider(config.simple_task_model)
            except (KeyError, ImportError):
                pass

        return ModelRouter(
            adapter,
            strategy=strategy,
            simple_task_provider=simple_provider,
            budget=budget,
        )
    except ImportError:
        return adapter


def _init_sandbox_executor(
    config: SandboxConfig | None, cwd: str,
) -> Any | None:
    """Initialize SandboxExecutor if configured."""
    if config is None or not config.enabled:
        return None
    try:
        from harness.sandbox.executor import create_executor
        from harness.sandbox.policy import build_policy

        policy = build_policy(config, cwd=cwd)
        return create_executor(policy)
    except ImportError:
        return None
