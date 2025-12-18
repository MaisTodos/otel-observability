"""AWS Lambda integration with distributed tracing."""

from collections.abc import Callable
from functools import wraps
import logging
import os
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry.propagate import extract
from opentelemetry.trace import Status, StatusCode

from .auto_instrument import auto_instrument
from .config import TelemetryConfig
from .logging import configure_logging
from .tracer import get_tracer, init_telemetry, shutdown_telemetry

logger = logging.getLogger(__name__)

_instrumented = False


def instrument_lambda_handler(
    config: TelemetryConfig | None = None,
    configure_logs: bool = True,
    json_logs: bool = True,
    auto_extract_context: bool = True,
    auto_instrument_libs: bool = True,
):
    """
    Decorator para instrumentar AWS Lambda handler com tracing distribuído.

    **Nota importante**: Este decorator é destinado a funções Lambda "puras"
    (sem frameworks como Chalice). Para aplicações Chalice, use
    `otel_observability.chalice.instrument_chalice()`.

    Args:
        config: Configuração customizada. Se None, carrega de variáveis de ambiente.
        configure_logs: Se True, configura logging com correlação de traces.
        json_logs: Se True, usa formato JSON para logs.
        auto_extract_context: Se True, extrai automaticamente trace context de eventos
                             SQS/SNS/EventBridge/API Gateway para tracing distribuído.
        auto_instrument_libs: Se True, auto-instrumenta bibliotecas comuns (boto3, httpx, etc.)

    Example:
        >>> from otel_observability.aws_lambda import instrument_lambda_handler
        >>>
        >>> @instrument_lambda_handler()
        >>> def lambda_handler(event, context):
        ...     logger.info("Processing request")
        ...     return {"statusCode": 200, "body": "OK"}

    Note:
        Para aplicações Chalice, use:
        >>> from otel_observability.chalice import instrument_chalice
        >>> instrument_chalice(app)
    """

    def decorator(handler: Callable) -> Callable:
        global _instrumented

        # Inicialização única (cold start)
        if not _instrumented:
            # Inicializar telemetria
            cfg = config or TelemetryConfig.from_env()
            init_telemetry(cfg)

            if configure_logs:
                configure_logging(level=cfg.log_level, json_format=json_logs)

            if auto_instrument_libs:
                auto_instrument()

            logger.info(f"Lambda handler instrumented: {handler.__name__}")
            _instrumented = True

        @wraps(handler)
        def wrapper(event: dict, lambda_context: Any) -> Any:
            tracer = get_tracer(__name__)

            carrier = {}
            if auto_extract_context:
                carrier = _extract_carrier_from_event(event)

            parent_context = extract(carrier) if carrier else otel_context.get_current()
            span_name = (
                f"lambda.{lambda_context.function_name}" if lambda_context else "lambda.handler"
            )
            token = otel_context.attach(parent_context)

            try:
                with tracer.start_as_current_span(span_name) as span:
                    if lambda_context:
                        span.set_attributes(
                            {
                                "faas.trigger": _get_event_source(event),
                                "faas.execution": lambda_context.aws_request_id,
                                "faas.name": lambda_context.function_name,
                                "faas.version": lambda_context.function_version,
                                "faas.max_memory": lambda_context.memory_limit_in_mb,
                                "cloud.provider": "aws",
                                "cloud.platform": "aws_lambda",
                                "cloud.region": os.getenv("AWS_REGION", "unknown"),
                            }
                        )

                    _add_event_attributes(span, event)

                    try:
                        result = handler(event, lambda_context)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        logger.exception("Lambda handler error", exc_info=e)
                        raise
            finally:
                otel_context.detach(token)
                shutdown_telemetry(timeout=5)

        return wrapper

    return decorator


def _extract_carrier_from_event(event: dict) -> dict:
    """Extrai trace context de diferentes tipos de eventos Lambda."""
    carrier = {}

    if "headers" in event:
        headers = event["headers"] or {}
        carrier = {k.lower(): v for k, v in headers.items()}
        logger.debug(f"Extracted context from HTTP headers: {list(carrier.keys())}")

    elif event.get("Records"):
        first_record = event["Records"][0]

        if first_record.get("eventSource") == "aws:sqs":
            if "messageAttributes" in first_record:
                attrs = first_record["messageAttributes"]
                if "traceparent" in attrs:
                    carrier["traceparent"] = attrs["traceparent"]["stringValue"]
                if "tracestate" in attrs:
                    carrier["tracestate"] = attrs["tracestate"]["stringValue"]
                logger.debug(f"Extracted context from SQS: {list(carrier.keys())}")

        elif first_record.get("eventSource") == "aws:sns":  # noqa: SIM102
            if "Sns" in first_record and "MessageAttributes" in first_record["Sns"]:
                attrs = first_record["Sns"]["MessageAttributes"]
                if "traceparent" in attrs:
                    carrier["traceparent"] = attrs["traceparent"]["Value"]
                if "tracestate" in attrs:
                    carrier["tracestate"] = attrs["tracestate"]["Value"]
                logger.debug(f"Extracted context from SNS: {list(carrier.keys())}")

    elif "detail-type" in event and "detail" in event:
        detail = event.get("detail", {})
        if "traceparent" in detail:
            carrier["traceparent"] = detail["traceparent"]
        if "tracestate" in detail:
            carrier["tracestate"] = detail["tracestate"]
        logger.debug(f"Extracted context from EventBridge: {list(carrier.keys())}")

    if not carrier:
        logger.debug("No trace context found in Lambda event - starting new trace")

    return carrier


