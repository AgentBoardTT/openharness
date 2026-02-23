"""Tests for harness.hooks — hook matching, execution, and template variables."""

from __future__ import annotations

import pytest

from harness.hooks.events import HookContext, build_hook_context
from harness.hooks.manager import HookManager
from harness.types.hooks import Hook, HookEvent


class TestBuildHookContext:
    def test_basic_context(self):
        ctx = build_hook_context(HookEvent.PRE_TOOL_USE, tool_name="Bash")
        assert ctx.event == HookEvent.PRE_TOOL_USE
        assert ctx.tool_name == "Bash"
        assert ctx.tool_args == {}
        assert ctx.result is None

    def test_full_context(self):
        ctx = build_hook_context(
            HookEvent.POST_TOOL_USE,
            tool_name="Read",
            tool_args={"file_path": "/tmp/test.py"},
            result="file contents here",
            is_error=False,
            session_id="abc123",
            cwd="/tmp/project",
        )
        assert ctx.tool_name == "Read"
        assert ctx.tool_args["file_path"] == "/tmp/test.py"
        assert ctx.result == "file contents here"
        assert ctx.session_id == "abc123"
        assert ctx.cwd == "/tmp/project"


class TestHookManager:
    def test_register_hook(self):
        mgr = HookManager()
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="echo test")
        mgr.register(hook)
        assert len(mgr._hooks) == 1

    def test_init_with_hooks(self):
        hooks = [
            Hook(event=HookEvent.PRE_TOOL_USE, command="echo pre"),
            Hook(event=HookEvent.POST_TOOL_USE, command="echo post"),
        ]
        mgr = HookManager(hooks)
        assert len(mgr._hooks) == 2


class TestHookMatching:
    def test_matches_by_event(self):
        mgr = HookManager()
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="echo test")
        ctx = HookContext(event=HookEvent.PRE_TOOL_USE, tool_name="Bash")
        assert mgr._matches(hook, ctx) is True

    def test_no_match_different_event(self):
        mgr = HookManager()
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="echo test")
        ctx = HookContext(event=HookEvent.POST_TOOL_USE, tool_name="Bash")
        assert mgr._matches(hook, ctx) is False

    def test_matches_with_tool_matcher(self):
        mgr = HookManager()
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="echo test", matcher="Bash")
        ctx_match = HookContext(event=HookEvent.PRE_TOOL_USE, tool_name="Bash")
        ctx_no = HookContext(event=HookEvent.PRE_TOOL_USE, tool_name="Read")
        assert mgr._matches(hook, ctx_match) is True
        assert mgr._matches(hook, ctx_no) is False

    def test_matches_with_glob_pattern(self):
        mgr = HookManager()
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="echo test", matcher="mcp__*")
        ctx = HookContext(event=HookEvent.PRE_TOOL_USE, tool_name="mcp__server__tool")
        assert mgr._matches(hook, ctx) is True

    def test_matcher_without_tool_name_fails(self):
        mgr = HookManager()
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="echo test", matcher="Bash")
        ctx = HookContext(event=HookEvent.PRE_TOOL_USE)
        assert mgr._matches(hook, ctx) is False

    def test_string_event_matching(self):
        mgr = HookManager()
        hook = Hook(event="pre_tool_use", command="echo test")
        ctx = HookContext(event=HookEvent.PRE_TOOL_USE, tool_name="Bash")
        assert mgr._matches(hook, ctx) is True


class TestHookExpansion:
    def test_expand_tool_name(self):
        mgr = HookManager()
        ctx = HookContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            session_id="s123",
            cwd="/tmp",
        )
        result = mgr._expand_command("echo {tool_name}", ctx)
        assert "Bash" in result

    def test_expand_file_path(self):
        mgr = HookManager()
        ctx = HookContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Read",
            tool_args={"file_path": "/tmp/test.py"},
        )
        result = mgr._expand_command("echo {file_path}", ctx)
        assert "/tmp/test.py" in result

    def test_expand_empty_variables(self):
        mgr = HookManager()
        ctx = HookContext(event=HookEvent.SESSION_START)
        result = mgr._expand_command("echo {tool_name} {command}", ctx)
        # Empty vars should be quoted as ''
        assert "''" in result


class TestHookExecution:
    @pytest.mark.asyncio
    async def test_fire_matching_hook(self):
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="echo hello")
        mgr = HookManager([hook])
        ctx = build_hook_context(HookEvent.PRE_TOOL_USE, tool_name="Bash")
        results = await mgr.fire(ctx)
        assert len(results) == 1
        assert results[0].success is True
        assert "hello" in results[0].output

    @pytest.mark.asyncio
    async def test_fire_no_matching_hooks(self):
        hook = Hook(event=HookEvent.POST_TOOL_USE, command="echo post")
        mgr = HookManager([hook])
        ctx = build_hook_context(HookEvent.PRE_TOOL_USE, tool_name="Bash")
        results = await mgr.fire(ctx)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_fire_failing_command(self):
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="false")
        mgr = HookManager([hook])
        ctx = build_hook_context(HookEvent.PRE_TOOL_USE, tool_name="Bash")
        results = await mgr.fire(ctx)
        assert len(results) == 1
        assert results[0].success is False

    @pytest.mark.asyncio
    async def test_fire_timeout(self):
        hook = Hook(event=HookEvent.PRE_TOOL_USE, command="sleep 10", timeout=0.1)
        mgr = HookManager([hook])
        ctx = build_hook_context(HookEvent.PRE_TOOL_USE, tool_name="Bash")
        results = await mgr.fire(ctx)
        assert len(results) == 1
        assert results[0].success is False
        assert "timed out" in results[0].error.lower()

    @pytest.mark.asyncio
    async def test_fire_multiple_hooks(self):
        hooks = [
            Hook(event=HookEvent.PRE_TOOL_USE, command="echo first"),
            Hook(event=HookEvent.PRE_TOOL_USE, command="echo second"),
        ]
        mgr = HookManager(hooks)
        ctx = build_hook_context(HookEvent.PRE_TOOL_USE, tool_name="Bash")
        results = await mgr.fire(ctx)
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_hook_with_template_expansion(self, tmp_path):
        hook = Hook(
            event=HookEvent.PRE_TOOL_USE,
            command="echo {tool_name}",
        )
        mgr = HookManager([hook])
        ctx = build_hook_context(
            HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            cwd=str(tmp_path),
        )
        results = await mgr.fire(ctx)
        assert results[0].success is True
        assert "Bash" in results[0].output

    @pytest.mark.asyncio
    async def test_hook_json_output_parsed(self):
        hook = Hook(
            event=HookEvent.PRE_TOOL_USE,
            command='echo \'{"blocked": true}\'',
        )
        mgr = HookManager([hook])
        ctx = build_hook_context(HookEvent.PRE_TOOL_USE, tool_name="Bash")
        results = await mgr.fire(ctx)
        assert results[0].data.get("blocked") is True
