"""Test fixtures including MockProvider for deterministic testing."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from harness.types.providers import ChatMessage, StreamEvent
from harness.types.tools import ToolDef


@dataclass
class MockTurn:
    """A scripted turn for MockProvider.

    Specify either text or tool_uses (or both) for what the model should "respond" with.
    """

    text: str = ""
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    # Each tool_use: {"id": "tu1", "name": "Read", "args": {"file_path": "foo.py"}}


class MockProvider:
    """A deterministic mock provider for testing.

    Usage:
        provider = MockProvider(turns=[
            MockTurn(text="Let me read that file."),
            MockTurn(tool_uses=[{"id": "tu1", "name": "Read", "args": {"file_path": "test.py"}}]),
            MockTurn(text="The file contains test code."),
        ])
    """

    def __init__(self, turns: list[MockTurn], model: str = "mock-model"):
        self._turns = list(turns)
        self._turn_index = 0
        self._model = model

    @property
    def model_id(self) -> str:
        return self._model

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Yield scripted StreamEvents for the current turn."""
        if self._turn_index >= len(self._turns):
            # No more turns — just end
            yield StreamEvent(
                type="message_end", stop_reason="end_turn",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
            return

        turn = self._turns[self._turn_index]
        self._turn_index += 1

        # Emit text
        if turn.text:
            yield StreamEvent(type="text_delta", text=turn.text)

        # Emit tool uses
        for tu in turn.tool_uses:
            yield StreamEvent(
                type="tool_use_start",
                tool_use_id=tu["id"],
                tool_name=tu["name"],
            )
            args_json = json.dumps(tu.get("args", {}))
            yield StreamEvent(type="tool_use_delta", tool_args_json=args_json)
            yield StreamEvent(type="tool_use_end")

        # Determine stop reason
        stop_reason = "tool_use" if turn.tool_uses else "end_turn"
        yield StreamEvent(
            type="message_end",
            stop_reason=stop_reason,
            usage={"input_tokens": 100, "output_tokens": 50},
        )

    def format_tool_result(
        self, tool_use_id: str, content: str, is_error: bool = False,
    ) -> ChatMessage:
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }
        if is_error:
            block["is_error"] = True
        return ChatMessage(role="user", content=[block])

    def format_tool_use(self, tool_use_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"type": "tool_use", "id": tool_use_id, "name": name, "input": args}


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with sample files."""
    # Create some sample files
    (tmp_path / "README.md").write_text("# Test Project\n\nA test project.\n")
    (tmp_path / "main.py").write_text("def hello():\n    print('Hello, world!')\n\nhello()\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.py").write_text("def add(a, b):\n    return a + b\n")
    (src / "app.py").write_text("from utils import add\n\nresult = add(1, 2)\nprint(result)\n")
    return tmp_path


@pytest.fixture
def mock_provider() -> MockProvider:
    """A simple mock provider that responds with text."""
    return MockProvider(turns=[
        MockTurn(text="I can help with that."),
    ])
