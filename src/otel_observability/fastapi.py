"""FastAPI integration with automatic instrumentation and distributed tracing."""

from collections.abc import Iterable
import logging
import time

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.util.http import parse_excluded_urls
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPIInstrumentor = None
    BaseHTTPMiddleware = object
    Request = None
    parse_excluded_urls = None

from .auto_instrument import auto_instrument
from .config import TelemetryConfig
from .logging import clear_log_context, configure_logging
from .tracer import init_telemetry

logger = logging.getLogger(__name__)


class _AccessLogPathFilter(logging.Filter):
    """Descarta logs do uvicorn.access cujos paths estão em excluded_urls.

    Usa o mesmo parser do FastAPIInstrumentor (parse_excluded_urls), então o
    access log e o tracing concordam sobre o que é rota excluída. Casa contra o
    path da requisição (record.args[2] do uvicorn.access), nunca contra a linha
    formatada — user-agent e query string não influenciam a decisão.
    """

    _PATH_ARG_INDEX = 2

    def __init__(self, excluded_urls: str) -> None:
        super().__init__()
        self._exclude_list = parse_excluded_urls(excluded_urls)

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) <= self._PATH_ARG_INDEX:
            # Formato inesperado: deixa passar. Filtro de log falha aberto.
            return True

        path = args[self._PATH_ARG_INDEX]
        if not isinstance(path, str):
            return True

        return not self._exclude_list.url_disabled(path)


def instrument_fastapi(
    app,
    config: TelemetryConfig | None = None,
    configure_logs: bool = True,
    json_logs: bool | None = None,
    excluded_urls: str | None = None,
    auto_instrument_libs: bool = True,
    redact_keys: Iterable[str] | None = None,
    mask_policy: dict | None = None,
    suppress_access_logs: bool = True,
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
        json_logs: Formato JSON dos logs, resolvido por precedência: parâmetro
            explícito True/False > OTEL_LOG_FORMAT ("json" liga JSON) > default
            do entrypoint (False aqui).
        excluded_urls: Regex de URLs para excluir do tracing (ex: "/health,/metrics").
        mask_policy: Mapa campo -> Mask estendendo DEFAULT_MASK_POLICY (o default
            universal sempre entra; o que passar aqui faz merge por cima e pode
            sobrescrever um default). Exemplo:
            >>> from otel_observability import CONTA_DIGITAL_MASK_POLICY, Mask
            >>> instrument_fastapi(
            ...     app, mask_policy={**CONTA_DIGITAL_MASK_POLICY, "xpto": Mask.LAST4}
            ... )

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
        json_format = cfg.resolve_json_logs(json_logs, default=False)
        configure_logging(
            level=cfg.log_level,
            json_format=json_format,
            redact_keys=redact_keys,
            mask_policy=mask_policy,
        )

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

    if excluded_urls and suppress_access_logs:
        logging.getLogger("uvicorn.access").addFilter(_AccessLogPathFilter(excluded_urls))

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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware genérico de logging de requests para FastAPI/App Runner.

    Responsabilidades:
    - Medir duração da request
    - Logar 'request.completed' com method, path, status_code, duration_ms
    - Garantir clear_log_context() no finally (evita vazamento de contexto OTEL
      entre requests no mesmo worker)

    Uso típico: subclasse este middleware em cada app para adicionar
    set_log_context() com os headers de negócio específicos do serviço.

    Args:
        app: Instância ASGI.
        logger: Qualquer objeto com método .info(). Tipicamente o ILogger do app.
        skip_log_paths: Conjunto de paths que não geram log. Default: {"/ping"}.

    Example:
        >>> from otel_observability.fastapi import RequestLoggingMiddleware
        >>> from otel_observability import set_log_context
        >>>
        >>> class RequestContextMiddleware(RequestLoggingMiddleware):
        ...     def __init__(self, app):
        ...         super().__init__(app, logger=my_logger, skip_log_paths={"/ping"})
        ...
        ...     async def dispatch(self, request, call_next):
        ...         set_log_context(user_id=request.headers.get("user_id", ""))
        ...         return await super().dispatch(request, call_next)
    """

    def __init__(self, app, logger, skip_log_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self._logger = logger
        self._skip_log_paths = skip_log_paths or {"/ping"}

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start) * 1000)
            if request.url.path not in self._skip_log_paths:
                self._logger.info(
                    "request.completed",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                )
            return response
        finally:
            clear_log_context()
