"""Tests for harness.core.context — context compaction."""

from __future__ import annotations

import pytest

from harness.core.context import (
    _build_summary,
    _find_safe_boundary,
    compact_messages,
    estimate_message_tokens,
    estimate_total_tokens,
    needs_compaction,
)
from harness.types.providers import ChatMessage
from tests.conftest import MockProvider


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider(turns=[])


class TestTokenEstimation:
    def test_string_content(self, provider: MockProvider):
        msg = ChatMessage(role="user", content="hello world")
        tokens = estimate_message_tokens(msg, provider)
        assert tokens > 0

    def test_list_content(self, provider: MockProvider):
        msg = ChatMessage(
            role="assistant",
            content=[
                {"type": "text", "text": "Let me help."},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "x"}},
            ],
        )
        tokens = estimate_message_tokens(msg, provider)
        assert tokens > 10

    def test_total_tokens(self, provider: MockProvider):
        msgs = [
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="hi there"),
        ]
        total = estimate_total_tokens(msgs, "system prompt", provider)
        assert total > 0


class TestNeedsCompaction:
    def test_small_history_no_compaction(self, provider: MockProvider):
        msgs = [
            ChatMessage(role="user", content="hi"),
            ChatMessage(role="assistant", content="hello"),
        ]
        assert not needs_compaction(msgs, "system", provider, 200_000)

    def test_large_history_triggers_compaction(self, provider: MockProvider):
        # Create a large message that exceeds 85% of a small window
        big_text = "x" * 10000
        msgs = [
            ChatMessage(role="user", content=big_text),
            ChatMessage(role="assistant", content=big_text),
            ChatMessage(role="user", content=big_text),
            ChatMessage(role="assistant", content=big_text),
            ChatMessage(role="user", content="final question"),
        ]
        # With a tiny context window, this should trigger
        assert needs_compaction(msgs, "system", provider, 1000)


class TestFindSafeBoundary:
    def test_finds_user_message(self):
        msgs = [
            ChatMessage(role="user", content="q1"),
            ChatMessage(role="assistant", content="a1"),
            ChatMessage(role="user", content="q2"),
            ChatMessage(role="assistant", content="a2"),
        ]
        idx = _find_safe_boundary(msgs, 1)
        assert msgs[idx].role == "user"

    def test_skips_tool_result_boundary(self):
        msgs = [
            ChatMessage(role="user", content="q1"),
            ChatMessage(role="assistant", content="a1"),
            ChatMessage(
                role="user",
                content=[{"type": "tool_result", "tool_use_id": "x", "content": "r"}],
            ),
            ChatMessage(role="user", content="q2"),
            ChatMessage(role="assistant", content="a2"),
            ChatMessage(role="user", content="q3"),
            ChatMessage(role="assistant", content="a3"),
            ChatMessage(role="user", content="q4"),
        ]
        idx = _find_safe_boundary(msgs, 2)
        # Should land on a plain user message, not the tool_result one
        msg = msgs[idx]
        if isinstance(msg.content, list):
            has_tr = any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in msg.content
            )
            assert not has_tr
        else:
            assert msg.role == "user"


class TestCompactMessages:
    def test_compact_reduces_messages(self, provider: MockProvider):
        # Create enough messages that compaction has room to work
        msgs = []
        for i in range(10):
            msgs.append(ChatMessage(role="user", content=f"question {i} " + "x" * 2000))
            msgs.append(ChatMessage(role="assistant", content=f"answer {i} " + "y" * 2000))
        msgs.append(ChatMessage(role="user", content="final question"))

        compacted, event = compact_messages(
            msgs, "system", provider, context_window=3000,
        )
        assert len(compacted) < len(msgs)
        assert event.tokens_after <= event.tokens_before
        assert "[Context Summary" in compacted[0].content

    def test_compact_no_op_when_small(self, provider: MockProvider):
        msgs = [
            ChatMessage(role="user", content="hi"),
            ChatMessage(role="assistant", content="hello"),
        ]
        compacted, event = compact_messages(
            msgs, "system", provider, context_window=200_000,
        )
        assert len(compacted) == len(msgs)


class TestBuildSummary:
    def test_basic_summary(self):
        msgs = [
            ChatMessage(role="user", content="How do I fix auth?"),
            ChatMessage(role="assistant", content="Let me look at the code."),
        ]
        summary = _build_summary(msgs)
        assert len(summary) > 0

    def test_summary_with_tools(self):
        msgs = [
            ChatMessage(
                role="assistant",
                content=[
                    {"type": "text", "text": "Reading file..."},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "auth.py"}},
                ],
            ),
        ]
        summary = _build_summary(msgs)
        assert "Read" in summary or "auth.py" in summary
