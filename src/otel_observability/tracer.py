"""Core tracing functionality with distributed tracing support."""

from collections.abc import Callable
from functools import wraps
import logging
from typing import Any

from opentelemetry import trace as trace_api
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from .config import TelemetryConfig

logger = logging.getLogger(__name__)

_tracer_provider: TracerProvider | None = None
_config: TelemetryConfig | None = None


def init_telemetry(config: TelemetryConfig | None = None) -> None:
    """
    Initialize OpenTelemetry tracing with distributed tracing support.

    Args:
        config: Optional TelemetryConfig. If None, loads from environment.

    Example:
        >>> from otel_observability import init_telemetry
        >>> init_telemetry()
    """
    global _tracer_provider, _config

    if _tracer_provider is not None:
        logger.warning("Telemetry already initialized. Skipping.")
        return

    _config = config or TelemetryConfig.from_env()

    resource = Resource.create(
        {
            SERVICE_NAME: _config.service_name,
            SERVICE_VERSION: _config.service_version,
            DEPLOYMENT_ENVIRONMENT: _config.environment,
            "runtime": "lambda" if _config.is_lambda else "container",
            "telemetry.sdk.name": "otel-observability",
            "telemetry.sdk.version": "0.1.0",
        }
    )

    sampler = ParentBased(root=TraceIdRatioBased(_config.sample_rate))
    _tracer_provider = TracerProvider(resource=resource, sampler=sampler)

    if _config.traces_enabled and _config.otlp_traces_endpoint:
        otlp_exporter = OTLPSpanExporter(
            endpoint=_config.otlp_traces_endpoint.strip(),
            headers=_config.otlp_headers or {},
        )
        _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    else:
        logger.info(
            "Traces OTLP exporter disabled — set OTEL_EXPORTER_OTLP_TRACES_ENDPOINT to enable."
        )

    if _config.enable_console_export:
        console_exporter = ConsoleSpanExporter()
        _tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))

    trace_api.set_tracer_provider(_tracer_provider)

    propagators = [
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator(),
    ]

    from opentelemetry.propagators.composite import CompositeHTTPPropagator

    composite_propagator = CompositeHTTPPropagator(propagators)
    set_global_textmap(composite_propagator)

    from .logging import init_otlp_log_export

    init_otlp_log_export(_config, resource)

    logger.info(
        f"Telemetry initialized: service={_config.service_name}, "
        f"env={_config.environment}, version={_config.service_version}, "
        f"traces_endpoint={_config.otlp_traces_endpoint}, "
        f"logs_endpoint={_config.otlp_logs_endpoint}, "
        f"sample_rate={_config.sample_rate}"
    )


def shutdown_telemetry(timeout: int = 30) -> None:
    """
    Shutdown telemetry and flush remaining spans.

    Args:
        timeout: Maximum time to wait for flush (seconds).

    Example:
        >>> shutdown_telemetry()
    """
    global _tracer_provider

    from .logging import shutdown_log_export

    shutdown_log_export(timeout=timeout)

    if _tracer_provider:
        _tracer_provider.force_flush(timeout_millis=timeout * 1000)
        _tracer_provider.shutdown()
        logger.info("Telemetry shutdown complete")


def get_tracer(name: str = __name__) -> trace_api.Tracer:
    """
    Get a tracer instance.

    Args:
        name: Tracer name (usually __name__ of the module).

    Returns:
        Tracer instance.

    Example:
        >>> tracer = get_tracer(__name__)
        >>> with tracer.start_as_current_span("my_operation"):
        ...     pass
    """
    return trace_api.get_tracer(name)


def get_current_span() -> trace_api.Span:
    """
    Get the current active span.

    Returns:
        Current span instance.

    Example:
        >>> span = get_current_span()
        >>> span.set_attribute("custom.key", "value")
    """
    return trace_api.get_current_span()


def get_current_trace_id() -> str:
    """
    Get current trace ID as hex string.

    Returns:
        Trace ID (32 hex characters) or empty string if no active trace.

    Example:
        >>> trace_id = get_current_trace_id()
        >>> print(f"Trace ID: {trace_id}")
    """
    span = trace_api.get_current_span()
    ctx = span.get_span_context()
    if ctx.trace_id == 0:
        return ""
    return format(ctx.trace_id, "032x")


def get_current_span_id() -> str:
    """
    Get current span ID as hex string.

    Returns:
        Span ID (16 hex characters) or empty string if no active span.

    Example:
        >>> span_id = get_current_span_id()
        >>> print(f"Span ID: {span_id}")
    """
    span = trace_api.get_current_span()
    ctx = span.get_span_context()
    if ctx.span_id == 0:
        return ""
    return format(ctx.span_id, "016x")


def trace(
    name: str | None = None,
    attributes: dict | None = None,
):
    """
    Decorator to trace a function with distributed tracing support.

    Args:
        name: Span name. If None, uses function name.
        attributes: Additional span attributes.

    Example:
        >>> @trace("process_payment")
        >>> def process_payment(amount: float):
        ...     return {"status": "success"}
        >>>
        >>> @trace(attributes={"category": "business"})
        >>> async def async_operation():
        ...     return "result"
    """

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        module_name = func.__module__

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            tracer = get_tracer(module_name)
            with tracer.start_as_current_span(span_name) as span:
                # Set custom attributes
                if attributes:
                    span.set_attributes(attributes)

                # Add function metadata
                span.set_attribute("code.function", func.__name__)
                span.set_attribute("code.namespace", module_name)

                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            tracer = get_tracer(module_name)
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    span.set_attributes(attributes)

                span.set_attribute("code.function", func.__name__)
                span.set_attribute("code.namespace", module_name)

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        import asyncio
        import inspect

        if asyncio.iscoroutinefunction(func) or inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
