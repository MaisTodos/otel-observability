"""
OpenTelemetry Observability Library
====================================

Biblioteca simplificada de OpenTelemetry para FastAPI e AWS Lambda com:
- Tracing distribuído (W3C Trace Context + AWS X-Ray)
- Logging estruturado com correlação de traces
- Auto-instrumentação
- Integração com Datadog

Example (FastAPI):
    >>> from fastapi import FastAPI
    >>> from otel_observability.fastapi import instrument_fastapi
    >>>
    >>> app = FastAPI()
    >>>
    >>> # Instrumentar ANTES de definir rotas
    >>> instrument_fastapi(app)
    >>>
    >>> @app.get("/users/{user_id}")
    >>> async def get_user(user_id: int):
    ...     return {"user_id": user_id}

Example (Lambda):
    >>> from otel_observability.aws_lambda import instrument_lambda_handler
    >>> from otel_observability import get_logger
    >>>
    >>> logger = get_logger(__name__)
    >>>
    >>> @instrument_lambda_handler()
    >>> def lambda_handler(event, context):
    ...     logger.info("Processing request")
    ...     return {"statusCode": 200, "body": "OK"}

Example (Manual Tracing):
    >>> from otel_observability import trace, get_logger
    >>>
    >>> logger = get_logger(__name__)
    >>>
    >>> @trace("process_payment")
    >>> def process_payment(user_id: int, amount: float):
    ...     logger.info(f"Processing payment", extra={"amount": amount})
    ...     # ... lógica de pagamento ...
    ...     return {"status": "success"}
"""

from .config import TelemetryConfig
from .logging import (
    clear_log_context,
    configure_logging,
    get_log_context,
    get_logger,
    set_log_context,
)
from .tracer import (
    get_current_span,
    get_current_span_id,
    get_current_trace_id,
    get_tracer,
    init_telemetry,
    shutdown_telemetry,
    trace,
)

__version__ = "0.1.0"

__all__ = [
    # Tracer
    "init_telemetry",
    "shutdown_telemetry",
    "trace",
    "get_current_span",
    "get_tracer",
    "get_current_trace_id",
    "get_current_span_id",
    # Logging
    "get_logger",
    "configure_logging",
    "set_log_context",
    "get_log_context",
    "clear_log_context",
    # Config
    "TelemetryConfig",
]
