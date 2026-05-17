"""Structured logging with trace correlation."""

from contextvars import ContextVar
import logging
import os
import sys
from typing import Any

from .tracer import get_current_span_id, get_current_trace_id

# ContextVar para armazenar contexto customizado de log
_log_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "log_context",
    default=None,
)

_logger_provider: Any = None
_module_logger = logging.getLogger(__name__)


def set_log_context(**kwargs) -> None:
    """
    Define contexto customizado para logs.

    O contexto será automaticamente adicionado a todos os logs da requisição atual.
    Usa ContextVar para garantir thread-safety e funcionar corretamente com async/await.

    Args:
        **kwargs: Campos a serem adicionados aos logs

    Example:
        >>> from otel_observability.logging import set_log_context
        >>> set_log_context(user_email="user@example.com", user_id="123")
    """
    context = _log_context.get({}).copy()
    context.update(kwargs)
    _log_context.set(context)


def get_log_context() -> dict[str, Any]:
    """
    Retorna o contexto atual de log.

    Returns:
        Dicionário com o contexto atual

    Example:
        >>> from otel_observability.logging import get_log_context
        >>> context = get_log_context()
        >>> print(context)
        {'user_email': 'user@example.com', 'user_id': '123'}
    """
    return _log_context.get({}).copy()


def clear_log_context() -> None:
    """
    Limpa o contexto de log.

    Deve ser chamado após processar uma requisição para evitar vazamento
    de contexto entre requisições. Em aplicações web, geralmente é chamado
    no finally de um middleware.

    Example:
        >>> from otel_observability.logging import clear_log_context
        >>> clear_log_context()
    """
    _log_context.set({})


class TraceContextFilter(logging.Filter):
    """
    Logging filter that adds trace_id, span_id and custom context to log records.

    This enables correlation between logs and distributed traces, and allows
    adding custom context (like user information, request IDs, etc.) that will
    be automatically included in all logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add trace context and custom context to log record."""
        record.trace_id = get_current_trace_id()
        record.span_id = get_current_span_id()

        # Adicionar contexto customizado automaticamente
        context = get_log_context()
        for key, value in context.items():
            setattr(record, key, value)

        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(self, *args, **kwargs):
        """Initialize JSON formatter with service tags."""
        super().__init__(*args, **kwargs)
        self._service_tags = self._get_service_tags()

    def _get_service_tags(self) -> dict[str, str]:
        """Get service tags from TelemetryConfig."""
        try:
            from .config import TelemetryConfig

            config = TelemetryConfig.from_env()
            return {
                "env": config.environment,
                "service": config.service_name,
                "version": config.service_version,
            }
        except Exception:
            # Fallback se não conseguir obter config
            return {
                "env": os.getenv("OTEL_ENVIRONMENT", "unknown"),
                "service": os.getenv("OTEL_SERVICE_NAME", "unknown-service"),
                "version": os.getenv("OTEL_SERVICE_VERSION", "0.0.0"),
            }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        from datetime import datetime
        import json

        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", ""),
            "span_id": getattr(record, "span_id", ""),
            # Unified Service Tags (explicitamente nos logs)
            "env": self._service_tags["env"],
            "service": self._service_tags["service"],
            "version": self._service_tags["version"],
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "trace_id",
                "span_id",
            ]:
                log_data[key] = value

        return json.dumps(log_data)


def configure_logging(
    level: str = "INFO",
    json_format: bool = False,
    logger_name: str | None = None,
) -> None:
    """
    Configure logging with trace correlation.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: Use JSON formatter (recommended for production).
        logger_name: Specific logger to configure. If None, configures root logger.

    Example:
        >>> from otel_observability import configure_logging
        >>> configure_logging(level="INFO", json_format=True)
    """
    # Get logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Add trace context filter
    handler.addFilter(TraceContextFilter())

    # Set formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        # Human-readable format with trace context
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [trace_id=%(trace_id)s span_id=%(span_id)s] "
            "%(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Prevent propagation to avoid duplicate logs
    if logger_name:
        logger.propagate = False


