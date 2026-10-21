"""Chalice integration with automatic instrumentation and distributed tracing."""

from collections.abc import Callable, Iterable
from functools import wraps
import logging
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry.propagate import extract
from opentelemetry.trace import Status, StatusCode

try:
    from chalice import Chalice

    CHALICE_AVAILABLE = True
except ImportError:
    CHALICE_AVAILABLE = False
    Chalice = None

from ._excecao import SPAN_SEM_REGISTRO_AUTOMATICO, mark_span_error
from .auto_instrument import auto_instrument
from .config import TelemetryConfig
from .logging import ExceptionMessageFilter, configure_logging
from .propagation import string_attribute
from .tracer import flush_telemetry, get_current_span, get_tracer, init_telemetry

logger = logging.getLogger(__name__)

_instrumented = False


def instrument_chalice(
    app: Chalice,
    config: TelemetryConfig | None = None,
    configure_logs: bool = True,
    json_logs: bool | None = None,
    auto_instrument_libs: bool = True,
    redact_keys: Iterable[str] | None = None,
    mask_policy: dict | None = None,
):
    """
    Instrumenta aplicação Chalice com OpenTelemetry.

    Adiciona automaticamente:
    - Tracing de todas as requisições HTTP via middleware
    - Propagação de contexto distribuído (W3C Trace Context)
    - Captura de erros e exceções
    - Atributos semânticos HTTP (método, status, URL, etc.)

    Para eventos SQS, use o decorator trace_sqs_message (nu, sem parênteses) junto com @app.on_sqs_message().

    Args:
        app: Instância do Chalice.
        config: Configuração customizada. Se None, carrega de variáveis de ambiente.
        configure_logs: Se True, configura logging com correlação de traces.
        json_logs: Formato JSON dos logs, resolvido por precedência: parâmetro
            explícito True/False > OTEL_LOG_FORMAT ("json" liga JSON) > default
            do entrypoint (True aqui).
        auto_instrument_libs: Se True, auto-instrumenta bibliotecas comuns (httpx, requests, boto3, etc.)
        redact_keys: Chaves extras cujos valores são mascarados nos logs, além
            das chaves padrão de credencial.
        mask_policy: Mapa campo -> Mask estendendo DEFAULT_MASK_POLICY (o default
            universal sempre entra; o que passar aqui faz merge por cima e pode
            sobrescrever um default). Exemplo:
            >>> from otel_observability import CONTA_DIGITAL_MASK_POLICY, Mask
            >>> instrument_chalice(
            ...     app, mask_policy={**CONTA_DIGITAL_MASK_POLICY, "xpto": Mask.LAST4}
            ... )

    Raises:
        ImportError: Se chalice não estiver instalado.

    Example:
        >>> from chalice import Chalice
        >>> from otel_observability.chalice import instrument_chalice
        >>>
        >>> app = Chalice(app_name='myapp')
        >>>
        >>> # Instrumentar ANTES de definir rotas
        >>> instrument_chalice(app)
        >>>
        >>> @app.route('/users/{user_id}')
        >>> def get_user(user_id: int):
        ...     return {"user_id": user_id}

    Note:
        Requer instalação com extras Chalice:
        pip install otel-observability[chalice]
    """
    if not CHALICE_AVAILABLE:
        raise ImportError(
            "Chalice instrumentation not available. "
            "Install with: pip install otel-observability[chalice] "
            "or: pip install chalice"
        )

    global _instrumented

    if _instrumented:
        logger.warning("Chalice already instrumented. Skipping.")
        return

    cfg = config or TelemetryConfig.from_env()

    # configure_logging must run BEFORE init_telemetry: init_telemetry calls
    # init_otlp_log_export which adds the LoggingHandler to the root logger.
    # If configure_logging runs after, its handlers.clear() removes that handler
    # and logs never reach Datadog.
    if configure_logs:
        configure_logging(
            level=cfg.log_level,
            json_format=cfg.resolve_json_logs(json_logs, default=True),
            redact_keys=redact_keys,
            mask_policy=mask_policy,
        )

    # Inicializar telemetria
    init_telemetry(cfg)

    if auto_instrument_libs:
        auto_instrument()

    _proteger_log_do_app(app)

    # Registrar middleware HTTP
    @app.middleware("http")
    def otel_middleware(event, get_response):
        """Middleware para tracing de requisições HTTP."""
        tracer = get_tracer(__name__)

        # Extrair contexto de trace dos headers
        headers = event.headers or {}
        carrier = {k.lower(): v for k, v in headers.items()}

        parent_context = extract(carrier) if carrier else otel_context.get_current()
        token = otel_context.attach(parent_context)

        try:
            span_name = f"{event.method} {event.path}"
            with tracer.start_as_current_span(span_name, **SPAN_SEM_REGISTRO_AUTOMATICO) as span:
                # Adicionar atributos HTTP
                span.set_attribute("http.method", event.method)
                span.set_attribute("http.route", event.path)
                span.set_attribute("http.target", event.path)

                if headers:
                    user_agent = headers.get("user-agent") or headers.get("User-Agent")
                    if user_agent:
                        span.set_attribute("http.user_agent", user_agent)

                # Verificar se é health check
                if event.path in ["/health", "/healthz", "/readiness", "/liveness"]:
                    span.set_attribute("request.is_health_check", True)

                try:
                    response = get_response(event)
                    # Adicionar status code se disponível
                    if hasattr(response, "status_code"):
                        span.set_attribute("http.status_code", response.status_code)
                    elif isinstance(response, dict) and "statusCode" in response:
                        span.set_attribute("http.status_code", response["statusCode"])

                    _fechar_status(span, response)
                    return response
                except Exception as e:
                    mark_span_error(span, e)
                    logger.exception("Chalice HTTP request error", exc_info=e)
                    raise
        finally:
            otel_context.detach(token)
            flush_telemetry(timeout=5)

    _instrumented = True
    logger.info(
        f"Chalice app instrumented: service={cfg.service_name}, "
        f"env={cfg.environment}, app_name={app.app_name}"
    )


