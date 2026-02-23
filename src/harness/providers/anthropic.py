"""Anthropic/Claude provider adapter."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from harness.providers.base import BaseProvider
from harness.types.providers import ChatMessage, StreamEvent
from harness.types.tools import ToolDef

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Provider adapter for Anthropic's Claude models.

    Uses the official ``anthropic`` Python SDK with its async streaming
    interface.  All stream events from the SDK are translated into the
    provider-agnostic :class:`~harness.types.providers.StreamEvent` format.

    Parameters
    ----------
    api_key:
        Anthropic API key.  When *None* the SDK will fall back to the
        ``ANTHROPIC_API_KEY`` environment variable.
    model:
        Model ID to use for completions (default ``"claude-sonnet-4-6"``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        super().__init__(model)
        # Defer import so the rest of the codebase can be imported even if the
        # anthropic package is not installed (useful for type checking).
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for AnthropicProvider. "
                "Install it with: pip install anthropic"
            ) from exc

        self._client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()

    # ------------------------------------------------------------------
    # ProviderAdapter protocol
    # ------------------------------------------------------------------

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int = 8096,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a chat completion from the Anthropic API.

        Converts the provider-agnostic message list and tool definitions into
        the Anthropic wire format, opens a streaming request, and yields
        :class:`~harness.types.providers.StreamEvent` objects as chunks arrive.

        Parameters
        ----------
        messages:
            Conversation history (system messages are extracted separately).
        tools:
            Tool definitions available to the model.
        system:
            System prompt (extracted from *messages* if present; an explicit
            ``system`` parameter in the message list overrides this value).
        max_tokens:
            Maximum number of tokens to generate.

        Yields
        ------
        StreamEvent
            One event per meaningful chunk from the Anthropic stream.
        """
        # Extract system prompt from messages (last system message wins).
        resolved_system = system
        for msg in messages:
            if msg.role == "system":
                resolved_system = msg.content if isinstance(msg.content, str) else system

        anthropic_messages = self._to_anthropic_messages(messages)
        anthropic_tools = self._to_anthropic_tools(tools)

        # Kick off the streaming request (with retry on transient errors).
        # We cannot wrap the async-for loop itself inside _retry_with_backoff
        # because streaming is lazy — we must open the context manager and
        # iterate inside the same call frame.  Instead we retry the whole
        # generator invocation at the caller level; here we just surface any
        # initial connection error immediately.
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            system=resolved_system,
            messages=anthropic_messages,
            tools=anthropic_tools,  # type: ignore[arg-type]
        ) as stream:
            # Track the type of the *current* content block so we know when
            # a tool_use block has ended (content_block_stop).
            current_block_type: str | None = None

            async for event in stream:
                event_type: str = event.type

                # --- Tool use start ---
                if (
                    event_type == "content_block_start"
                    and hasattr(event, "content_block")
                    and event.content_block.type == "tool_use"
                ):
                    current_block_type = "tool_use"
                    yield StreamEvent(
                        type="tool_use_start",
                        tool_use_id=event.content_block.id,
                        tool_name=event.content_block.name,
                    )

                # --- Plain text block start (track type only) ---
                elif (
                    event_type == "content_block_start"
                    and hasattr(event, "content_block")
                    and event.content_block.type == "text"
                ):
                    current_block_type = "text"

                # --- Text delta ---
                elif (
                    event_type == "content_block_delta"
                    and hasattr(event, "delta")
                    and event.delta.type == "text_delta"
                ):
                    yield StreamEvent(type="text_delta", text=event.delta.text)

                # --- Tool args (partial JSON) ---
                elif (
                    event_type == "content_block_delta"
                    and hasattr(event, "delta")
                    and event.delta.type == "input_json_delta"
                ):
                    yield StreamEvent(
                        type="tool_use_delta",
                        tool_args_json=event.delta.partial_json,
                    )

                # --- Content block end ---
                elif event_type == "content_block_stop":
                    if current_block_type == "tool_use":
                        yield StreamEvent(type="tool_use_end")
                    current_block_type = None

                # --- Message end ---
                elif event_type == "message_stop":
                    # Retrieve final message for usage + stop_reason.
                    final_message = await stream.get_final_message()
                    usage_obj = final_message.usage
                    usage: dict[str, int] = {
                        "input_tokens": usage_obj.input_tokens,
                        "output_tokens": usage_obj.output_tokens,
                    }
                    # Cache token fields may not be present on all accounts.
                    cache_read = getattr(usage_obj, "cache_read_input_tokens", 0) or 0
                    cache_write = getattr(usage_obj, "cache_creation_input_tokens", 0) or 0
                    if cache_read:
                        usage["cache_read_tokens"] = cache_read
                    if cache_write:
                        usage["cache_write_tokens"] = cache_write

                    yield StreamEvent(
                        type="message_end",
                        stop_reason=final_message.stop_reason,
                        usage=usage,
                    )

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _to_anthropic_messages(
        self, messages: list[ChatMessage]
    ) -> list[dict[str, Any]]:
        """Convert our :class:`ChatMessage` list to Anthropic's messages format.

        System-role messages are stripped out (the caller passes the system
        prompt as a separate argument).  Assistant messages may contain a mix
        of text and tool_use content blocks.  Tool-result messages are emitted
        as ``role="user"`` messages containing ``tool_result`` blocks, which is
        what the Anthropic API expects.

        Parameters
        ----------
        messages:
            Provider-agnostic message list.

        Returns
        -------
        list[dict[str, Any]]
            Messages array ready for the Anthropic SDK.
        """
        result: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                # System prompt is handled by the caller.
                continue

            if msg.role == "user":
                # Could be a plain user message or a tool-result message.
                if isinstance(msg.content, list):
                    # Already in block format (e.g. tool_result blocks).
                    result.append({"role": "user", "content": msg.content})
                else:
                    result.append({"role": "user", "content": str(msg.content)})

            elif msg.role == "assistant":
                if isinstance(msg.content, list):
                    # Content is already a list of blocks (text + tool_use).
                    result.append({"role": "assistant", "content": msg.content})
                else:
                    # Plain string content.
                    result.append(
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": str(msg.content)}],
                        }
                    )

        return result

    def _to_anthropic_tools(self, tools: list[ToolDef]) -> list[dict[str, Any]]:
        """Convert :class:`ToolDef` objects to the Anthropic tool schema format.

        Builds on :meth:`~harness.providers.base.BaseProvider._make_tool_defs`
        which produces the generic JSON-Schema intermediate form, then maps
        ``input_schema`` to the key expected by the Anthropic SDK.

        Parameters
        ----------
        tools:
            Tool definitions to convert.

        Returns
        -------
        list[dict[str, Any]]
            Tool dicts ready for the ``tools`` parameter of the Anthropic API.
        """
        generic = self._make_tool_defs(tools)
        # The Anthropic SDK wants exactly the same structure our base method
        # already produces (name / description / input_schema).
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in generic
        ]