def _flatten_value(prefix: str, value: Any, result: dict, depth: int = 0) -> None:
    """Recursively flatten nested dicts into dot-notation keys.

    None values are dropped: the OTLP attribute protocol does not accept None,
    and including them causes the OTel SDK to emit a warning per attribute
    ("Invalid type NoneType for attribute ..."), which is itself shipped via
    OTLP and pollutes the log stream.
    """
    if value is None:
        return
    if depth >= 3:
        result[prefix] = str(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            _flatten_value(f"{prefix}.{k}", v, result, depth + 1)
    elif isinstance(value, str | int | float | bool):
        result[prefix] = value
    else:
        result[prefix] = str(value)


class FlattenAttributesLogRecordProcessor:
    """
    LogRecordProcessor that flattens nested dict attributes into dot-notation keys
    and serializes non-primitive objects to string before OTLP export.

    This ensures all extra fields passed via logger.info("msg", extra={...}) reach
    the OTLP exporter, since the OTLP protocol only supports primitive attribute values.

    Examples:
        {"output": {"count": 42}}       -> {"output.count": 42}
        {"input": {"account_id": "x"}}  -> {"input.account_id": "x"}
        {"input": some_dto}             -> {"input": str(some_dto)}
        {"error": "msg"}                -> {"error": "msg"}  (unchanged)
    """

    def on_emit(self, log_record: Any, context: Any = None) -> None:
        # Attributes live on the inner log_record, not on ReadWriteLogRecord directly
        inner = getattr(log_record, "log_record", log_record)
        if not inner.attributes:
            return
        flattened: dict[str, Any] = {}
        for key, value in inner.attributes.items():
            _flatten_value(key, value, flattened)
        try:
            from opentelemetry.attributes import BoundedAttributes

            inner.attributes = BoundedAttributes(attributes=flattened, immutable=False)
        except ImportError:
            inner.attributes = flattened

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def init_otlp_log_export(config: Any, resource: Any) -> None:
    """
    Initialize OTLP log exporter if logs endpoint is configured.

    This is an additive path — the existing stdout handler is kept.
    Called automatically by init_telemetry() when OTEL_EXPORTER_OTLP_LOGS_ENDPOINT is set.

    Args:
        config: TelemetryConfig instance.
        resource: OpenTelemetry Resource (shared with TracerProvider).
    """
    global _logger_provider

    if not config.otlp_logs_endpoint:
        return

    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        _logger_provider = LoggerProvider(resource=resource)

        endpoint = config.otlp_logs_endpoint.strip()
        log_exporter = OTLPLogExporter(
            endpoint=endpoint,
            headers=config.otlp_headers or {},
        )
        _logger_provider.add_log_record_processor(FlattenAttributesLogRecordProcessor())
        _logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        set_logger_provider(_logger_provider)

        otel_handler = LoggingHandler(
            level=logging.NOTSET,
            logger_provider=_logger_provider,
        )
        otel_handler.addFilter(TraceContextFilter())
        logging.getLogger().addHandler(otel_handler)

        _module_logger.info(f"OTLP log exporter initialized: endpoint={endpoint}")

    except ImportError:
        _module_logger.warning(
            "OTLP log exporter not available. Ensure opentelemetry-sdk>=1.20.0 is installed."
        )
    except Exception as e:
        _module_logger.warning(f"Failed to initialize OTLP log exporter: {e}", exc_info=True)


def shutdown_log_export(timeout: int = 30) -> None:
    """
    Flush and shutdown the OTLP log exporter.

    Called automatically by shutdown_telemetry().

    Args:
        timeout: Maximum time to wait for flush (seconds).
    """
    global _logger_provider

    if _logger_provider:
        try:
            _logger_provider.force_flush(timeout_millis=timeout * 1000)
            _logger_provider.shutdown()
        except Exception as e:
            _module_logger.warning(f"Error during log export shutdown: {e}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with trace correlation enabled.

    Args:
        name: Logger name (usually __name__).

    Returns:
        Logger instance.

    Example:
        >>> from otel_observability import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing request")
        # Contexto customizado será adicionado automaticamente se configurado via set_log_context()
        # Campos extras podem ser adicionados via parâmetro extra:
        >>> logger.info("Processing request", extra={"count": 10})
    """
    return logging.getLogger(name)