def _get_event_source(event: dict) -> str:
    """Identifica a fonte do evento Lambda."""
    if "httpMethod" in event or "requestContext" in event:
        return "http"
    if event.get("Records"):
        source = event["Records"][0].get("eventSource", "")
        if "sqs" in source:
            return "sqs"
        if "sns" in source:
            return "sns"
        if "s3" in source:
            return "s3"
        if "dynamodb" in source:
            return "dynamodb"
    elif "detail-type" in event:
        return "eventbridge"
    return "other"


def _add_event_attributes(span, event: dict):
    """Adiciona atributos semânticos específicos do tipo de evento."""

    if "httpMethod" in event or "requestContext" in event:
        span.set_attribute("http.method", event.get("httpMethod", "GET"))
        span.set_attribute("http.route", event.get("resource", ""))
        span.set_attribute("http.target", event.get("path", ""))

        if "requestContext" in event:
            req_ctx = event["requestContext"]
            span.set_attribute("http.request_id", req_ctx.get("requestId", ""))

            if "domainName" in req_ctx:
                span.set_attribute("http.host", req_ctx["domainName"])
                span.set_attribute("http.scheme", "https")

            if event.get("headers"):
                user_agent = event["headers"].get("user-agent") or event["headers"].get(
                    "User-Agent"
                )
                if user_agent:
                    span.set_attribute("http.user_agent", user_agent)

    elif event.get("Records"):
        first_record = event["Records"][0]
        event_source = first_record.get("eventSource", "")

        if event_source == "aws:sqs":
            span.set_attribute("messaging.system", "aws_sqs")
            span.set_attribute("messaging.operation", "process")
            span.set_attribute("messaging.batch.message_count", len(event["Records"]))
            span.set_attribute("messaging.message.id", first_record.get("messageId", ""))

            if "eventSourceARN" in first_record:
                queue_arn = first_record["eventSourceARN"]
                queue_name = queue_arn.split(":")[-1]
                span.set_attribute("messaging.destination.name", queue_name)

        elif event_source == "aws:sns":
            span.set_attribute("messaging.system", "aws_sns")
            span.set_attribute("messaging.operation", "process")
            span.set_attribute("messaging.batch.message_count", len(event["Records"]))

            if "Sns" in first_record:
                sns = first_record["Sns"]
                span.set_attribute("messaging.message.id", sns.get("MessageId", ""))

                if "TopicArn" in sns:
                    topic_arn = sns["TopicArn"]
                    topic_name = topic_arn.split(":")[-1]
                    span.set_attribute("messaging.destination.name", topic_name)

        elif event_source == "aws:dynamodb":
            span.set_attribute("db.system", "dynamodb")
            span.set_attribute("db.operation", first_record.get("eventName", ""))
            span.set_attribute("messaging.batch.message_count", len(event["Records"]))

            if "eventSourceARN" in first_record:
                table_arn = first_record["eventSourceARN"]
                table_name = table_arn.split("/")[1] if "/" in table_arn else "unknown"
                span.set_attribute("db.name", table_name)

        elif event_source == "aws:s3":
            span.set_attribute("cloud.service", "s3")
            if "s3" in first_record:
                s3 = first_record["s3"]
                if "bucket" in s3:
                    span.set_attribute("aws.s3.bucket", s3["bucket"].get("name", ""))
                if "object" in s3:
                    span.set_attribute("aws.s3.key", s3["object"].get("key", ""))
    elif "detail-type" in event:
        span.set_attribute("messaging.system", "aws_eventbridge")
        span.set_attribute("messaging.operation", "process")
        span.set_attribute("messaging.message.event_type", event.get("detail-type", ""))
        span.set_attribute("cloud.event.source", event.get("source", ""))

        if event.get("resources"):
            span.set_attribute("cloud.event.resource", event["resources"][0])
