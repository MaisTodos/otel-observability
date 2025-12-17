"""
Exemplo completo de tracing distribuído entre múltiplos serviços.

Arquitetura:
- API Gateway → Lambda 1 (create_order)
  → SQS → Lambda 2 (process_payment)
    → SNS → Lambda 3 (send_notification)

Demonstra como o trace_id é propagado através de toda a cadeia.
"""

import json
from typing import Any

import boto3

from otel_observability import get_logger, trace
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability.propagation import (
    inject_context_into_sns_message_attributes,
    inject_context_into_sqs_message_attributes,
)

logger = get_logger(__name__)

# Clients AWS
sqs = boto3.client("sqs")
sns = boto3.client("sns")

# Configurações (em produção, usar variáveis de ambiente)
PAYMENT_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789/payment-queue"
NOTIFICATION_TOPIC_ARN = "arn:aws:sns:us-east-1:123456789:notifications"


# ============================================================================
# Lambda 1: Create Order (entrada via API Gateway)
# ============================================================================


@instrument_lambda_handler()
def create_order_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda 1: Recebe requisição HTTP e cria pedido.

    Trace context é extraído automaticamente dos headers HTTP.
    Este Lambda inicia ou continua um trace distribuído.
    """
    logger.info("Creating order")

    # Parse body
    body = json.loads(event.get("body", "{}"))
    order_id = body.get("order_id", 12345)
    amount = body.get("amount", 99.99)

    # Criar pedido
    order = create_order(order_id, amount)

    # Enviar para fila de pagamento com trace context
    send_payment_to_queue(order)

    return {
        "statusCode": 201,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "order_id": order["order_id"],
                "status": "created",
                "message": "Order created successfully",
            }
        ),
    }


@trace("create_order")
def create_order(order_id: int, amount: float) -> dict[str, Any]:
    """Cria pedido no banco de dados (simulado)."""
    logger.info("Creating order in database", extra={"order_id": order_id})

    # Simular salvamento no DynamoDB
    order = {"order_id": order_id, "amount": amount, "status": "pending", "currency": "BRL"}

    logger.debug("Order created", extra=order)
    return order


@trace("send_payment_to_queue")
def send_payment_to_queue(order: dict[str, Any]):
    """
    Envia mensagem para fila SQS com trace context.

    IMPORTANTE: inject_context_into_sqs_message_attributes() captura
    o trace context atual e injeta nos messageAttributes.
    """
    logger.info("Sending payment to queue", extra={"order_id": order["order_id"]})

    try:
        response = sqs.send_message(
            QueueUrl=PAYMENT_QUEUE_URL,
            MessageBody=json.dumps(
                {
                    "order_id": order["order_id"],
                    "amount": order["amount"],
                    "currency": order["currency"],
                }
            ),
            # CRÍTICO: Injetar trace context
            MessageAttributes=inject_context_into_sqs_message_attributes(),
        )

        logger.info("Payment message sent", extra={"message_id": response["MessageId"]})

    except Exception as e:
        logger.exception("Failed to send payment to queue", exc_info=e)
        raise


# ============================================================================
# Lambda 2: Process Payment (trigger: SQS)
# ============================================================================


@instrument_lambda_handler()
def process_payment_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda 2: Processa pagamentos da fila SQS.

    Trace context é extraído automaticamente dos messageAttributes.
    Este Lambda cria spans FILHOS do trace iniciado em Lambda 1.
    """
    logger.info(f"Processing {len(event['Records'])} payment messages")

    for record in event["Records"]:
        message = json.loads(record["body"])

        # Processar pagamento
        payment_result = process_payment(message)

        # Enviar notificação via SNS
        send_notification(payment_result)

    return {"statusCode": 200}


@trace("process_payment")
def process_payment(payment_data: dict[str, Any]) -> dict[str, Any]:
    """Processa pagamento (simulado)."""
    order_id = payment_data["order_id"]
    amount = payment_data["amount"]

    logger.info("Processing payment", extra={"order_id": order_id, "amount": amount})

    # Simular validação
    validate_payment(payment_data)

    # Simular chamada a gateway de pagamento
    transaction_id = charge_payment(payment_data)

    logger.info(
        "Payment processed successfully",
        extra={"order_id": order_id, "transaction_id": transaction_id},
    )

    return {
        "order_id": order_id,
        "amount": amount,
        "transaction_id": transaction_id,
        "status": "completed",
    }


