"""Metrics recording — counters, histograms, with no-op fallback."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator

try:
    from opentelemetry import metrics

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

# Lazily-created instruments
_meter: Any = None
_token_counter: Any = None
_tool_call_counter: Any = None
_cost_counter: Any = None
_latency_histogram: Any = None
_context_utilization_histogram: Any = None


def _ensure_instruments() -> None:
    """Create meter and instruments on first use."""
    global _meter, _token_counter, _tool_call_counter, _cost_counter
    global _latency_histogram, _context_utilization_histogram

    if not _HAS_OTEL or _meter is not None:
        return

    _meter = metrics.get_meter("harness")
    _token_counter = _meter.create_counter(
        "harness.tokens",
        description="Total tokens consumed",
        unit="tokens",
    )
    _tool_call_counter = _meter.create_counter(
        "harness.tool_calls",
        description="Total tool calls executed",
    )
    _cost_counter = _meter.create_counter(
        "harness.cost",
        description="Total cost in USD",
        unit="USD",
    )
    _latency_histogram = _meter.create_histogram(
        "harness.provider_latency",
        description="Provider response latency",
        unit="ms",
    )
    _context_utilization_histogram = _meter.create_histogram(
        "harness.context_utilization",
        description="Context window utilization percentage",
        unit="percent",
    )


def record_tokens(
    input_tokens: int = 0,
    output_tokens: int = 0,
    *,
    provider: str = "",
    model: str = "",
) -> None:
    """Record token usage."""
    if not _HAS_OTEL:
        return
    _ensure_instruments()
    attrs = {"provider": provider, "model": model}
    _token_counter.add(input_tokens, {"direction": "input", **attrs})
    _token_counter.add(output_tokens, {"direction": "output", **attrs})


def record_tool_call(tool_name: str, *, is_error: bool = False) -> None:
    """Record a tool call execution."""
    if not _HAS_OTEL:
        return
    _ensure_instruments()
    _tool_call_counter.add(1, {"tool": tool_name, "error": str(is_error).lower()})


def record_cost(cost: float, *, provider: str = "", model: str = "") -> None:
    """Record monetary cost."""
    if not _HAS_OTEL:
        return
    _ensure_instruments()
    _cost_counter.add(cost, {"provider": provider, "model": model})


def record_provider_latency(latency_ms: float, *, provider: str = "", model: str = "") -> None:
    """Record provider response latency in milliseconds."""
    if not _HAS_OTEL:
        return
    _ensure_instruments()
    _latency_histogram.record(latency_ms, {"provider": provider, "model": model})


def record_context_utilization(
    utilization_pct: float, *, provider: str = "", model: str = "",
) -> None:
    """Record context window utilization percentage (0-100)."""
    if not _HAS_OTEL:
        return
    _ensure_instruments()
    _context_utilization_histogram.record(
        utilization_pct, {"provider": provider, "model": model},
    )


@contextmanager
def timed_operation(
    name: str, *, provider: str = "", model: str = "",
) -> Generator[None, None, None]:
    """Context manager that measures wall-clock time and records as latency."""
    start = time.monotonic()
    yield
    elapsed_ms = (time.monotonic() - start) * 1000
    record_provider_latency(elapsed_ms, provider=provider, model=model)


def reset_instruments() -> None:
    """Reset module-level instruments — useful for test isolation."""
    global _meter, _token_counter, _tool_call_counter, _cost_counter
    global _latency_histogram, _context_utilization_histogram
    _meter = None
    _token_counter = None
    _tool_call_counter = None
    _cost_counter = None
    _latency_histogram = None
    _context_utilization_histogram = None
