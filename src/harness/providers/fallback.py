"""FallbackProvider — wraps multiple providers with automatic fallback."""

from __future__ import annotations

from typing import Any

from harness.types.providers import ChatMessage, ProviderAdapter, StreamEvent
from harness.types.tools import ToolDef


class FallbackProvider:
    """Provider adapter that tries providers in order, falling back on connection errors.

    Only falls back on connection-phase failures (before streaming starts).
    Once the first event is yielded, mid-stream failures propagate to the caller
    — there is no mid-stream fallback because the conversation state would be
    corrupted by partial output.
    """

    def __init__(self, providers: list[ProviderAdapter]) -> None:
        if not providers:
            raise ValueError("FallbackProvider requires at least one provider")
        self._providers = providers
        self._active_index = 0

    @property
    def model_id(self) -> str:
        return self._providers[self._active_index].model_id

    @property
    def active_provider(self) -> ProviderAdapter:
        return self._providers[self._active_index]

    def estimate_tokens(self, text: str) -> int:
        return self._providers[self._active_index].estimate_tokens(text)

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int,
    ) -> Any:
        """Try each provider in order. Fall back only on connection-phase errors.

        Once the first event has been yielded to the caller, any error
        propagates directly — no fallback is attempted because the caller
        has already consumed partial output.
        """
        last_error: Exception | None = None

        for i in range(len(self._providers)):
            idx = (self._active_index + i) % len(self._providers)
            provider = self._providers[idx]

            # --- Connection phase: errors here trigger fallback ---
            try:
                stream = provider.chat_completion_stream(
                    messages=messages,
                    tools=tools,
                    system=system,
                    max_tokens=max_tokens,
                )
                # Attempt to get the first event to confirm the connection works.
                # For async generators this is the first __anext__() call.
                first_event = None
                async for event in stream:
                    first_event = event
                    break
            except (ConnectionError, OSError, TimeoutError) as e:
                last_error = e
                continue

            # If the stream was empty (no events at all), that's still a success
            if first_event is None:
                self._active_index = idx
                return

            # --- Streaming phase: errors propagate, no fallback ---
            self._active_index = idx
            yield first_event
            async for event in stream:
                yield event
            return

        # All providers failed during connection phase
        if last_error is not None:
            raise last_error
        raise ConnectionError("All providers in fallback chain failed")

    def format_tool_result(
        self, tool_use_id: str, content: str, is_error: bool = False,
    ) -> ChatMessage:
        return self._providers[self._active_index].format_tool_result(
            tool_use_id, content, is_error,
        )

    def format_tool_use(
        self, tool_use_id: str, name: str, args: dict[str, Any],
    ) -> dict[str, Any]:
        return self._providers[self._active_index].format_tool_use(
            tool_use_id, name, args,
        )
