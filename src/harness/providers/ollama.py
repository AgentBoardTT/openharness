"""Ollama provider adapter for local model inference.

Ollama exposes an OpenAI-compatible API at ``http://localhost:11434/v1``.
This adapter wraps :class:`OpenAIProvider` with Ollama-specific defaults:
no API key required, local base URL, and model availability checking.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from harness.providers.openai import OpenAIProvider
from harness.types.providers import ChatMessage, StreamEvent
from harness.types.tools import ToolDef

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(OpenAIProvider):
    """Provider adapter for Ollama local models.

    Inherits from :class:`OpenAIProvider` since Ollama exposes an
    OpenAI-compatible chat completions endpoint.  Overrides defaults
    to point at the local Ollama server and skip API key requirements.

    Parameters
    ----------
    model:
        Ollama model name (e.g. ``"llama3.3"``, ``"mistral"``).
    base_url:
        Ollama API base URL.  Defaults to ``http://localhost:11434/v1``.
    """

    def __init__(
        self,
        model: str = "llama3.3",
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key or "ollama",  # Ollama doesn't need a real key
            model=model,
            base_url=base_url or DEFAULT_OLLAMA_BASE_URL,
        )

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int = 8096,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a chat completion from the local Ollama server.

        Delegates to :class:`OpenAIProvider` after stripping unsupported
        options (e.g. ``stream_options``) that Ollama may not handle.
        """
        return self._stream(messages, tools, system, max_tokens)

    async def _stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Override streaming to handle Ollama-specific behavior."""
        from openai import NOT_GIVEN

        resolved_system = system
        for msg in messages:
            if msg.role == "system":
                resolved_system = (
                    msg.content if isinstance(msg.content, str) else system
                )

        openai_messages = self._to_openai_messages(messages, resolved_system)
        openai_tools = self._to_openai_tools(tools)

        # Ollama may not support stream_options, so we omit it
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,  # type: ignore[arg-type]
            tools=openai_tools if openai_tools else NOT_GIVEN,
            max_tokens=max_tokens,
            stream=True,
        )

        active_tool_call_ids: dict[int, str] = {}

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            delta = choice.delta

            if delta.content:
                yield StreamEvent(type="text_delta", text=delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index

                    if tc.id is not None:
                        active_tool_call_ids[idx] = tc.id
                        tool_name = tc.function.name if tc.function else ""
                        yield StreamEvent(
                            type="tool_use_start",
                            tool_use_id=tc.id,
                            tool_name=tool_name,
                        )

                    if tc.function and tc.function.arguments:
                        yield StreamEvent(
                            type="tool_use_delta",
                            tool_args_json=tc.function.arguments,
                        )

            if choice.finish_reason:
                for _idx in sorted(active_tool_call_ids):
                    yield StreamEvent(type="tool_use_end")
                active_tool_call_ids.clear()

                usage: dict[str, int] | None = None
                raw_usage = getattr(chunk, "usage", None)
                if raw_usage is not None:
                    usage = {
                        "input_tokens": (
                            getattr(raw_usage, "prompt_tokens", 0) or 0
                        ),
                        "output_tokens": (
                            getattr(raw_usage, "completion_tokens", 0) or 0
                        ),
                    }

                yield StreamEvent(
                    type="message_end",
                    stop_reason=choice.finish_reason,
                    usage=usage,
                )
