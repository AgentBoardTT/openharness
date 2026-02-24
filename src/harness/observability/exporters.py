"""OTel provider setup (console, OTLP, Jaeger exporters)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

_tracer_provider: Any = None
_meter_provider: Any = None


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """Configuration for OTel exporters."""

    enabled: bool = False
    exporter: str = "console"  # console | otlp | jaeger | none
    otlp_endpoint: str = "http://localhost:4317"
    service_name: str = "harness-agent"
    extra: dict[str, str] = field(default_factory=dict)


def configure_exporters(config: ObservabilityConfig) -> bool:
    """Set up OTel TracerProvider and MeterProvider.

    Returns True if OTel was configured, False if unavailable or disabled.
    """
    global _tracer_provider, _meter_provider

    if not _HAS_OTEL or not config.enabled:
        return False

    resource = Resource.create({"service.name": config.service_name})

    # Tracer
    tp = TracerProvider(resource=resource)

    if config.exporter == "console":
        tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif config.exporter == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            tp.add_span_processor(BatchSpanProcessor(
                OTLPSpanExporter(endpoint=config.otlp_endpoint),
            ))
        except ImportError:
            tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif config.exporter == "jaeger":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            tp.add_span_processor(BatchSpanProcessor(
                OTLPSpanExporter(endpoint=config.otlp_endpoint),
            ))
        except ImportError:
            tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(tp)
    _tracer_provider = tp

    # Meter
    if config.exporter == "console":
        reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    elif config.exporter in ("otlp", "jaeger"):
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

            reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=config.otlp_endpoint),
            )
        except ImportError:
            reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    else:
        reader = PeriodicExportingMetricReader(ConsoleMetricExporter())

    mp = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(mp)
    _meter_provider = mp

    return True


def shutdown() -> None:
    """Shut down OTel providers gracefully."""
    global _tracer_provider, _meter_provider

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
        except Exception:
            pass
        _tracer_provider = None

    if _meter_provider is not None:
        try:
            _meter_provider.shutdown()
        except Exception:
            pass
        _meter_provider = None
