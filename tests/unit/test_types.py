"""Tests for harness.types module."""

from harness.types.config import MCPServerConfig, PermissionMode, RunConfig
from harness.types.messages import (
    CompactionEvent,
    Message,
    Result,
    SystemEvent,
    TextMessage,
    ToolResult,
    ToolUse,
)
from harness.types.providers import ChatMessage, ModelInfo, StreamEvent
from harness.types.tools import ToolContext, ToolDef, ToolParam, ToolResultData


class TestMessages:
    def test_text_message(self):
        msg = TextMessage(text="hello", is_partial=True)
        assert msg.text == "hello"
        assert msg.is_partial is True

    def test_tool_use(self):
        tu = ToolUse(id="tu1", name="Read", args={"file_path": "foo.py"})
        assert tu.id == "tu1"
        assert tu.name == "Read"
        assert tu.args == {"file_path": "foo.py"}

    def test_tool_result(self):
        tr = ToolResult(tool_use_id="tu1", content="file contents", is_error=False)
        assert tr.tool_use_id == "tu1"
        assert tr.content == "file contents"
        assert tr.is_error is False

    def test_result(self):
        r = Result(text="Done", session_id="abc123", turns=3, tool_calls=5)
        assert r.text == "Done"
        assert r.session_id == "abc123"
        assert r.turns == 3
        assert r.tool_calls == 5
        assert r.total_cost == 0.0

    def test_compaction_event(self):
        ce = CompactionEvent(tokens_before=10000, tokens_after=5000, summary="Summarized context")
        assert ce.tokens_before == 10000

    def test_system_event(self):
        se = SystemEvent(type="session_start", data={"id": "123"})
        assert se.type == "session_start"

    def test_message_union_match(self):
        msg: Message = TextMessage(text="hi")
        match msg:
            case TextMessage(text=t):
                assert t == "hi"
            case _:
                raise AssertionError("Should match TextMessage")


class TestConfig:
    def test_permission_modes(self):
        assert PermissionMode.DEFAULT.value == "default"
        assert PermissionMode.ACCEPT_EDITS.value == "accept_edits"
        assert PermissionMode.PLAN.value == "plan"
        assert PermissionMode.BYPASS.value == "bypass"

    def test_run_config_defaults(self):
        config = RunConfig()
        assert config.provider == "anthropic"
        assert config.model is None
        assert len(config.tools) == 6
        assert config.max_turns == 100

    def test_mcp_server_config(self):
        mcp = MCPServerConfig(command="mcp-postgres", args=["--host", "localhost"])
        assert mcp.transport == "stdio"


class TestProviderTypes:
    def test_chat_message(self):
        msg = ChatMessage(role="user", content="hello")
        assert msg.role == "user"

    def test_stream_event(self):
        event = StreamEvent(type="text_delta", text="hello")
        assert event.type == "text_delta"
        assert event.text == "hello"

    def test_model_info(self):
        info = ModelInfo(
            id="claude-sonnet-4-6",
            provider="anthropic",
            display_name="Claude Sonnet 4.6",
            context_window=200000,
            max_output_tokens=16384,
            input_cost_per_mtok=3.0,
            output_cost_per_mtok=15.0,
            aliases=("sonnet",),
        )
        assert info.supports_tools is True
        assert info.aliases == ("sonnet",)


class TestToolTypes:
    def test_tool_def(self):
        td = ToolDef(
            name="Read",
            description="Read a file",
            parameters=(ToolParam(name="file_path", type="string", description="Path"),),
        )
        assert td.name == "Read"
        assert len(td.parameters) == 1

    def test_tool_result_data(self):
        trd = ToolResultData(content="file contents")
        assert trd.is_error is False
        assert trd.display is None

    def test_tool_context(self):
        from pathlib import Path
        ctx = ToolContext(cwd=Path("/tmp"))
        assert ctx.permission_mode == "default"
