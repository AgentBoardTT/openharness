"""Sub-agent lifecycle manager."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from harness.agents.registry import get_agent_def
from harness.core.session import Session
from harness.types.agents import AgentDef
from harness.types.config import PermissionMode, RunConfig
from harness.types.messages import Result, TextMessage
from harness.types.providers import ProviderAdapter


class AgentManager:
    """Manages spawning and running sub-agents.

    Sub-agents reuse AgentLoop with filtered tools and fresh context.
    """

    def __init__(
        self,
        provider: ProviderAdapter,
        tools: dict[str, Any],
        cwd: str | Path,
        context_window: int = 200_000,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._cwd = str(Path(cwd).resolve())
        self._context_window = context_window

    async def spawn(
        self,
        agent_name: str,
        prompt: str,
        *,
        model: str | None = None,
    ) -> str:
        """Spawn a sub-agent and return its final response text.

        Args:
            agent_name: Name of the agent type (e.g. "general", "explore").
            prompt: The task for the sub-agent.
            model: Optional model override.

        Returns:
            The sub-agent's final response text.
        """
        agent_def = get_agent_def(agent_name)
        return await self._run_agent(agent_def, prompt, model=model)

    async def spawn_parallel(
        self,
        tasks: list[tuple[str, str]],
        *,
        model: str | None = None,
    ) -> list[str]:
        """Spawn multiple sub-agents in parallel.

        Args:
            tasks: List of (agent_name, prompt) tuples.
            model: Optional model override for all agents.

        Returns:
            List of response texts, one per task (in order).
        """
        coros = [self.spawn(name, prompt, model=model) for name, prompt in tasks]
        return list(await asyncio.gather(*coros, return_exceptions=False))

    async def _run_agent(
        self,
        agent_def: AgentDef,
        prompt: str,
        *,
        model: str | None = None,
    ) -> str:
        """Run a sub-agent with the given definition."""
        from harness.core.loop import AgentLoop

        # Filter tools based on agent definition
        if agent_def.tools:
            filtered_tools = {
                name: tool
                for name, tool in self._tools.items()
                if name in agent_def.tools
            }
        else:
            filtered_tools = dict(self._tools)

        # Determine permission mode for sub-agent
        perm_mode = PermissionMode.PLAN if agent_def.read_only else PermissionMode.BYPASS

        # Build config for sub-agent
        config = RunConfig(
            model=model or agent_def.model,
            tools=list(filtered_tools.keys()),
            permission_mode=perm_mode,
            max_turns=agent_def.max_turns,
            cwd=self._cwd,
            system_prompt=agent_def.system_prompt,
        )

        # Fresh session for sub-agent
        session = Session(cwd=self._cwd)

        # Create and run nested loop
        loop = AgentLoop(
            provider=self._provider,
            tools=filtered_tools,
            config=config,
            session=session,
            context_window=self._context_window,
        )

        final_text = ""
        async for msg in loop.run(prompt):
            if isinstance(msg, TextMessage) and not msg.is_partial:
                final_text = msg.text
            elif isinstance(msg, Result):
                if not final_text:
                    final_text = msg.text

        return final_text or "(No response from sub-agent)"
