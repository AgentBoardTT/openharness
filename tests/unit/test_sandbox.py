"""Tests for the sandbox execution module."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.sandbox.executor import ExecutionResult, SandboxExecutor, create_executor
from harness.sandbox.policy import build_policy
from harness.sandbox.process import ProcessSandbox
from harness.sandbox.docker import DockerSandbox
from harness.types.config import SandboxConfig
from harness.types.sandbox import NetworkPolicy, ResourceLimits, SandboxMode, SandboxPolicy
from harness.types.tools import ToolContext, ToolResultData


# ---------------------------------------------------------------------------
# SandboxPolicy building tests
# ---------------------------------------------------------------------------


class TestBuildPolicy:
    def test_default_policy(self) -> None:
        config = SandboxConfig()
        policy = build_policy(config)
        assert policy.mode == SandboxMode.PROCESS
        assert policy.resource_limits.max_memory_mb == 512
        assert policy.resource_limits.max_cpu_seconds == 30

    def test_docker_mode(self) -> None:
        config = SandboxConfig(mode="docker", docker_image="node:20-slim")
        policy = build_policy(config)
        assert policy.mode == SandboxMode.DOCKER
        assert policy.docker_image == "node:20-slim"

    def test_relative_paths_resolved(self, tmp_path: Path) -> None:
        config = SandboxConfig(allowed_paths=("./src", "./tests"))
        policy = build_policy(config, cwd=str(tmp_path))
        for p in policy.allowed_paths:
            assert Path(p).is_absolute()

    def test_blocked_commands(self) -> None:
        config = SandboxConfig(blocked_commands=("rm -rf /", "mkfs"))
        policy = build_policy(config)
        assert "rm -rf /" in policy.blocked_commands

    def test_network_policy(self) -> None:
        config = SandboxConfig(network_access=True)
        policy = build_policy(config)
        assert policy.network.allow_network is True

    def test_resource_limits(self) -> None:
        config = SandboxConfig(max_memory_mb=256, max_cpu_seconds=10)
        policy = build_policy(config)
        assert policy.resource_limits.max_memory_mb == 256
        assert policy.resource_limits.max_cpu_seconds == 10


# ---------------------------------------------------------------------------
# ProcessSandbox tests
# ---------------------------------------------------------------------------


class TestProcessSandbox:
    @pytest.mark.asyncio
    async def test_basic_execution(self) -> None:
        policy = SandboxPolicy()
        sandbox = ProcessSandbox(policy)
        result = await sandbox.execute("echo hello")
        assert result.exit_code == 0
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        policy = SandboxPolicy()
        sandbox = ProcessSandbox(policy)
        result = await sandbox.execute("sleep 10", timeout_sec=0.5)
        assert result.timed_out

    @pytest.mark.asyncio
    async def test_blocked_command(self) -> None:
        policy = SandboxPolicy(blocked_commands=("rm -rf /",))
        sandbox = ProcessSandbox(policy)
        result = await sandbox.execute("rm -rf / --no-preserve-root")
        assert result.exit_code == 1
        assert result.error is not None
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_command_whitespace_bypass(self) -> None:
        """Extra whitespace should not bypass blocked command checks."""
        policy = SandboxPolicy(blocked_commands=("rm -rf /",))
        sandbox = ProcessSandbox(policy)
        result = await sandbox.execute("rm  -rf  /")
        assert result.exit_code == 1
        assert result.error is not None
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_exit_code_preserved(self) -> None:
        policy = SandboxPolicy()
        sandbox = ProcessSandbox(policy)
        result = await sandbox.execute("exit 42")
        assert result.exit_code == 42

    @pytest.mark.asyncio
    async def test_cleanup_noop(self) -> None:
        policy = SandboxPolicy()
        sandbox = ProcessSandbox(policy)
        await sandbox.cleanup()  # Should not raise


# ---------------------------------------------------------------------------
# DockerSandbox tests
# ---------------------------------------------------------------------------


class TestDockerSandbox:
    def test_build_docker_args(self) -> None:
        policy = SandboxPolicy(
            mode=SandboxMode.DOCKER,
            allowed_paths=("/tmp/test",),
            docker_image="python:3.12-slim",
            network=NetworkPolicy(allow_network=False),
            resource_limits=ResourceLimits(max_memory_mb=256, max_cpu_seconds=10),
        )
        sandbox = DockerSandbox(policy)
        args, container_name = sandbox._build_docker_args("echo hello", cwd="/tmp/test")

        assert "docker" in args
        assert "--rm" in args
        assert "--network=none" in args
        assert "--memory=256m" in args
        assert any("-v" in a for a in args) or "/tmp/test:/tmp/test" in " ".join(args)
        assert "echo hello" in args
        assert container_name.startswith("harness-sandbox-")

    def test_dangerous_mount_rejected(self) -> None:
        policy = SandboxPolicy(
            mode=SandboxMode.DOCKER,
            allowed_paths=("/etc", "/tmp/safe"),
        )
        sandbox = DockerSandbox(policy)
        args, _ = sandbox._build_docker_args("ls")
        args_str = " ".join(args)
        assert "/etc:/etc" not in args_str
        assert "/tmp/safe:/tmp/safe" in args_str

    def test_build_docker_args_with_network(self) -> None:
        policy = SandboxPolicy(
            mode=SandboxMode.DOCKER,
            network=NetworkPolicy(allow_network=True),
        )
        sandbox = DockerSandbox(policy)
        args, _ = sandbox._build_docker_args("echo hello")
        assert "--network=none" not in args

    @pytest.mark.asyncio
    async def test_blocked_command(self) -> None:
        policy = SandboxPolicy(
            mode=SandboxMode.DOCKER,
            blocked_commands=("rm -rf /",),
        )
        sandbox = DockerSandbox(policy)
        result = await sandbox.execute("rm -rf / --force")
        assert result.exit_code == 1
        assert result.error is not None


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestFactory:
    def test_create_process_executor(self) -> None:
        policy = SandboxPolicy(mode=SandboxMode.PROCESS)
        executor = create_executor(policy)
        assert isinstance(executor, ProcessSandbox)

    def test_create_docker_executor(self) -> None:
        policy = SandboxPolicy(mode=SandboxMode.DOCKER)
        executor = create_executor(policy)
        assert isinstance(executor, DockerSandbox)


# ---------------------------------------------------------------------------
# BashTool with sandbox delegation
# ---------------------------------------------------------------------------


class TestBashToolSandboxDelegation:
    @pytest.mark.asyncio
    async def test_delegates_to_sandbox(self) -> None:
        from harness.tools.bash import BashTool
        from tests.conftest import MockSandboxExecutor, MockExecutionResult

        executor = MockSandboxExecutor(results=[
            MockExecutionResult(stdout="sandboxed output", exit_code=0),
        ])

        tool = BashTool()
        ctx = ToolContext(
            cwd=Path.cwd(),
            extra={"sandbox_executor": executor},
        )

        result = await tool.execute({"command": "echo test"}, ctx)
        assert "sandboxed output" in result.content
        assert not result.is_error
        assert len(executor.calls) == 1

    @pytest.mark.asyncio
    async def test_sandbox_error_returned(self) -> None:
        from harness.tools.bash import BashTool
        from tests.conftest import MockSandboxExecutor, MockExecutionResult

        executor = MockSandboxExecutor(results=[
            MockExecutionResult(stdout="", exit_code=1, error="Command blocked"),
        ])

        tool = BashTool()
        ctx = ToolContext(
            cwd=Path.cwd(),
            extra={"sandbox_executor": executor},
        )

        result = await tool.execute({"command": "rm -rf /"}, ctx)
        assert result.is_error
        assert "blocked" in result.content.lower()

    @pytest.mark.asyncio
    async def test_sandbox_timed_out(self) -> None:
        from harness.tools.bash import BashTool
        from tests.conftest import MockSandboxExecutor, MockExecutionResult

        executor = MockSandboxExecutor(results=[
            MockExecutionResult(stdout="", exit_code=-1, timed_out=True),
        ])

        tool = BashTool()
        ctx = ToolContext(
            cwd=Path.cwd(),
            extra={"sandbox_executor": executor},
        )

        result = await tool.execute({"command": "sleep 999"}, ctx)
        assert result.is_error
        assert "timed out" in result.content.lower()

    @pytest.mark.asyncio
    async def test_sandbox_oom_killed(self) -> None:
        from harness.tools.bash import BashTool
        from tests.conftest import MockSandboxExecutor, MockExecutionResult

        executor = MockSandboxExecutor(results=[
            MockExecutionResult(stdout="", exit_code=137, oom_killed=True),
        ])

        tool = BashTool()
        ctx = ToolContext(
            cwd=Path.cwd(),
            extra={"sandbox_executor": executor},
        )

        result = await tool.execute({"command": "eat-memory"}, ctx)
        assert result.is_error
        assert "oom" in result.content.lower()

    @pytest.mark.asyncio
    async def test_no_sandbox_uses_direct_execution(self) -> None:
        from harness.tools.bash import BashTool

        tool = BashTool()
        ctx = ToolContext(cwd=Path.cwd())

        result = await tool.execute({"command": "echo direct"}, ctx)
        assert "direct" in result.content
