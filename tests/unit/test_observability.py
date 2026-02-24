"""Tests for the observability module."""

from __future__ import annotations

from harness.observability.tracing import (
    _NoOpSpan,
    _NoOpTracer,
    get_tracer,
    inject_context,
    extract_context,
    span,
)
from harness.observability.metrics import (
    record_tokens,
    record_tool_call,
    record_cost,
    record_provider_latency,
    record_context_utilization,
    reset_instruments,
    timed_operation,
)
from harness.observability.exporters import ObservabilityConfig, configure_exporters, shutdown


class TestNoOpFallback:
    """Test that everything works when OTel is not installed."""

    def test_noop_span_methods(self) -> None:
        s = _NoOpSpan()
        s.set_attribute("key", "value")
        s.set_status(None)
        s.record_exception(ValueError("test"))
        s.add_event("test_event")
        s.end()

    def test_noop_tracer(self) -> None:
        tracer = _NoOpTracer()
        s = tracer.start_span("test")
        assert isinstance(s, _NoOpSpan)

        with tracer.start_as_current_span("test") as s2:
            assert isinstance(s2, _NoOpSpan)

    def test_get_tracer_returns_something(self) -> None:
        tracer = get_tracer()
        assert tracer is not None

    def test_span_context_manager(self) -> None:
        with span("test_span", attributes={"key": "value"}) as s:
            assert s is not None

    def test_inject_extract_context(self) -> None:
        carrier = inject_context()
        assert isinstance(carrier, dict)

        result = extract_context(carrier)
        # May be None (no-op) or a real context

    def test_metric_functions_noop(self) -> None:
        """Metric recording should not fail when OTel is absent."""
        record_tokens(100, 50, provider="test", model="test")
        record_tool_call("Bash", is_error=False)
        record_cost(0.01, provider="test", model="test")
        record_provider_latency(100.0, provider="test", model="test")
        record_context_utilization(50.0, provider="test", model="test")

    def test_timed_operation(self) -> None:
        with timed_operation("test", provider="test", model="test"):
            pass  # Should not raise


class TestObservabilityConfig:
    def test_default_config(self) -> None:
        config = ObservabilityConfig()
        assert not config.enabled
        assert config.exporter == "console"
        assert config.service_name == "harness-agent"

    def test_disabled_config_returns_false(self) -> None:
        config = ObservabilityConfig(enabled=False)
        result = configure_exporters(config)
        assert result is False

    def test_shutdown_noop(self) -> None:
        """Shutdown should not raise even if nothing was configured."""
        shutdown()

    def test_reset_instruments(self) -> None:
        """reset_instruments should not raise and should clear state."""
        reset_instruments()
        # Metric calls after reset should still work (re-creates instruments)
        record_tokens(10, 5, provider="test", model="test")
        reset_instruments()
