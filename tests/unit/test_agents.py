"""Tests for harness.agents — registry and sub-agent spawning."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.agents.manager import AgentManager
from harness.agents.registry import AGENTS, get_agent_def, list_agents
from harness.types.agents import AgentDef
from tests.conftest import MockProvider, MockTurn


class TestAgentRegistry:
    def test_get_general_agent(self):
        agent = get_agent_def("general")
        assert agent.name == "general"
        assert "Read" in agent.tools
        assert "Write" in agent.tools
        assert agent.read_only is False

    def test_get_explore_agent(self):
        agent = get_agent_def("explore")
        assert agent.name == "explore"
        assert "Read" in agent.tools
        assert "Glob" in agent.tools
        assert "Write" not in agent.tools
        assert agent.read_only is True

    def test_get_plan_agent(self):
        agent = get_agent_def("plan")
        assert agent.name == "plan"
        assert agent.read_only is True
        assert agent.system_prompt is not None

    def test_unknown_agent_raises(self):
        with pytest.raises(KeyError, match="Unknown agent type"):
            get_agent_def("nonexistent")

    def test_list_agents(self):
        agents = list_agents()
        assert len(agents) >= 3
        names = {a.name for a in agents}
        assert "general" in names
        assert "explore" in names
        assert "plan" in names

    def test_agent_def_structure(self):
        for name, agent in AGENTS.items():
            assert isinstance(agent, AgentDef)
            assert agent.name == name
            assert agent.max_turns > 0


class TestAgentManager:
    @pytest.mark.asyncio
    async def test_spawn_general_agent(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
        (tmp_path / "sessions").mkdir(exist_ok=True)

        provider = MockProvider(turns=[
            MockTurn(text="I completed the task."),
        ])

        # Create minimal tools
        from harness.tools.read import ReadTool
        tools = {"Read": ReadTool()}

        mgr = AgentManager(provider=provider, tools=tools, cwd=str(tmp_path))
        result = await mgr.spawn("general", "Do something")
        assert "completed" in result.lower()

    @pytest.mark.asyncio
    async def test_spawn_explore_agent(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
        (tmp_path / "sessions").mkdir(exist_ok=True)

        provider = MockProvider(turns=[
            MockTurn(text="Found the files."),
        ])

        from harness.tools.glob import GlobTool
        from harness.tools.grep import GrepTool
        from harness.tools.read import ReadTool
        tools = {"Read": ReadTool(), "Glob": GlobTool(), "Grep": GrepTool()}

        mgr = AgentManager(provider=provider, tools=tools, cwd=str(tmp_path))
        result = await mgr.spawn("explore", "Find config files")
        assert "Found" in result

    @pytest.mark.asyncio
    async def test_spawn_unknown_agent_raises(self, tmp_path: Path):
        provider = MockProvider(turns=[])
        mgr = AgentManager(provider=provider, tools={}, cwd=str(tmp_path))
        with pytest.raises(KeyError):
            await mgr.spawn("doesnt_exist", "Do something")

    @pytest.mark.asyncio
    async def test_tool_filtering(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
        (tmp_path / "sessions").mkdir(exist_ok=True)

        provider = MockProvider(turns=[
            MockTurn(text="Done."),
        ])

        from harness.tools.bash import BashTool
        from harness.tools.read import ReadTool
        from harness.tools.write import WriteTool
        tools = {"Read": ReadTool(), "Write": WriteTool(), "Bash": BashTool()}

        mgr = AgentManager(provider=provider, tools=tools, cwd=str(tmp_path))
        # explore agent should only get Read, Glob, Grep — so Write and Bash filtered out
        result = await mgr.spawn("explore", "Explore the code")
        assert result  # Just confirm it runs

    @pytest.mark.asyncio
    async def test_empty_response(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
        (tmp_path / "sessions").mkdir(exist_ok=True)

        # Provider with no turns — empty response
        provider = MockProvider(turns=[])
        mgr = AgentManager(provider=provider, tools={}, cwd=str(tmp_path))
        result = await mgr.spawn("general", "Do something")
        assert "No response" in result

    @pytest.mark.asyncio
    async def test_spawn_parallel(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("harness.core.session._sessions_dir", lambda: tmp_path / "sessions")
        (tmp_path / "sessions").mkdir(exist_ok=True)

        provider = MockProvider(turns=[
            MockTurn(text="Result A."),
            MockTurn(text="Result B."),
            MockTurn(text="Result C."),
        ])

        from harness.tools.read import ReadTool
        tools = {"Read": ReadTool()}

        mgr = AgentManager(provider=provider, tools=tools, cwd=str(tmp_path))
        results = await mgr.spawn_parallel([
            ("general", "Task A"),
            ("general", "Task B"),
            ("general", "Task C"),
        ])
        assert len(results) == 3
        for r in results:
            assert isinstance(r, str)
            assert len(r) > 0