@trace("validate_payment")
def validate_payment(payment_data: dict[str, Any]):
    """Valida dados do pagamento."""
    logger.debug("Validating payment")

    if payment_data["amount"] <= 0:
        raise ValueError("Invalid amount")

    if payment_data["amount"] > 10000:
        raise ValueError("Amount exceeds limit")


@trace("charge_payment")
def charge_payment(payment_data: dict[str, Any]) -> str:
    """Processa cobrança no gateway."""
    logger.debug("Charging payment gateway")

    # Simular chamada a API externa
    return f"txn_{payment_data['order_id']}"


@trace("send_notification")
def send_notification(payment_result: dict[str, Any]):
    """
    Publica notificação no SNS com trace context.

    IMPORTANTE: inject_context_into_sns_message_attributes() captura
    o trace context atual e injeta nos MessageAttributes.
    """
    logger.info("Sending notification to SNS", extra={"order_id": payment_result["order_id"]})

    try:
        response = sns.publish(
            TopicArn=NOTIFICATION_TOPIC_ARN,
            Subject=f"Payment Completed - Order {payment_result['order_id']}",
            Message=json.dumps(
                {
                    "event_type": "payment.completed",
                    "order_id": payment_result["order_id"],
                    "amount": payment_result["amount"],
                    "transaction_id": payment_result["transaction_id"],
                }
            ),
            # CRÍTICO: Injetar trace context
            MessageAttributes=inject_context_into_sns_message_attributes(),
        )

        logger.info("Notification sent", extra={"message_id": response["MessageId"]})

    except Exception as e:
        logger.exception("Failed to send notification", exc_info=e)
        raise


# ============================================================================
# Lambda 3: Send Email (trigger: SNS)
# ============================================================================


@instrument_lambda_handler()
def send_email_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda 3: Envia email de notificação.

    Trace context é extraído automaticamente dos MessageAttributes.
    Este Lambda cria spans NETOS do trace iniciado em Lambda 1.

    Hierarquia de spans:
    - Lambda 1: create_order
      └─ Lambda 2: process_payment
         └─ Lambda 3: send_email  ← estamos aqui
    """
    logger.info(f"Processing {len(event['Records'])} notification messages")

    for record in event["Records"]:
        sns_message = record["Sns"]
        message = json.loads(sns_message["Message"])

        # Enviar email
        send_email(message)

    return {"statusCode": 200}


@trace("send_email")
def send_email(notification: dict[str, Any]):
    """Envia email de notificação (simulado)."""
    order_id = notification["order_id"]

    logger.info(
        "Sending email notification",
        extra={"order_id": order_id, "event_type": notification["event_type"]},
    )

    # Simular envio de email via SES
    email_id = f"email_{order_id}"

    logger.info("Email sent successfully", extra={"order_id": order_id, "email_id": email_id})


# ============================================================================
# Teste Local (Simulação)
# ============================================================================

if __name__ == "__main__":
    import os

    # Configurar ambiente
    os.environ["OTEL_SERVICE_NAME"] = "distributed-tracing-example"
    os.environ["OTEL_ENVIRONMENT"] = "development"
    os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "test-lambda"
    os.environ["OTEL_CONSOLE_EXPORT"] = "true"

    # Mock context
    class MockContext:
        function_name = "test-lambda"
        function_version = "$LATEST"
        memory_limit_in_mb = 128
        aws_request_id = "test-request-id"

    print("=" * 80)
    print("Simulando fluxo completo de tracing distribuído")
    print("=" * 80)
    print()

    # Simular requisição inicial (API Gateway)
    print("1. Lambda 1: Create Order (API Gateway trigger)")
    print("-" * 80)

    api_event = {
        "httpMethod": "POST",
        "path": "/orders",
        "headers": {
            "Content-Type": "application/json",
            # Em produção, traceparent viria do cliente/load balancer
            # "traceparent": "00-abc123...-def456...-01"
        },
        "body": json.dumps({"order_id": 12345, "amount": 99.99}),
    }

    # Comentar chamada real pois precisa de AWS credentials
    # result = create_order_handler(api_event, MockContext())
    # print(json.dumps(result, indent=2))

    print("\nNOTA: Para testar localmente com AWS, configure:")
    print("  - AWS credentials")
    print("  - Fila SQS: PAYMENT_QUEUE_URL")
    print("  - Tópico SNS: NOTIFICATION_TOPIC_ARN")
    print()
    print("No Datadog, você verá UM trace completo com 3 spans:")
    print("  - create_order (Lambda 1)")
    print("    └─ process_payment (Lambda 2)")
    print("       └─ send_email (Lambda 3)")
    print()
    print("Todos compartilham o mesmo trace_id! 🎉")
