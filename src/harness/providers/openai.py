"""OpenAI provider adapter.

Supports OpenAI models (GPT-4o, GPT-4o-mini) and any OpenAI-compatible
endpoint such as Ollama (``http://localhost:11434/v1``), Groq, and OpenRouter
by passing a custom ``base_url``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from harness.providers.base import BaseProvider
from harness.types.providers import ChatMessage, StreamEvent
from harness.types.tools import ToolDef

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """Provider adapter for OpenAI-compatible chat completion APIs.

    Uses the official ``openai`` Python SDK with its async streaming interface.
    All stream events from the SDK are translated into the provider-agnostic
    :class:`~harness.types.providers.StreamEvent` format.

    The ``base_url`` parameter enables drop-in compatibility with:

    - **Ollama**: ``http://localhost:11434/v1``
    - **Groq**: ``https://api.groq.com/openai/v1``
    - **OpenRouter**: ``https://openrouter.ai/api/v1``

    Parameters
    ----------
    api_key:
        OpenAI API key.  When *None* the SDK falls back to the
        ``OPENAI_API_KEY`` environment variable.
    model:
        Model ID to use for completions (default ``"gpt-4o"``).
    base_url:
        Optional custom base URL for OpenAI-compatible endpoints.  When
        *None* the standard ``https://api.openai.com/v1`` endpoint is used.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        super().__init__(model)
        # Defer import so the rest of the codebase can be imported even if the
        # openai package is not installed (useful for type checking).
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for OpenAIProvider. "
                "Install it with: pip install openai"
            ) from exc

        kwargs: dict[str, Any] = {}
        if api_key is not None:
            kwargs["api_key"] = api_key
        if base_url is not None:
            kwargs["base_url"] = base_url

        self._client = AsyncOpenAI(**kwargs)

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
        """Stream a chat completion from an OpenAI-compatible API.

        Converts the provider-agnostic message list and tool definitions into
        the OpenAI wire format, opens a streaming request, and yields
        :class:`~harness.types.providers.StreamEvent` objects as chunks arrive.

        The system prompt is injected as the first message with
        ``role="system"``, which is the convention for OpenAI-compatible APIs.

        Parameters
        ----------
        messages:
            Conversation history (system messages are merged into the first
            position automatically).
        tools:
            Tool definitions available to the model.
        system:
            System prompt string.
        max_tokens:
            Maximum number of tokens to generate.

        Yields
        ------
        StreamEvent
            One event per meaningful chunk from the OpenAI stream.
        """
        async for event in self._stream(messages, tools, system, max_tokens):
            yield event

    async def _stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Internal async generator — yielded by :meth:`chat_completion_stream`."""
        from openai import NOT_GIVEN

        # Resolve system prompt: explicit ``system`` parameter wins, but any
        # system-role message in the history also takes effect (last one wins).
        resolved_system = system
        for msg in messages:
            if msg.role == "system":
                resolved_system = msg.content if isinstance(msg.content, str) else system

        openai_messages = self._to_openai_messages(messages, resolved_system)
        openai_tools = self._to_openai_tools(tools)

        # GPT-5+ and reasoning models (o1/o3/o4) use max_completion_tokens
        # instead of the legacy max_tokens parameter.
        model_lower = self._model.lower()
        use_new_param = any(
            model_lower.startswith(p)
            for p in ("gpt-5", "o1", "o3", "o4")
        )

        token_kwargs: dict[str, Any] = {}
        if use_new_param:
            token_kwargs["max_completion_tokens"] = max_tokens
        else:
            token_kwargs["max_tokens"] = max_tokens

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,  # type: ignore[arg-type]
            tools=openai_tools if openai_tools else NOT_GIVEN,
            stream=True,
            stream_options={"include_usage": True},
            **token_kwargs,
        )

        # Track active tool calls by their index within the delta stream.
        # OpenAI may send multiple tool calls in one response and streams
        # their arguments progressively.  A new entry starts when we see a
        # chunk with a non-None ``id`` field on the tool_call object.
        active_tool_call_ids: dict[int, str] = {}  # index -> tool_use_id
        final_usage: dict[str, int] | None = None

        async for chunk in stream:
            # OpenAI sends a final chunk with choices=[] and usage populated
            # when stream_options={"include_usage": True}. Capture it before
            # skipping the chunk.
            raw_usage = getattr(chunk, "usage", None)
            if raw_usage is not None:
                final_usage = {
                    "input_tokens": getattr(raw_usage, "prompt_tokens", 0) or 0,
                    "output_tokens": getattr(raw_usage, "completion_tokens", 0) or 0,
                }

            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            delta = choice.delta

            # --- Text delta ---
            if delta.content:
                yield StreamEvent(type="text_delta", text=delta.content)

            # --- Tool call deltas ---
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index

                    # A non-None ``tc.id`` signals the start of a new tool call
                    # at this index position.
                    if tc.id is not None:
                        active_tool_call_ids[idx] = tc.id
                        tool_name = tc.function.name if tc.function else ""
                        yield StreamEvent(
                            type="tool_use_start",
                            tool_use_id=tc.id,
                            tool_name=tool_name,
                        )

                    # Argument fragment — may arrive with or without an id.
                    if tc.function and tc.function.arguments:
                        yield StreamEvent(
                            type="tool_use_delta",
                            tool_args_json=tc.function.arguments,
                        )

            # --- Finish reason ---
            if choice.finish_reason:
                # Emit tool_use_end for every open tool call before closing.
                for _idx in sorted(active_tool_call_ids):
                    yield StreamEvent(type="tool_use_end")
                active_tool_call_ids.clear()

                # Normalize OpenAI's "tool_calls" to "tool_use" for consistency
                # with the provider-agnostic convention used by the agent loop.
                reason = choice.finish_reason
                if reason == "tool_calls":
                    reason = "tool_use"

                yield StreamEvent(
                    type="message_end",
                    stop_reason=reason,
                    usage=final_usage,
                )

    # ------------------------------------------------------------------
    # Provider-specific overrides
    # ------------------------------------------------------------------

    def format_tool_result(
        self,
        tool_use_id: str,
        content: str,
        is_error: bool = False,
    ) -> ChatMessage:
        """Build an OpenAI-style tool-result message.

        OpenAI expects tool results as a dedicated ``role="tool"`` message
        rather than embedding them inside a ``role="user"`` message.

        Parameters
        ----------
        tool_use_id:
            The opaque ID from the corresponding tool call.
        content:
            Serialised text output from the tool (or error message).
        is_error:
            When *True* the content is treated as an error.  OpenAI does not
            have a first-class error flag, so the content is passed as-is.

        Returns
        -------
        ChatMessage
            A ``role="tool"`` message carrying the tool result.
        """
        return ChatMessage(role="tool", content=content, tool_use_id=tool_use_id)

    def format_tool_use(
        self,
        tool_use_id: str,
        name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Build an OpenAI-style tool-call content block.

        Parameters
        ----------
        tool_use_id:
            Unique ID for this tool invocation.
        name:
            Name of the tool being called.
        args:
            Parsed arguments dict for the call.

        Returns
        -------
        dict[str, Any]
            A tool_call block dict suitable for embedding in an assistant
            message's ``tool_calls`` list.
        """
        return {
            "type": "tool_call",
            "id": tool_use_id,
            "function": {
                "name": name,
                "arguments": json.dumps(args),
            },
        }

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _to_openai_messages(
        self,
        messages: list[ChatMessage],
        system: str,
    ) -> list[dict[str, Any]]:
        """Convert :class:`ChatMessage` list to the OpenAI messages array format.

        The system prompt is prepended as ``{"role": "system", "content": ...}``.
        Tool-result messages (``role="tool"`` or user messages containing
        ``tool_result`` blocks) are expanded into individual ``role="tool"``
        messages.  Assistant messages that contain tool_use blocks are split
        into a text part and a ``tool_calls`` list.

        Parameters
        ----------
        messages:
            Provider-agnostic message list.
        system:
            Resolved system prompt to inject at the top of the array.

        Returns
        -------
        list[dict[str, Any]]
            Messages array ready for the OpenAI SDK.
        """
        result: list[dict[str, Any]] = []

        # System prompt always goes first.
        if system:
            result.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == "system":
                # Already handled above via the ``system`` parameter.
                continue

            if msg.role == "tool":
                # Explicit tool-result message (produced by format_tool_result).
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_use_id or "",
                        "content": msg.content if isinstance(msg.content, str) else "",
                    }
                )

            elif msg.role == "user":
                if isinstance(msg.content, list):
                    # The list may contain tool_result blocks mixed with text
                    # blocks.  Convert each tool_result into its own role=tool
                    # message; collect plain text blocks into a user message.
                    text_parts: list[str] = []
                    for block in msg.content:
                        block_type = block.get("type") if isinstance(block, dict) else None
                        if block_type == "tool_result":
                            result.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": block.get("tool_use_id", ""),
                                    "content": block.get("content", ""),
                                }
                            )
                        elif block_type == "text":
                            text_parts.append(block.get("text", ""))
                        else:
                            # Pass unrecognised blocks through as-is so the
                            # caller can handle provider-specific types.
                            text_parts.append(str(block))

                    if text_parts:
                        result.append({"role": "user", "content": " ".join(text_parts)})
                else:
                    result.append({"role": "user", "content": str(msg.content)})

            elif msg.role == "assistant":
                if isinstance(msg.content, list):
                    # Separate text blocks from tool_use blocks.
                    text_blocks: list[str] = []
                    tool_calls: list[dict[str, Any]] = []

                    for block in msg.content:
                        block_type = block.get("type") if isinstance(block, dict) else None
                        if block_type == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block.get("id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": block.get("name", ""),
                                        "arguments": json.dumps(block.get("input", {})),
                                    },
                                }
                            )
                        elif block_type == "text":
                            text_blocks.append(block.get("text", ""))
                        elif block_type == "tool_call":
                            # Already in OpenAI format (from format_tool_use).
                            tool_calls.append(
                                {
                                    "id": block.get("id", ""),
                                    "type": "function",
                                    "function": block.get("function", {}),
                                }
                            )

                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": " ".join(text_blocks) if text_blocks else None,
                    }
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls
                    result.append(assistant_msg)
                else:
                    result.append({"role": "assistant", "content": str(msg.content)})

        return result

    def _to_openai_tools(self, tools: list[ToolDef]) -> list[dict[str, Any]]:
        """Convert :class:`ToolDef` objects to the OpenAI function-calling format.

        Builds on :meth:`~harness.providers.base.BaseProvider._make_tool_defs`
        which produces the generic JSON-Schema intermediate form, then wraps
        each entry in the ``{"type": "function", "function": {...}}`` envelope
        expected by the OpenAI API.

        Parameters
        ----------
        tools:
            Tool definitions to convert.

        Returns
        -------
        list[dict[str, Any]]
            Tool dicts ready for the ``tools`` parameter of the OpenAI API.
        """
        generic = self._make_tool_defs(tools)
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in generic
        ]
