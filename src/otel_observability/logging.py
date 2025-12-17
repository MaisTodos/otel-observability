"""Structured logging with trace correlation."""

from contextvars import ContextVar
import logging
import sys
from typing import Any

from .tracer import get_current_span_id, get_current_trace_id

# ContextVar para armazenar contexto customizado de log
_log_context: ContextVar[dict[str, Any]] = ContextVar(
    "log_context",
    default={},
)


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
