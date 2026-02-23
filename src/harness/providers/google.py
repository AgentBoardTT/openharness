"""Google Gemini provider adapter."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from harness.providers.base import BaseProvider
from harness.types.providers import ChatMessage, StreamEvent
from harness.types.tools import ToolDef

logger = logging.getLogger(__name__)


class GoogleProvider(BaseProvider):
    """Provider adapter for Google's Gemini models.

    Uses the official ``google-genai`` Python SDK with its async streaming
    interface.  All stream events from the SDK are translated into the
    provider-agnostic :class:`~harness.types.providers.StreamEvent` format.

    Parameters
    ----------
    api_key:
        Google API key.  When *None* the value of the ``GOOGLE_API_KEY``
        environment variable is used as a fallback.
    model:
        Model ID to use for completions (default ``"gemini-2.0-flash"``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
    ) -> None:
        super().__init__(model)
        # Defer import so the rest of the codebase can be imported even if the
        # google-genai package is not installed (useful for type checking).
        try:
            from google import genai
        except ImportError as exc:
            raise ImportError(
                "The 'google-genai' package is required for GoogleProvider. "
                "Install it with: pip install google-genai"
            ) from exc

        resolved_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self._client = genai.Client(api_key=resolved_key)

        # Maps tool_use_id -> tool_name so format_tool_result can embed
        # the name required by Gemini's function_response wire format.
        self._last_tool_names: dict[str, str] = {}

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
        """Stream a chat completion from the Google Gemini API.

        Converts the provider-agnostic message list and tool definitions into
        the Gemini wire format, opens a streaming request, and yields
        :class:`~harness.types.providers.StreamEvent` objects as chunks arrive.

        Parameters
        ----------
        messages:
            Conversation history (system messages are extracted separately).
        tools:
            Tool definitions available to the model.
        system:
            System prompt (used as ``system_instruction`` in the Gemini API).
        max_tokens:
            Maximum number of tokens to generate.

        Yields
        ------
        StreamEvent
            One event per meaningful chunk from the Gemini stream.
        """
        return self._stream(messages, tools, system, max_tokens)

    async def _stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Internal async generator — yielded by :meth:`chat_completion_stream`."""
        from google.genai import types

        # Extract the system prompt: last system-role message wins.
        resolved_system = system
        for msg in messages:
            if msg.role == "system":
                if isinstance(msg.content, str):
                    resolved_system = msg.content

        gemini_contents = self._to_gemini_contents(messages)
        gemini_tools = self._to_gemini_tools(tools)

        config = types.GenerateContentConfig(
            system_instruction=resolved_system,
            tools=gemini_tools,
            max_output_tokens=max_tokens,
        )

        try:
            async for chunk in self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=gemini_contents,
                config=config,
            ):
                # Guard against empty candidate lists (safety filtering, etc.).
                if not chunk.candidates:
                    continue

                candidate = chunk.candidates[0]

                # Guard against a missing content object in the candidate.
                if candidate.content is None or not candidate.content.parts:
                    # Still check finish_reason below.
                    parts: list[Any] = []
                else:
                    parts = candidate.content.parts

                for part in parts:
                    if part.text:
                        yield StreamEvent(type="text_delta", text=part.text)
                    elif part.function_call:
                        fc = part.function_call
                        # Gemini does not supply a stable call ID; synthesise one
                        # from the function name and object identity.
                        tool_id = f"gemini_{fc.name}_{id(fc)}"
                        # Remember the mapping so format_tool_result can embed it.
                        self._last_tool_names[tool_id] = fc.name
                        yield StreamEvent(
                            type="tool_use_start",
                            tool_use_id=tool_id,
                            tool_name=fc.name,
                        )
                        yield StreamEvent(
                            type="tool_use_delta",
                            tool_args_json=json.dumps(
                                dict(fc.args) if fc.args else {}
                            ),
                        )
                        yield StreamEvent(type="tool_use_end")

                if candidate.finish_reason:
                    # Determine the stop reason based on whether any function
                    # calls were present in this chunk's parts.
                    has_function_call = any(
                        p.function_call for p in parts
                    )
                    stop = "tool_use" if has_function_call else "end_turn"

                    usage_dict: dict[str, int] = {}
                    if chunk.usage_metadata:
                        usage_dict = {
                            "input_tokens": chunk.usage_metadata.prompt_token_count or 0,
                            "output_tokens": chunk.usage_metadata.candidates_token_count or 0,
                        }

                    yield StreamEvent(
                        type="message_end",
                        stop_reason=stop,
                        usage=usage_dict,
                    )
        except Exception as exc:
            logger.error(
                "Error during Gemini streaming request: %s: %s",
                type(exc).__name__,
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # BaseProvider override — Gemini needs tool_name in function_response
    # ------------------------------------------------------------------

    def format_tool_result(
        self,
        tool_use_id: str,
        content: str,
        is_error: bool = False,
    ) -> ChatMessage:
        """Build a Gemini-compatible tool-result :class:`ChatMessage`.

        Gemini's ``function_response`` wire format requires the function name
        alongside the call ID.  This override embeds ``tool_name`` in the
        result block so that :meth:`_to_gemini_contents` can construct a
        proper :class:`google.genai.types.Part.from_function_response`.

        Parameters
        ----------
        tool_use_id:
            The opaque ID from the corresponding ``tool_use`` block.
        content:
            Serialised text output from the tool (or error message).
        is_error:
            When *True*, the block is marked as an error result.

        Returns
        -------
        ChatMessage
            A ``role="user"`` message carrying the tool result.
        """
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "tool_name": self._last_tool_names.get(tool_use_id, "unknown"),
        }
        if is_error:
            block["is_error"] = True
        return ChatMessage(role="user", content=[block])

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _to_gemini_contents(
        self, messages: list[ChatMessage]
    ) -> list[Any]:
        """Convert our :class:`ChatMessage` list to Gemini ``Content`` objects.

        System-role messages are stripped (the system prompt is passed via
        ``system_instruction`` in the config).  Assistant messages use the
        Gemini ``"model"`` role.  Tool results are encoded as
        ``Part.from_function_response`` blocks within a ``"user"`` turn.

        Parameters
        ----------
        messages:
            Provider-agnostic message list.

        Returns
        -------
        list[types.Content]
            Contents list ready for the Gemini SDK.
        """
        from google.genai import types

        result: list[types.Content] = []

        for msg in messages:
            if msg.role == "system":
                # Handled separately via system_instruction.
                continue

            if msg.role == "user":
                if isinstance(msg.content, list):
                    # Check whether these are tool_result blocks.
                    tool_result_parts: list[types.Part] = []
                    plain_parts: list[types.Part] = []

                    for block in msg.content:
                        if block.get("type") == "tool_result":
                            tool_result_parts.append(
                                types.Part.from_function_response(
                                    name=block.get("tool_name", "unknown"),
                                    response={"result": block.get("content", "")},
                                )
                            )
                        else:
                            # Fallback: treat unrecognised blocks as text.
                            text_val = block.get("text") or str(block)
                            plain_parts.append(types.Part.from_text(text=text_val))

                    if tool_result_parts:
                        result.append(
                            types.Content(role="user", parts=tool_result_parts)
                        )
                    if plain_parts:
                        result.append(
                            types.Content(role="user", parts=plain_parts)
                        )
                else:
                    result.append(
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=str(msg.content))],
                        )
                    )

            elif msg.role == "assistant":
                if isinstance(msg.content, list):
                    # May contain text and/or tool_use blocks.
                    parts: list[types.Part] = []
                    for block in msg.content:
                        block_type = block.get("type")
                        if block_type == "text":
                            parts.append(
                                types.Part.from_text(text=block.get("text", ""))
                            )
                        elif block_type == "tool_use":
                            parts.append(
                                types.Part.from_function_call(
                                    name=block["name"],
                                    args=block.get("input", {}),
                                )
                            )
                    if parts:
                        result.append(types.Content(role="model", parts=parts))
                else:
                    result.append(
                        types.Content(
                            role="model",
                            parts=[types.Part.from_text(text=str(msg.content))],
                        )
                    )

        return result

    def _to_gemini_tools(self, tools: list[ToolDef]) -> list[Any]:
        """Convert :class:`ToolDef` objects to the Gemini tool schema format.

        Builds on :meth:`~harness.providers.base.BaseProvider._make_tool_defs`
        which produces the generic JSON-Schema intermediate form, then wraps
        each entry in a :class:`google.genai.types.FunctionDeclaration`.

        Parameters
        ----------
        tools:
            Tool definitions to convert.

        Returns
        -------
        list[types.Tool]
            A single-element list containing a :class:`types.Tool` with all
            function declarations, or an empty list when *tools* is empty.
        """
        if not tools:
            return []

        from google.genai import types

        declarations: list[types.FunctionDeclaration] = []
        for tool_def in self._make_tool_defs(tools):
            schema = tool_def["input_schema"]
            declarations.append(
                types.FunctionDeclaration(
                    name=tool_def["name"],
                    description=tool_def["description"],
                    parameters=schema,
                )
            )

        return [types.Tool(function_declarations=declarations)]
