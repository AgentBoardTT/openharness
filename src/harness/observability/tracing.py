"""Tracer, span context manager, no-op fallback."""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
from typing import Any, Generator

try:
    from opentelemetry import trace
    from opentelemetry.context import attach, detach
    from opentelemetry.trace.propagation import get_current_span
    from opentelemetry.propagate import inject, extract

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


class _NoOpSpan:
    """No-op span used when OTel is not installed."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def end(self) -> None:
        pass


class _NoOpTracer:
    """No-op tracer used when OTel is not installed."""

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    @contextmanager
    def start_as_current_span(
        self, name: str, **kwargs: Any,
    ) -> Generator[_NoOpSpan, None, None]:
        yield _NoOpSpan()


def get_tracer(name: str = "harness") -> Any:
    """Return an OTel Tracer or a no-op fallback."""
    if _HAS_OTEL:
        return trace.get_tracer(name)
    return _NoOpTracer()


@contextmanager
def span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Context manager that creates an OTel span or no-op."""
    if _HAS_OTEL:
        tracer = trace.get_tracer("harness")
        with tracer.start_as_current_span(name, attributes=attributes) as s:
            yield s
    else:
        yield _NoOpSpan()


def inject_context(carrier: dict[str, str] | None = None) -> dict[str, str]:
    """Inject current trace context into a carrier dict for sub-agent propagation."""
    carrier = carrier or {}
    if _HAS_OTEL:
        inject(carrier)
    return carrier


def extract_context(carrier: dict[str, str]) -> Any:
    """Extract trace context from a carrier dict."""
    if _HAS_OTEL:
        return extract(carrier)
    return None
