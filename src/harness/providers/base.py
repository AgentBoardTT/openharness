"""Base provider with shared retry logic, token estimation, and tool schema conversion."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from harness.types.providers import ChatMessage, StreamEvent
from harness.types.tools import ToolDef, ToolParam

logger = logging.getLogger(__name__)

# Errors that are worth retrying on — rate limits and server overload.
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 529})
_MAX_RETRIES: int = 3
_BACKOFF_BASE: float = 1.0  # seconds; doubled each retry


def _is_retryable(exc: BaseException) -> bool:
    """Return True when *exc* represents a transient error worth retrying."""
    exc_type_name = type(exc).__name__
    # Anthropic SDK raises RateLimitError (429) and OverloadedError (529).
    retryable_names = {"RateLimitError", "OverloadedError", "APIStatusError"}
    if exc_type_name in retryable_names:
        return True
    # Generic check: look for a status_code attribute (OpenAI / httpx style).
    status_code: int | None = getattr(exc, "status_code", None)
    if status_code is not None and status_code in _RETRYABLE_STATUS_CODES:
        return True
    return False


class BaseProvider(ABC):
    """Abstract base class for all provider adapters.

    Concrete sub-classes must implement :meth:`chat_completion_stream`.  All
    other public methods have sensible default implementations that may be
    overridden when provider-specific behaviour is needed.

    Parameters
    ----------
    model:
        The model identifier string (e.g. ``"claude-sonnet-4-6"``).
    """

    def __init__(self, model: str) -> None:
        self._model = model

    # ------------------------------------------------------------------
    # Public interface (ProviderAdapter protocol)
    # ------------------------------------------------------------------

    @property
    def model_id(self) -> str:
        """The model identifier being used by this provider instance."""
        return self._model

    def estimate_tokens(self, text: str) -> int:
        """Rough token count estimate — approximately 4 characters per token.

        This is intentionally imprecise; use it only for progress tracking and
        context-window budgeting, not for billing.

        Parameters
        ----------
        text:
            Raw text whose token count to estimate.

        Returns
        -------
        int
            Estimated token count (always >= 0).

        Examples
        --------
        >>> provider.estimate_tokens("Hello, world!")
        3
        """
        return max(0, len(text) // 4)

    def format_tool_result(
        self,
        tool_use_id: str,
        content: str,
        is_error: bool = False,
    ) -> ChatMessage:
        """Build a provider-agnostic tool-result :class:`ChatMessage`.

        The default representation stores the result as a list-style content
        block that mirrors the Anthropic tool_result format.  Providers that
        need a different wire format should override this method.

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
        }
        if is_error:
            block["is_error"] = True
        return ChatMessage(role="user", content=[block])

    def format_tool_use(
        self,
        tool_use_id: str,
        name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a tool-use content block for inclusion in an assistant message.

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
            A content block dict suitable for embedding in a
            :class:`ChatMessage` content list.
        """
        return {
            "type": "tool_use",
            "id": tool_use_id,
            "name": name,
            "input": args,
        }

    # ------------------------------------------------------------------
    # Abstract interface — must be implemented by sub-classes
    # ------------------------------------------------------------------

    @abstractmethod
    def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a chat completion, yielding :class:`StreamEvent` objects.

        Implementations should be ``async def`` generators (returning an
        :class:`AsyncIterator`) decorated with ``@abstractmethod``.  Retry
        logic should be wired in via :meth:`_retry_with_backoff`.

        Parameters
        ----------
        messages:
            Ordered list of conversation messages (system excluded).
        tools:
            Tool definitions the model may call.
        system:
            System prompt string (passed separately for providers that handle
            it outside the message list).
        max_tokens:
            Hard upper bound on generated tokens.

        Yields
        ------
        StreamEvent
            Individual stream events as they arrive from the provider.
        """
        ...

    # ------------------------------------------------------------------
    # Protected helpers — available to sub-classes
    # ------------------------------------------------------------------

    async def _retry_with_backoff(
        self,
        coro_fn: Any,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call *coro_fn* with exponential back-off on transient errors.

        Up to :data:`_MAX_RETRIES` additional attempts are made when the
        raised exception is identified as retryable by :func:`_is_retryable`.
        The delay doubles after each failure, starting at :data:`_BACKOFF_BASE`
        seconds.

        Parameters
        ----------
        coro_fn:
            An async callable.  It is invoked as ``await coro_fn(*args, **kwargs)``.
        *args, **kwargs:
            Forwarded verbatim to *coro_fn*.

        Returns
        -------
        Any
            Whatever *coro_fn* returns on success.

        Raises
        ------
        Exception
            Re-raises the last exception when all retries are exhausted.
        """
        delay = _BACKOFF_BASE
        last_exc: BaseException | None = None

        for attempt in range(1, _MAX_RETRIES + 2):  # +2: initial attempt + retries
            try:
                return await coro_fn(*args, **kwargs)
            except Exception as exc:
                if not _is_retryable(exc) or attempt > _MAX_RETRIES + 1:
                    raise
                last_exc = exc
                logger.warning(
                    "Transient error on attempt %d/%d (%s). Retrying in %.1fs.",
                    attempt,
                    _MAX_RETRIES + 1,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2.0

        # Should be unreachable, but satisfies the type checker.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unexpected state in _retry_with_backoff")  # pragma: no cover

    def _make_tool_defs(self, tools: list[ToolDef]) -> list[dict[str, Any]]:
        """Convert :class:`ToolDef` objects into JSON-Schema-style dicts.

        The output format is intentionally provider-neutral.  Provider-specific
        adapters convert this intermediate representation into the exact wire
        format expected by their SDK.

        Parameters
        ----------
        tools:
            Tool definitions to convert.

        Returns
        -------
        list[dict[str, Any]]
            One dict per tool, each with keys ``name``, ``description``, and
            ``input_schema`` (a JSON Schema ``object``).

        Examples
        --------
        >>> defs = provider._make_tool_defs([ToolDef(
        ...     name="read_file",
        ...     description="Read a file from disk.",
        ...     parameters=(ToolParam(name="path", type="string",
        ...                          description="Absolute path", required=True),),
        ... )])
        >>> defs[0]["name"]
        'read_file'
        >>> defs[0]["input_schema"]["properties"]["path"]["type"]
        'string'
        """
        result: list[dict[str, Any]] = []
        for tool in tools:
            properties: dict[str, Any] = {}
            required_params: list[str] = []

            for param in tool.parameters:
                prop = self._param_to_schema(param)
                properties[param.name] = prop
                if param.required:
                    required_params.append(param.name)

            schema: dict[str, Any] = {
                "type": "object",
                "properties": properties,
            }
            if required_params:
                schema["required"] = required_params

            result.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": schema,
                }
            )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _param_to_schema(param: ToolParam) -> dict[str, Any]:
        """Render a single :class:`ToolParam` as a JSON Schema property dict."""
        prop: dict[str, Any] = {
            "type": param.type,
            "description": param.description,
        }
        if param.enum is not None:
            prop["enum"] = list(param.enum)
        if param.default is not None:
            prop["default"] = param.default
        # Array types require an items schema (OpenAI enforces this).
        if param.type == "array":
            prop["items"] = param.items if param.items is not None else {"type": "string"}
        return prop
