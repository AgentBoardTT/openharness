"""ModelRouter — intelligent routing across providers and models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from harness.providers.budget import BudgetExhaustedError, TokenBudgetTracker
from harness.types.providers import ChatMessage, ProviderAdapter, StreamEvent
from harness.types.tools import ToolDef


class RoutingStrategy(Enum):
    """Model routing strategies."""

    MANUAL = "manual"
    COST_OPTIMIZED = "cost_optimized"
    QUALITY_FIRST = "quality_first"
    LATENCY_FIRST = "latency_first"


class ModelRouter:
    """Routes requests to appropriate models based on strategy and budget.

    Implements ProviderAdapter protocol so it can be used as a drop-in replacement.
    """

    def __init__(
        self,
        primary: ProviderAdapter,
        *,
        strategy: RoutingStrategy = RoutingStrategy.MANUAL,
        simple_task_provider: ProviderAdapter | None = None,
        budget: TokenBudgetTracker | None = None,
    ) -> None:
        self._primary = primary
        self._strategy = strategy
        self._simple_task_provider = simple_task_provider
        self._budget = budget or TokenBudgetTracker()

    @property
    def model_id(self) -> str:
        return self._primary.model_id

    @property
    def budget(self) -> TokenBudgetTracker:
        return self._budget

    def estimate_tokens(self, text: str) -> int:
        return self._primary.estimate_tokens(text)

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDef],
        system: str,
        max_tokens: int,
    ) -> Any:
        """Route and stream, recording usage from message_end events."""
        # Check budget before calling
        self._budget.check_budget()

        provider = self._select_provider(messages)

        async for event in provider.chat_completion_stream(
            messages=messages, tools=tools, system=system, max_tokens=max_tokens,
        ):
            # Intercept message_end to record usage
            if event.type == "message_end" and event.usage:
                input_tokens = event.usage.get("input_tokens", 0)
                output_tokens = event.usage.get("output_tokens", 0)

                # Estimate cost from model info
                cost = 0.0
                model_info = getattr(provider, "_model_info", None)
                if model_info:
                    in_cost = input_tokens * model_info.input_cost_per_mtok
                    out_cost = output_tokens * model_info.output_cost_per_mtok
                    cost = (in_cost + out_cost) / 1_000_000

                self._budget.record_usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                )

            yield event

    def _select_provider(self, messages: list[ChatMessage]) -> ProviderAdapter:
        """Select the best provider based on strategy."""
        if self._strategy == RoutingStrategy.MANUAL:
            return self._primary

        if self._strategy == RoutingStrategy.COST_OPTIMIZED:
            # Use simple task model for short conversations
            if self._simple_task_provider and len(messages) <= 4:
                return self._simple_task_provider
            return self._primary

        # QUALITY_FIRST and LATENCY_FIRST: just use primary for now
        return self._primary

    def format_tool_result(
        self, tool_use_id: str, content: str, is_error: bool = False,
    ) -> ChatMessage:
        return self._primary.format_tool_result(tool_use_id, content, is_error)

    def format_tool_use(
        self, tool_use_id: str, name: str, args: dict[str, Any],
    ) -> dict[str, Any]:
        return self._primary.format_tool_use(tool_use_id, name, args)
