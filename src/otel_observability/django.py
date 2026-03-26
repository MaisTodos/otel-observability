"""Django integration with automatic instrumentation and distributed tracing."""

import asyncio
import logging
import time

try:
    from opentelemetry.instrumentation.django import DjangoInstrumentor

    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    DjangoInstrumentor = None

from .auto_instrument import auto_instrument
from .config import TelemetryConfig
from .logging import clear_log_context, configure_logging
from .tracer import init_telemetry

logger = logging.getLogger(__name__)


def instrument_django(
    config: TelemetryConfig | None = None,
    configure_logs: bool = True,
    json_logs: bool = False,
    excluded_urls: str | None = None,
    auto_instrument_libs: bool = True,
) -> None:
    """
    Instrumenta uma aplicação Django com OpenTelemetry.

    Deve ser chamado no AppConfig.ready() ou no ponto de entrada WSGI/ASGI,
    ANTES de qualquer request ser processado.

    Adiciona automaticamente:
    - Tracing de todas as requisições HTTP
    - Propagação de contexto distribuído (W3C Trace Context)
    - Captura de erros e exceções
    - Atributos semânticos HTTP (método, status, URL, etc.)

    Args:
        config: Configuração customizada. Se None, carrega de variáveis de ambiente.
        configure_logs: Se True, configura logging com correlação de traces.
        json_logs: Se True, usa formato JSON para logs (recomendado em produção).
        excluded_urls: Regex de URLs para excluir do tracing (ex: "/health,/metrics").
        auto_instrument_libs: Se True, auto-instrumenta bibliotecas comuns (httpx, requests, etc.)

    Raises:
        ImportError: Se opentelemetry-instrumentation-django não estiver instalado.

    Example (AppConfig):
        >>> # myapp/apps.py
        >>> from django.apps import AppConfig
        >>>
        >>> class MyAppConfig(AppConfig):
        ...     def ready(self):
        ...         from otel_observability.django import instrument_django
        ...         instrument_django()

    Example (wsgi.py):
        >>> from otel_observability.django import instrument_django
        >>> instrument_django(json_logs=True)
        >>>
        >>> from django.core.wsgi import get_wsgi_application
        >>> application = get_wsgi_application()

    Note:
        Requer instalação com extras Django:
        pip install otel-observability[django]
        ou: pip install opentelemetry-instrumentation-django
    """
    if not DJANGO_AVAILABLE:
        raise ImportError(
            "Django instrumentation not available. "
            "Install with: pip install otel-observability[django] "
            "or: pip install opentelemetry-instrumentation-django"
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

    DjangoInstrumentor().instrument(
        request_hook=_request_hook,
        response_hook=_response_hook,
        excluded_urls=excluded_urls,
    )

    logger.info(
        f"Django instrumented: service={cfg.service_name}, "
        f"env={cfg.environment}, excluded_urls={excluded_urls}"
    )


def _request_hook(span, request):
    """Hook chamado no início de cada requisição HTTP."""
    user_agent = request.META.get("HTTP_USER_AGENT")
    if user_agent:
        span.set_attribute("http.user_agent", user_agent)

    if request.path in ["/health", "/healthz", "/readiness", "/liveness"]:
        span.set_attribute("request.is_health_check", True)

    tenant_id = request.META.get("HTTP_X_TENANT_ID")
    if tenant_id:
        span.set_attribute("tenant.id", tenant_id)


def _response_hook(span, request, response):
    """Hook chamado ao final de cada requisição HTTP."""


def add_span_attribute(key: str, value):
    """
    Adiciona um atributo ao span atual.

    Útil para adicionar informações de negócio ao trace.

    Args:
        key: Nome do atributo.
        value: Valor do atributo.

    Example:
        >>> from otel_observability.django import add_span_attribute
        >>>
        >>> def get_user(request, user_id):
        ...     add_span_attribute("user.id", user_id)
        ...     add_span_attribute("user.premium", True)
        ...     return JsonResponse({"user_id": user_id})
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
        >>> from otel_observability.django import add_span_event
        >>>
        >>> def process_payment(request):
        ...     add_span_event("payment.validation_started")
        ...     # ... validar ...
        ...     add_span_event("payment.processing", {"amount": 100.0})
        ...     return JsonResponse({"status": "success"})
    """
    from opentelemetry import trace

    span = trace.get_current_span()
    span.add_event(name, attributes=attributes or {})


class DjangoRequestLoggingMiddleware:
    """
    Middleware de logging de requests para Django.

    Suporta views síncronas (WSGI) e assíncronas (ASGI, Django 4.1+).

    Responsabilidades:
    - Medir duração da request
    - Logar 'request.completed' com method, path, status_code, duration_ms
    - Garantir clear_log_context() no finally (evita vazamento de contexto OTel
      entre requests no mesmo worker)

    Uso típico: adicione ao MIDDLEWARE em settings.py ANTES de outros middlewares:

        MIDDLEWARE = [
            'otel_observability.django.DjangoRequestLoggingMiddleware',
            ...
        ]

    Para customizar contexto de log por request, subclasse este middleware:

        class RequestContextMiddleware(DjangoRequestLoggingMiddleware):
            def _sync_call(self, request):
                set_log_context(user_id=request.headers.get("x-user-id", ""))
                return super()._sync_call(request)

    Args:
        get_response: O próximo middleware ou view callable.
        logger: Logger a ser usado. Se None, usa o logger do módulo.
        skip_log_paths: Conjunto de paths que não geram log. Default: {"/ping"}.
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response, logger=None, skip_log_paths: set[str] | None = None):
        if asyncio.iscoroutinefunction(get_response):
            self._is_coroutine = asyncio.coroutines._is_coroutine
        self.get_response = get_response
        self._logger = logger or logging.getLogger(__name__)
        self._skip_log_paths = skip_log_paths or {"/ping"}

    def __call__(self, request):
        if asyncio.iscoroutinefunction(self.get_response):
            return self._acall(request)
        return self._sync_call(request)

    def _sync_call(self, request):
        start = time.monotonic()
        try:
            response = self.get_response(request)
            duration_ms = round((time.monotonic() - start) * 1000)
            if request.path not in self._skip_log_paths:
                self._logger.info(
                    "request.completed",
                    extra={
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                )
            return response
        finally:
            clear_log_context()

    async def _acall(self, request):
        start = time.monotonic()
        try:
            response = await self.get_response(request)
            duration_ms = round((time.monotonic() - start) * 1000)
            if request.path not in self._skip_log_paths:
                self._logger.info(
                    "request.completed",
                    extra={
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                )
            return response
        finally:
            clear_log_context()
