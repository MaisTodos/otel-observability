"""
Exemplo de uso da biblioteca otel-observability com AWS Lambda.

Este exemplo demonstra:
1. Instrumentação de Lambda handlers
2. Tracing distribuído entre Lambdas (via SQS, SNS, EventBridge)
3. Logging correlacionado com traces
4. Extração automática de trace context de eventos
5. Diferentes tipos de eventos (API Gateway, SQS, SNS, EventBridge)

Para testar localmente:
    export OTEL_SERVICE_NAME=lambda-example
    export OTEL_ENVIRONMENT=development
    export AWS_LAMBDA_FUNCTION_NAME=my-lambda  # Simula ambiente Lambda

    python -c "from examples.lambda_example import *; api_gateway_handler({'httpMethod': 'GET', 'path': '/users/123'}, None)"
"""

import json
from typing import Any

from otel_observability import get_logger, trace
from otel_observability.aws_lambda import instrument_lambda_handler

logger = get_logger(__name__)


# ============================================================================
# EXEMPLO 1: API Gateway Lambda (HTTP)
# ============================================================================


@instrument_lambda_handler()
def api_gateway_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler para API Gateway.

    Trace context é extraído automaticamente dos headers HTTP:
    - traceparent (W3C Trace Context)
    - X-Amzn-Trace-Id (AWS X-Ray)

    Se o API Gateway recebeu uma requisição com headers de trace,
    este Lambda será um span filho daquele trace (tracing distribuído).
    """
    logger.info("API Gateway request received")

    # Extrair informações da requisição
    http_method = event.get("httpMethod", "GET")
    path = event.get("path", "/")

    logger.info(
        f"Processing {http_method} {path}", extra={"http_method": http_method, "path": path}
    )

    try:
        # Lógica de negócio
        result = process_api_request(event)

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result),
        }

    except Exception as e:
        logger.exception("API request failed", exc_info=e)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


@trace("process_api_request")
def process_api_request(event: dict[str, Any]) -> dict[str, Any]:
    """Processar requisição da API - span customizado."""
    path = event.get("path", "/")

    if "/users/" in path:
        user_id = path.split("/")[-1]
        logger.debug("Fetching user", extra={"user_id": user_id})

        return {
            "user_id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com",
        }

    return {"message": "Hello from Lambda!"}


# ============================================================================
# EXEMPLO 2: SQS Lambda (tracing distribuído via queue)
# ============================================================================


@instrument_lambda_handler()
def sqs_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler para processar mensagens SQS.

    Trace context é extraído automaticamente dos messageAttributes:
    - traceparent (injetado pelo produtor)
    - _X_AMZN_TRACE_ID (AWS X-Ray)

    IMPORTANTE: O produtor deve injetar o trace context ao enviar para SQS.
    Exemplo de como enviar mensagem com trace context:

        from opentelemetry.propagate import inject

        carrier = {}
        inject(carrier)  # Injeta traceparent, tracestate

        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(data),
            MessageAttributes={
                'traceparent': {'StringValue': carrier['traceparent'], 'DataType': 'String'},
                'tracestate': {'StringValue': carrier.get('tracestate', ''), 'DataType': 'String'}
            }
        )
    """
    logger.info(f"Processing {len(event['Records'])} SQS messages")

    for record in event["Records"]:
        message_id = record["messageId"]
        body = json.loads(record["body"])

        logger.info("Processing SQS message", extra={"message_id": message_id, "body": body})

        # Processar cada mensagem em um span separado
        process_sqs_message(body)

    return {"statusCode": 200, "processed": len(event["Records"])}


@trace("process_sqs_message")
def process_sqs_message(message: dict[str, Any]):
    """Processar mensagem individual - span customizado."""
    logger.debug("Processing message", extra={"message": message})

    # Lógica de processamento
    if message.get("type") == "order":
        process_order(message["order_id"])
    elif message.get("type") == "payment":
        process_payment(message["payment_id"])
    else:
        logger.warning(f"Unknown message type: {message.get('type')}")


@trace("process_order")
def process_order(order_id: int):
    """Processar pedido."""
    logger.info("Processing order", extra={"order_id": order_id})
    # ... lógica ...


@trace("process_payment")
def process_payment(payment_id: int):
    """Processar pagamento."""
    logger.info("Processing payment", extra={"payment_id": payment_id})
    # ... lógica ...


# ============================================================================
# EXEMPLO 3: SNS Lambda (tracing distribuído via pub/sub)
# ============================================================================