class _ErroDoAppFilter(ExceptionMessageFilter):
    """Handler de `app.log`: o Chalice captura a exceção da view e a loga ali.

    O `except` do middleware nunca roda nesse caminho, então é aqui que o span
    ganha o erro, e o handler (sem propagar ao root) perde a mensagem.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ja_tratado = getattr(record, "_otel_exc_sanitized", False)
        if record.exc_info and record.exc_info[1] is not None and not ja_tratado:
            mark_span_error(get_current_span(), record.exc_info[1])
        return super().filter(record)


def _proteger_log_do_app(app: Any) -> None:
    log = getattr(app, "log", None)
    if not isinstance(log, logging.Logger):
        return
    for handler in log.handlers:
        if not any(isinstance(f, _ErroDoAppFilter) for f in handler.filters):
            handler.addFilter(_ErroDoAppFilter())


def _fechar_status(span: Any, response: Any) -> None:
    codigo = getattr(response, "status_code", None)
    if isinstance(response, dict):
        codigo = response.get("statusCode", codigo)
    if isinstance(codigo, int) and codigo >= 500:
        if span.status.status_code is not StatusCode.ERROR:
            span.set_status(Status(StatusCode.ERROR))
        return
    span.set_status(Status(StatusCode.OK))


def trace_sqs_message(func: Callable) -> Callable:
    """
    Decorator para tracing de mensagens SQS no Chalice.

    Use junto com @app.on_sqs_message() para instrumentar handlers de mensagens SQS.

    Args:
        func: Função handler de mensagem SQS.

    Returns:
        Função wrapper com instrumentação de tracing.

    Example:
        >>> from chalice import Chalice
        >>> from otel_observability.chalice import trace_sqs_message
        >>>
        >>> app = Chalice(app_name='myapp')
        >>>
        >>> @app.on_sqs_message(queue_name='my-queue')
        >>> @trace_sqs_message
        >>> def process_message(event):
        ...     # event contém a mensagem SQS
        ...     message_id = event.get('messageId')
        ...     body = event.get('body', '')
        ...     return {"status": "processed"}

    Note:
        O decorator deve ser usado DEPOIS de @app.on_sqs_message() (decorators
        são aplicados de baixo para cima).
    """
    if not CHALICE_AVAILABLE:
        raise ImportError(
            "Chalice not available. Install with: pip install otel-observability[chalice]"
        )

    @wraps(func)
    def wrapper(event: dict) -> Any:
        tracer = get_tracer(__name__)

        # Extrair contexto de trace de messageAttributes
        carrier = _extract_sqs_carrier(event)
        parent_context = extract(carrier) if carrier else otel_context.get_current()
        token = otel_context.attach(parent_context)

        try:
            span_name = "sqs.process"
            with tracer.start_as_current_span(span_name, **SPAN_SEM_REGISTRO_AUTOMATICO) as span:
                # Adicionar atributos SQS
                span.set_attribute("messaging.system", "aws_sqs")
                span.set_attribute("messaging.operation", "process")

                if "messageId" in event:
                    span.set_attribute("messaging.message.id", event["messageId"])

                # Extrair nome da fila de eventSourceARN se disponível
                if "eventSourceARN" in event:
                    queue_arn = event["eventSourceARN"]
                    queue_name = queue_arn.split(":")[-1]
                    span.set_attribute("messaging.destination.name", queue_name)

                # Adicionar atributos de mensagem se disponíveis
                if "messageAttributes" in event:
                    attrs = event["messageAttributes"]
                    if attrs:
                        span.set_attribute("messaging.message.attributes_count", len(attrs))

                try:
                    result = func(event)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    mark_span_error(span, e)
                    logger.exception("SQS message processing error", exc_info=e)
                    raise
        finally:
            otel_context.detach(token)
            flush_telemetry(timeout=5)

    return wrapper


def _extract_sqs_carrier(event: dict) -> dict:
    """
    Extrai trace context de mensagem SQS do Chalice.

    Args:
        event: Evento SQS do Chalice (mensagem individual).

    Returns:
        Dicionário com trace context (traceparent, tracestate).
    """
    carrier = {}

    attrs = event.get("messageAttributes")
    if isinstance(attrs, dict):
        for chave in ("traceparent", "tracestate"):
            bruto = attrs.get(chave)
            valor = (
                bruto if isinstance(bruto, str) else string_attribute(bruto, "stringValue", "Value")
            )
            if valor:
                carrier[chave] = valor
        if carrier:
            logger.debug(f"Extracted context from SQS message: {list(carrier.keys())}")

    if not carrier:
        logger.debug("No trace context found in SQS message - starting new trace")

    return carrier
