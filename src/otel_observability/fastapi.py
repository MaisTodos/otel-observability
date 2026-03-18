"""FastAPI integration with automatic instrumentation and distributed tracing."""

import logging

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPIInstrumentor = None

from .auto_instrument import auto_instrument
from .config import TelemetryConfig
from .logging import configure_logging
from .tracer import init_telemetry

logger = logging.getLogger(__name__)


def instrument_fastapi(
    app,
    config: TelemetryConfig | None = None,
    configure_logs: bool = True,
    json_logs: bool = False,
    excluded_urls: str | None = None,
    auto_instrument_libs: bool = True,
):
    """
    Instrumenta uma aplicação FastAPI com OpenTelemetry.

    Adiciona automaticamente:
    - Tracing de todas as requisições HTTP
    - Propagação de contexto distribuído (W3C Trace Context)
    - Captura de erros e exceções
    - Atributos semânticos HTTP (método, status, URL, etc.)

    Args:
        app: Instância do FastAPI.
        config: Configuração customizada. Se None, carrega de variáveis de ambiente.
        configure_logs: Se True, configura logging com correlação de traces.
        json_logs: Se True, usa formato JSON para logs (recomendado em produção).
        excluded_urls: Regex de URLs para excluir do tracing (ex: "/health,/metrics").

    Raises:
        ImportError: Se opentelemetry-instrumentation-fastapi não estiver instalado.

    Example:
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

    Example (com exclusões):
        >>> instrument_fastapi(
        ...     app,
        ...     excluded_urls="/health|/metrics|/docs"
        ... )

    Note:
        Requer instalação com extras FastAPI:
        pip install otel-observability[fastapi]

    Args:
        auto_instrument_libs: Se True, auto-instrumenta bibliotecas comuns (httpx, requests, sqlalchemy, etc.)
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI instrumentation not available. "
            "Install with: pip install otel-observability[fastapi] "
            "or: pip install opentelemetry-instrumentation-fastapi"
        )

    cfg = config or TelemetryConfig.from_env()

    # configure_logging must run BEFORE init_telemetry: init_telemetry calls
    # init_otlp_log_export which adds the LoggingHandler to the root logger.
    # If configure_logging runs after, its handlers.clear() removes that handler
    # and logs never reach Datadog.
    if configure_logs:
        configure_logging(level=cfg.log_level, json_format=json_logs)

    init_telemetry(cfg)

    if auto_instrument_libs:
        auto_instrument()

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=None,
        excluded_urls=excluded_urls,
        server_request_hook=_server_request_hook,
        client_request_hook=None,
        client_response_hook=None,
    )

    logger.info(
        f"FastAPI instrumented: service={cfg.service_name}, "
        f"env={cfg.environment}, excluded_urls={excluded_urls}"
    )


def _server_request_hook(span, scope: dict):
    """Hook chamado no início de cada requisição HTTP."""
    headers = dict(scope.get("headers", []))

    if b"user-agent" in headers:
        user_agent = headers[b"user-agent"].decode("utf-8", errors="ignore")
        span.set_attribute("http.user_agent", user_agent)

    path = scope.get("path", "")
    if path in ["/health", "/healthz", "/readiness", "/liveness"]:
        span.set_attribute("request.is_health_check", True)

    if b"x-tenant-id" in headers:
        tenant_id = headers[b"x-tenant-id"].decode("utf-8", errors="ignore")
        span.set_attribute("tenant.id", tenant_id)


def add_span_attribute(key: str, value):
    """
    Adiciona um atributo ao span atual.

    Útil para adicionar informações de negócio ao trace.

    Args:
        key: Nome do atributo.
        value: Valor do atributo.

    Example:
        >>> from otel_observability.fastapi import add_span_attribute
        >>>
        >>> @app.get("/users/{user_id}")
        >>> async def get_user(user_id: int):
        ...     add_span_attribute("user.id", user_id)
        ...     add_span_attribute("user.premium", True)
        ...     return {"user_id": user_id}
    """
    from opentelemetry import trace

    span = trace.get_current_span()
    span.set_attribute(key, value)


def add_span_event(name: str, attributes: dict | None = None):
    """
    Adiciona um evento ao span atual.

    Eventos são pontos no tempo dentro de um span, úteis para marcar
    operações importantes ou debug.

    Args:
        name: Nome do evento.
        attributes: Atributos opcionais do evento.

    Example:
        >>> from otel_observability.fastapi import add_span_event
        >>>
        >>> @app.post("/payment")
        >>> async def process_payment(amount: float):
        ...     add_span_event("payment.validation_started")
        ...     # ... validar ...
        ...     add_span_event("payment.processing", {"amount": amount})
        ...     # ... processar ...
        ...     add_span_event("payment.completed")
        ...     return {"status": "success"}
    """
    from opentelemetry import trace

    span = trace.get_current_span()
    span.add_event(name, attributes=attributes or {})
