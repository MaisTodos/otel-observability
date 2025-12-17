"""Helpers para propagação de trace context."""

from typing import Any

from opentelemetry import context
from opentelemetry.propagate import extract, inject

# ============================================================================
# Injeção de Trace Context (Producer/Sender)
# ============================================================================


def inject_context_into_http_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    """
    Injeta trace context em headers HTTP.

    Útil para chamadas HTTP manuais (sem auto-instrumentação).

    Args:
        headers: Headers existentes (opcional). Novo dict é criado se None.

    Returns:
        Dict com headers incluindo traceparent, tracestate, etc.

    Example:
        >>> import httpx
        >>> from otel_observability.propagation import inject_context_into_http_headers
        >>>
        >>> headers = inject_context_into_http_headers()
        >>> response = httpx.get("https://api.example.com", headers=headers)
    """
    carrier = headers or {}
    inject(carrier)
    return carrier


def inject_context_into_sqs_message_attributes() -> dict[str, dict[str, str]]:
    """
    Injeta trace context em SQS messageAttributes.

    Returns:
        Dict no formato SQS MessageAttributes.

    Example:
        >>> import boto3
        >>> from otel_observability.propagation import inject_context_into_sqs_message_attributes
        >>>
        >>> sqs = boto3.client('sqs')
        >>>
        >>> sqs.send_message(
        ...     QueueUrl='https://sqs.us-east-1.amazonaws.com/123/my-queue',
        ...     MessageBody=json.dumps({'order_id': 123}),
        ...     MessageAttributes=inject_context_into_sqs_message_attributes()
        ... )
    """
    carrier = {}
    inject(carrier)

    # Converter para formato SQS
    message_attributes = {}

    if "traceparent" in carrier:
        message_attributes["traceparent"] = {
            "StringValue": carrier["traceparent"],
            "DataType": "String",
        }

    if carrier.get("tracestate"):
        message_attributes["tracestate"] = {
            "StringValue": carrier["tracestate"],
            "DataType": "String",
        }

    return message_attributes


def inject_context_into_sns_message_attributes() -> dict[str, dict[str, str]]:
    """
    Injeta trace context em SNS MessageAttributes.

    Returns:
        Dict no formato SNS MessageAttributes.

    Example:
        >>> import boto3
        >>> from otel_observability.propagation import inject_context_into_sns_message_attributes
        >>>
        >>> sns = boto3.client('sns')
        >>>
        >>> sns.publish(
        ...     TopicArn='arn:aws:sns:us-east-1:123/my-topic',
        ...     Message=json.dumps({'event': 'order.created'}),
        ...     MessageAttributes=inject_context_into_sns_message_attributes()
        ... )
    """
    # SNS usa mesmo formato que SQS
    return inject_context_into_sqs_message_attributes()


def inject_context_into_eventbridge_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """
    Injeta trace context no campo detail do EventBridge.

    Args:
        detail: Conteúdo do evento.

    Returns:
        Dict com detail + trace context.

    Example:
        >>> import boto3
        >>> from otel_observability.propagation import inject_context_into_eventbridge_detail
        >>>
        >>> events = boto3.client('events')
        >>>
        >>> detail = inject_context_into_eventbridge_detail({
        ...     'order_id': 123,
        ...     'status': 'created'
        ... })
        >>>
        >>> events.put_events(
        ...     Entries=[{
        ...         'Source': 'my.app',
        ...         'DetailType': 'order.created',
        ...         'Detail': json.dumps(detail)
        ...     }]
        ... )
    """
    carrier = {}
    inject(carrier)

    # Adicionar trace context ao detail
    detail_with_context = detail.copy()
    detail_with_context["_trace_context"] = carrier

    # Também adicionar no nível raiz para facilitar extração
    if "traceparent" in carrier:
        detail_with_context["traceparent"] = carrier["traceparent"]
    if carrier.get("tracestate"):
        detail_with_context["tracestate"] = carrier["tracestate"]

    return detail_with_context


