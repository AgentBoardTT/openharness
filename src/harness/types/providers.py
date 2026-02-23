"""Provider adapter protocol and stream event types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from harness.types.tools import ToolDef


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """A single event from a streaming provider response."""

    type: str  # "text_delta", "tool_use_start", "tool_use_delta", "tool_use_end", "message_end"
    text: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_args_json: str | None = None
    stop_reason: str | None = None
    usage: dict[str, int] | None = None


@dataclass(slots=True)
class ProviderUsage:
    """Token usage from a provider response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(slots=True)
class ChatMessage:
    """A message in the chat history (provider-agnostic format)."""

    role: str  # "user", "assistant", "system"
    content: str | list[dict[str, Any]] = ""
    tool_use_id: str | None = None
    tool_name: str | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    """Protocol that all provider adapters must implement."""

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int,
    ) -> Any:
        """Stream a chat completion. Returns an async iterator of StreamEvent."""
        ...

    def format_tool_result(self, tool_use_id: str, content: str, is_error: bool) -> ChatMessage:
        """Format a tool result into a provider-specific message."""
        ...

    def format_tool_use(self, tool_use_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Format a tool use block for the assistant message."""
        ...

    @property
    def model_id(self) -> str:
        """The model identifier being used."""
        ...

    def estimate_tokens(self, text: str) -> int:
        """Rough token count estimate for a text string."""
        ...


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Information about a supported model."""

    id: str
    provider: str
    display_name: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0
    aliases: tuple[str, ...] = ()
