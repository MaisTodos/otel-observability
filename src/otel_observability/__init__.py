"""
OpenTelemetry Observability Library
====================================

Biblioteca simplificada de OpenTelemetry para FastAPI, AWS Lambda e Chalice com:
- Tracing distribuído (W3C Trace Context + AWS X-Ray)
- Logging estruturado com correlação de traces
- Auto-instrumentação
- Integração com Datadog

Example (FastAPI):
    >>> from fastapi import FastAPI
    >>> from otel_observability import instrument_fastapi, get_logger, trace
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
    >>> from otel_observability import instrument_lambda_handler, get_logger, trace
    >>>
    >>> logger = get_logger(__name__)
    >>>
    >>> @instrument_lambda_handler()
    >>> def lambda_handler(event, context):
    ...     logger.info("Processing request")
    ...     return {"statusCode": 200, "body": "OK"}

Example (Chalice):
    >>> from chalice import Chalice
    >>> from otel_observability import instrument_chalice, trace_sqs_message, get_logger, trace
    >>>
    >>> app = Chalice(app_name='myapp')
    >>> instrument_chalice(app)
    >>>
    >>> @app.route('/users/{user_id}')
    >>> def get_user(user_id: int):
    ...     return {"user_id": user_id}
    >>>
    >>> @app.on_sqs_message(queue_name='my-queue')
    >>> @trace_sqs_message()
    >>> def process_message(event):
    ...     return {"status": "processed"}

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

# AWS Lambda integration (module always exists, no optional deps)
from .aws_lambda import instrument_lambda_handler
from .config import TelemetryConfig

# FastAPI integration (module always exists, but may raise ImportError if deps missing)
from .fastapi import RequestLoggingMiddleware, instrument_fastapi
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

# Chalice integration (optional - module may not be importable)
try:
    from .chalice import instrument_chalice, trace_sqs_message

    CHALICE_AVAILABLE = True
except ImportError:
    CHALICE_AVAILABLE = False
    instrument_chalice = None
    trace_sqs_message = None

# Metrics integration (optional - requires datadog package)
try:
    from .metrics import (
        flush,
        increment_counter,
        record_distribution,
        record_histogram,
        set_gauge,
        track_funnel_step,
    )

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    increment_counter = None
    set_gauge = None
    record_histogram = None
    record_distribution = None
    track_funnel_step = None
    flush = None

__version__ = "0.1.0"

__all__ = [
    "RequestLoggingMiddleware",
    "TelemetryConfig",
    "clear_log_context",
    "configure_logging",
    "get_current_span",
    "get_current_span_id",
    "get_current_trace_id",
    "get_log_context",
    "get_logger",
    "get_tracer",
    "init_telemetry",
    "instrument_fastapi",
    "instrument_lambda_handler",
    "set_log_context",
    "shutdown_telemetry",
    "trace",
]

# Add Chalice exports if available
if CHALICE_AVAILABLE:
    __all__.extend(["instrument_chalice", "trace_sqs_message"])

# Add Metrics exports if available
if METRICS_AVAILABLE:
    __all__.extend(
        [
            "flush",
            "increment_counter",
            "record_distribution",
            "record_histogram",
            "set_gauge",
            "track_funnel_step",
        ]
    )