@instrument_lambda_handler()
def sns_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler para processar mensagens SNS.

    Trace context é extraído automaticamente dos MessageAttributes.

    IMPORTANTE: O publicador deve injetar o trace context ao publicar no SNS.
    Exemplo:

        from opentelemetry.propagate import inject

        carrier = {}
        inject(carrier)

        sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps(data),
            MessageAttributes={
                'traceparent': {'StringValue': carrier['traceparent'], 'DataType': 'String'}
            }
        )
    """
    logger.info(f"Processing {len(event['Records'])} SNS messages")

    for record in event["Records"]:
        sns_message = record["Sns"]
        message_id = sns_message["MessageId"]
        message = sns_message["Message"]

        logger.info(
            "Processing SNS message",
            extra={"message_id": message_id, "subject": sns_message.get("Subject", "N/A")},
        )

        # Processar mensagem
        process_notification(json.loads(message))

    return {"statusCode": 200}


@trace("process_notification")
def process_notification(notification: dict[str, Any]):
    """Processar notificação - span customizado."""
    logger.info(
        "Processing notification",
        extra={"type": notification.get("type"), "user_id": notification.get("user_id")},
    )
    # ... lógica de notificação ...


# ============================================================================
# EXEMPLO 4: EventBridge Lambda (tracing distribuído via eventos)
# ============================================================================


@instrument_lambda_handler()
def eventbridge_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler para EventBridge.

    Trace context é extraído do campo 'detail'.

    Exemplo de como enviar evento com trace context:

        from opentelemetry.propagate import inject

        carrier = {}
        inject(carrier)

        events.put_events(
            Entries=[{
                'Source': 'my.app',
                'DetailType': 'order.created',
                'Detail': json.dumps({
                    'order_id': 123,
                    'traceparent': carrier['traceparent'],
                    'tracestate': carrier.get('tracestate', '')
                })
            }]
        )
    """
    detail_type = event.get("detail-type")
    source = event.get("source")
    detail = event.get("detail", {})

    logger.info("EventBridge event received", extra={"detail_type": detail_type, "source": source})

    # Roteamento baseado no tipo de evento
    if detail_type == "order.created":
        handle_order_created(detail)
    elif detail_type == "order.updated":
        handle_order_updated(detail)
    elif detail_type == "order.cancelled":
        handle_order_cancelled(detail)
    else:
        logger.warning(f"Unknown event type: {detail_type}")

    return {"statusCode": 200}


@trace("handle_order_created")
def handle_order_created(detail: dict[str, Any]):
    """Handler para evento de pedido criado."""
    order_id = detail.get("order_id")
    logger.info("Handling order created", extra={"order_id": order_id})
    # ... lógica ...


@trace("handle_order_updated")
def handle_order_updated(detail: dict[str, Any]):
    """Handler para evento de pedido atualizado."""
    order_id = detail.get("order_id")
    logger.info("Handling order updated", extra={"order_id": order_id})
    # ... lógica ...


@trace("handle_order_cancelled")
def handle_order_cancelled(detail: dict[str, Any]):
    """Handler para evento de pedido cancelado."""
    order_id = detail.get("order_id")
    logger.info("Handling order cancelled", extra={"order_id": order_id})
    # ... lógica ...


# ============================================================================
# EXEMPLO 5: Lambda que chama outro Lambda (tracing distribuído)
# ============================================================================


@instrument_lambda_handler()
def orchestrator_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda orquestrador que invoca outros Lambdas.

    Para propagar o trace context ao invocar outro Lambda:

        import boto3
        from opentelemetry.propagate import inject

        lambda_client = boto3.client('lambda')

        # Injetar trace context no payload
        carrier = {}
        inject(carrier)

        payload = {
            'data': {...},
            '_trace_context': carrier  # Incluir contexto
        }

        response = lambda_client.invoke(
            FunctionName='downstream-lambda',
            InvocationType='Event',  # Assíncrono
            Payload=json.dumps(payload)
        )
    """
    logger.info("Orchestrator lambda started")

    # Simular orquestração de múltiplos Lambdas
    step1_result = execute_step1()
    step2_result = execute_step2(step1_result)
    step3_result = execute_step3(step2_result)

    logger.info("Orchestration completed")

    return {
        "statusCode": 200,
        "body": json.dumps({"step1": step1_result, "step2": step2_result, "step3": step3_result}),
    }


@trace("execute_step1")
def execute_step1() -> str:
    """Primeiro passo da orquestração."""
    logger.info("Executing step 1")
    # Em produção: invocar Lambda ou chamar API
    return "step1_completed"


@trace("execute_step2")
def execute_step2(previous_result: str) -> str:
    """Segundo passo da orquestração."""
    logger.info("Executing step 2", extra={"previous_result": previous_result})
    return "step2_completed"


@trace("execute_step3")
def execute_step3(previous_result: str) -> str:
    """Terceiro passo da orquestração."""
    logger.info("Executing step 3", extra={"previous_result": previous_result})
    return "step3_completed"


# ============================================================================
# Testes locais
# ============================================================================

if __name__ == "__main__":
    import os

    # Configurar ambiente para simular Lambda
    os.environ["OTEL_SERVICE_NAME"] = "lambda-example"
    os.environ["OTEL_ENVIRONMENT"] = "development"
    os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "my-lambda"
    os.environ["OTEL_CONSOLE_EXPORT"] = "true"

    # Mock do contexto Lambda
    class MockContext:
        function_name = "my-lambda"
        function_version = "$LATEST"
        memory_limit_in_mb = 128
        aws_request_id = "test-request-id"

    # Teste 1: API Gateway
    print("=" * 80)
    print("Teste 1: API Gateway")
    print("=" * 80)
    api_event = {
        "httpMethod": "GET",
        "path": "/users/123",
        "headers": {"Content-Type": "application/json"},
    }
    result = api_gateway_handler(api_event, MockContext())
    print(json.dumps(result, indent=2))

    # Teste 2: SQS
    print("\n" + "=" * 80)
    print("Teste 2: SQS")
    print("=" * 80)
    sqs_event = {
        "Records": [
            {
                "messageId": "msg-123",
                "eventSource": "aws:sqs",
                "body": json.dumps({"type": "order", "order_id": 456}),
                "messageAttributes": {},
            }
        ]
    }
    result = sqs_handler(sqs_event, MockContext())
    print(json.dumps(result, indent=2))