def inject_context_into_lambda_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Injeta trace context em payload de invocação Lambda.

    Args:
        payload: Payload da Lambda.

    Returns:
        Dict com payload + trace context.

    Example:
        >>> import boto3
        >>> from otel_observability.propagation import inject_context_into_lambda_payload
        >>>
        >>> lambda_client = boto3.client('lambda')
        >>>
        >>> payload = inject_context_into_lambda_payload({
        ...     'order_id': 123,
        ...     'action': 'process'
        ... })
        >>>
        >>> lambda_client.invoke(
        ...     FunctionName='my-lambda',
        ...     InvocationType='Event',
        ...     Payload=json.dumps(payload)
        ... )
    """
    carrier = {}
    inject(carrier)

    payload_with_context = payload.copy()
    payload_with_context["_trace_context"] = carrier

    return payload_with_context


# ============================================================================
# Extração de Trace Context (Consumer/Receiver)
# ============================================================================


def extract_context_from_http_headers(headers: dict[str, str]):
    """
    Extrai trace context de headers HTTP.

    Args:
        headers: Headers HTTP.

    Returns:
        OpenTelemetry Context.

    Example:
        >>> from flask import request
        >>> from otel_observability.propagation import extract_context_from_http_headers
        >>> from opentelemetry import context as otel_context
        >>>
        >>> # Em um handler Flask/Django
        >>> parent_context = extract_context_from_http_headers(dict(request.headers))
        >>> token = otel_context.attach(parent_context)
        >>> try:
        ...     # Processar requisição
        ...     pass
        ... finally:
        ...     otel_context.detach(token)
    """
    # Normalizar headers para lowercase
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    return extract(normalized_headers)


def extract_context_from_sqs_message(message: dict[str, Any]):
    """
    Extrai trace context de mensagem SQS.

    Args:
        message: Mensagem SQS (um Record do evento).

    Returns:
        OpenTelemetry Context.

    Example:
        >>> from otel_observability.propagation import extract_context_from_sqs_message
        >>> from opentelemetry import context as otel_context
        >>>
        >>> def sqs_handler(event, context):
        ...     for record in event['Records']:
        ...         parent_context = extract_context_from_sqs_message(record)
        ...         token = otel_context.attach(parent_context)
        ...         try:
        ...             process_message(record)
        ...         finally:
        ...             otel_context.detach(token)
    """
    carrier = {}

    if "messageAttributes" in message:
        attrs = message["messageAttributes"]

        if "traceparent" in attrs:
            carrier["traceparent"] = attrs["traceparent"].get("stringValue", "")

        if "tracestate" in attrs:
            carrier["tracestate"] = attrs["tracestate"].get("stringValue", "")

    return extract(carrier) if carrier else context.get_current()


def extract_context_from_sns_message(record: dict[str, Any]):
    """
    Extrai trace context de mensagem SNS.

    Args:
        record: Record SNS do evento Lambda.

    Returns:
        OpenTelemetry Context.

    Example:
        >>> from otel_observability.propagation import extract_context_from_sns_message
        >>> from opentelemetry import context as otel_context
        >>>
        >>> def sns_handler(event, context):
        ...     for record in event['Records']:
        ...         parent_context = extract_context_from_sns_message(record)
        ...         token = otel_context.attach(parent_context)
        ...         try:
        ...             process_notification(record)
        ...         finally:
        ...             otel_context.detach(token)
    """
    carrier = {}

    if "Sns" in record and "MessageAttributes" in record["Sns"]:
        attrs = record["Sns"]["MessageAttributes"]

        if "traceparent" in attrs:
            carrier["traceparent"] = attrs["traceparent"].get("Value", "")

        if "tracestate" in attrs:
            carrier["tracestate"] = attrs["tracestate"].get("Value", "")

    return extract(carrier) if carrier else context.get_current()


def extract_context_from_eventbridge_detail(detail: dict[str, Any]):
    """
    Extrai trace context do detail do EventBridge.

    Args:
        detail: Campo 'detail' do evento EventBridge.

    Returns:
        OpenTelemetry Context.

    Example:
        >>> from otel_observability.propagation import extract_context_from_eventbridge_detail
        >>> from opentelemetry import context as otel_context
        >>>
        >>> def eventbridge_handler(event, context):
        ...     detail = event.get('detail', {})
        ...     parent_context = extract_context_from_eventbridge_detail(detail)
        ...     token = otel_context.attach(parent_context)
        ...     try:
        ...         process_event(detail)
        ...     finally:
        ...         otel_context.detach(token)
    """
    carrier = {}

    # Tentar extrair do _trace_context
    if "_trace_context" in detail:
        carrier = detail["_trace_context"]
    else:
        # Tentar extrair do nível raiz
        if "traceparent" in detail:
            carrier["traceparent"] = detail["traceparent"]
        if "tracestate" in detail:
            carrier["tracestate"] = detail["tracestate"]

    return extract(carrier) if carrier else context.get_current()


def extract_context_from_lambda_payload(payload: dict[str, Any]):
    """
    Extrai trace context de payload Lambda.

    Args:
        payload: Payload recebido pela Lambda.

    Returns:
        OpenTelemetry Context.

    Example:
        >>> from otel_observability.propagation import extract_context_from_lambda_payload
        >>> from opentelemetry import context as otel_context
        >>>
        >>> def lambda_handler(event, context):
        ...     parent_context = extract_context_from_lambda_payload(event)
        ...     token = otel_context.attach(parent_context)
        ...     try:
        ...         process_request(event)
        ...     finally:
        ...         otel_context.detach(token)
    """
    carrier = {}

    if "_trace_context" in payload:
        carrier = payload["_trace_context"]

    return extract(carrier) if carrier else context.get_current()


# ============================================================================
# Helpers de Contexto
# ============================================================================


def get_current_trace_context() -> dict[str, str]:
    """
    Obtém o trace context atual como dict (carrier).

    Útil para inspecionar ou armazenar o contexto atual.

    Returns:
        Dict com traceparent, tracestate, etc.

    Example:
        >>> from otel_observability.propagation import get_current_trace_context
        >>>
        >>> context = get_current_trace_context()
        >>> print(f"Current trace: {context.get('traceparent')}")
    """
    carrier = {}
    inject(carrier)
    return carrier


def attach_context(parent_context):
    """
    Anexa um contexto como contexto atual.

    IMPORTANTE: Sempre use com try/finally para garantir detach!

    Args:
        parent_context: Context obtido de extract_context_from_*.

    Returns:
        Token para usar em detach.

    Example:
        >>> from otel_observability.propagation import extract_context_from_http_headers, attach_context
        >>> from opentelemetry import context as otel_context
        >>>
        >>> parent_ctx = extract_context_from_http_headers(headers)
        >>> token = attach_context(parent_ctx)
        >>> try:
        ...     # Agora spans criados serão filhos deste contexto
        ...     with tracer.start_as_current_span("my_operation"):
        ...         pass
        ... finally:
        ...     otel_context.detach(token)
    """
    return context.attach(parent_context)
