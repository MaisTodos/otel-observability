"""
Exemplo de uso da biblioteca otel-observability com FastAPI.

Este exemplo demonstra:
1. Instrumentação automática de endpoints
2. Tracing distribuído entre serviços
3. Logging correlacionado com traces
4. Spans customizados para operações de negócio
5. Propagação de contexto em chamadas HTTP externas

Para executar:
    export OTEL_SERVICE_NAME=fastapi-example
    export OTEL_ENVIRONMENT=development
    uvicorn examples.fastapi_example:app --reload
"""

import asyncio

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import BaseModel

from otel_observability import get_logger, trace

# Importar instrumentação
from otel_observability.fastapi import add_span_attribute, add_span_event, instrument_fastapi

# Criar app FastAPI
app = FastAPI(
    title="FastAPI com OpenTelemetry",
    description="Exemplo de observabilidade com tracing distribuído",
)

# IMPORTANTE: Instrumentar ANTES de definir rotas
instrument_fastapi(
    app,
    json_logs=False,  # Use True em produção
    excluded_urls="/health|/metrics",  # Excluir health checks
)

# Logger com correlação automática de trace_id e span_id
logger = get_logger(__name__)


# Models
class PaymentRequest(BaseModel):
    user_id: int
    amount: float
    currency: str = "BRL"


class PaymentResponse(BaseModel):
    transaction_id: str
    status: str
    amount: float


# ============================================================================
# EXEMPLO 1: Endpoint simples (instrumentação automática)
# ============================================================================


@app.get("/")
async def root():
    """
    Endpoint raiz - demonstra instrumentação automática.

    O span é criado automaticamente pelo FastAPIInstrumentor.
    Logs são automaticamente correlacionados com o trace.
    """
    logger.info("Root endpoint accessed")
    return {"message": "FastAPI com OpenTelemetry", "version": "1.0"}


@app.get("/health")
async def health():
    """Health check - excluído do tracing via excluded_urls."""
    return {"status": "healthy"}


# ============================================================================
# EXEMPLO 2: Endpoint com atributos customizados
# ============================================================================


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    """
    Buscar usuário - demonstra adição de atributos customizados ao span.
    """
    logger.info("Fetching user", extra={"user_id": user_id})

    # Adicionar atributos de negócio ao span atual
    add_span_attribute("user.id", user_id)
    add_span_attribute("operation.type", "read")

    # Simular busca no banco
    await asyncio.sleep(0.1)  # Simula latência

    # Adicionar evento ao span
    add_span_event("user.found", {"user_id": user_id})

    return {"user_id": user_id, "name": f"User {user_id}", "email": f"user{user_id}@example.com"}


# ============================================================================
# EXEMPLO 3: Spans customizados para operações de negócio
# ============================================================================


@app.post("/payments", response_model=PaymentResponse)
async def process_payment(payment: PaymentRequest):
    """
    Processar pagamento - demonstra uso de spans customizados.

    A árvore de spans será:
    - POST /payments (automático)
      ├─ validate_payment (customizado)
      ├─ check_fraud (customizado)
      └─ charge_payment (customizado)
    """
    logger.info(
        "Processing payment",
        extra={"user_id": payment.user_id, "amount": payment.amount, "currency": payment.currency},
    )

    # Adicionar atributos ao span da requisição
    add_span_attribute("user.id", payment.user_id)
    add_span_attribute("payment.amount", payment.amount)
    add_span_attribute("payment.currency", payment.currency)

    try:
        # Validar pagamento (span customizado)
        await validate_payment(payment)

        # Verificar fraude (span customizado)
        is_fraud = await check_fraud(payment.user_id, payment.amount)
        if is_fraud:
            raise HTTPException(status_code=400, detail="Payment blocked - fraud detected")

        # Processar cobrança (span customizado)
        transaction_id = await charge_payment(payment)

        add_span_event("payment.completed", {"transaction_id": transaction_id})

        logger.info("Payment completed successfully", extra={"transaction_id": transaction_id})

        return PaymentResponse(
            transaction_id=transaction_id, status="success", amount=payment.amount
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Payment processing failed", exc_info=e)
        raise HTTPException(status_code=500, detail="Payment processing failed") from e


@trace("validate_payment", attributes={"operation.type": "validation"})
async def validate_payment(payment: PaymentRequest):
    """Validar dados do pagamento - span customizado."""
    logger.debug("Validating payment")

    if payment.amount <= 0:
        raise ValueError("Amount must be positive")

    if payment.amount > 10000:
        raise ValueError("Amount exceeds limit")

    await asyncio.sleep(0.05)  # Simula validação
    add_span_event("validation.passed")


@trace("check_fraud")
async def check_fraud(user_id: int, amount: float) -> bool:
    """
    Verificar fraude - span customizado.

    Em produção, isso chamaria um serviço externo de análise de fraude.
    """
    logger.debug("Checking fraud", extra={"user_id": user_id, "amount": amount})

    add_span_attribute("fraud.user_id", user_id)
    add_span_attribute("fraud.amount", amount)

    await asyncio.sleep(0.1)  # Simula chamada a serviço externo

    # Simulação simples: valores acima de 5000 são suspeitos
    is_fraud = amount > 5000

    add_span_attribute("fraud.detected", is_fraud)
    add_span_event("fraud_check.completed", {"result": "fraud" if is_fraud else "clean"})

    return is_fraud


@trace("charge_payment")
async def charge_payment(payment: PaymentRequest) -> str:
    """Processar cobrança - span customizado."""
    logger.debug("Charging payment")

    await asyncio.sleep(0.2)  # Simula processamento

    transaction_id = f"txn_{payment.user_id}_{int(payment.amount * 100)}"

    add_span_attribute("transaction.id", transaction_id)
    add_span_event("charge.completed")

    return transaction_id


# ============================================================================
# EXEMPLO 4: Chamadas HTTP externas (tracing distribuído)
# ============================================================================


@app.get("/external-call")
async def call_external_service():
    """
    Demonstra tracing distribuído em chamadas HTTP externas.

    O contexto de trace é automaticamente propagado via headers
    (traceparent, tracestate) para o serviço downstream.
    """
    logger.info("Calling external service")

    add_span_event("external_call.started")

    # httpx com instrumentação automática propaga o contexto
    async with httpx.AsyncClient() as client:
        try:
            # O trace context é propagado automaticamente via headers
            response = await client.get("https://jsonplaceholder.typicode.com/posts/1", timeout=5.0)

            add_span_attribute("http.status_code", response.status_code)
            add_span_event("external_call.completed")

            logger.info("External call completed", extra={"status_code": response.status_code})

            return {"status": "success", "data": response.json()}

        except httpx.TimeoutException as e:
            logger.warning("External call timed out")
            add_span_event("external_call.timeout")
            raise HTTPException(status_code=504, detail="External service timeout") from e

        except Exception as e:
            logger.exception("External call failed", exc_info=e)
            add_span_event("external_call.error", {"error": str(e)})
            raise HTTPException(status_code=502, detail="External service error") from e


# ============================================================================
# EXEMPLO 5: Simulação de microserviços (propagação de contexto)
# ============================================================================


@app.get("/order/{order_id}")
async def process_order(order_id: int):
    """
    Simula processamento de pedido que chama múltiplos serviços.

    Em produção:
    - order-service chama -> inventory-service
    - order-service chama -> payment-service
    - order-service chama -> notification-service

    Todos compartilham o mesmo trace_id (tracing distribuído).
    """
    logger.info("Processing order", extra={"order_id": order_id})

    add_span_attribute("order.id", order_id)

    # Simular chamadas a diferentes serviços
    inventory_result = await call_inventory_service(order_id)
    payment_result = await call_payment_service(order_id)
    notification_result = await call_notification_service(order_id)

    add_span_event("order.completed", {"order_id": order_id})

    return {
        "order_id": order_id,
        "status": "completed",
        "inventory": inventory_result,
        "payment": payment_result,
        "notification": notification_result,
    }


@trace("call_inventory_service")
async def call_inventory_service(order_id: int):
    """Simula chamada ao serviço de inventário."""
    logger.debug("Calling inventory service", extra={"order_id": order_id})
    await asyncio.sleep(0.1)
    add_span_event("inventory.checked")
    return {"status": "available"}


@trace("call_payment_service")
async def call_payment_service(order_id: int):
    """Simula chamada ao serviço de pagamento."""
    logger.debug("Calling payment service", extra={"order_id": order_id})
    await asyncio.sleep(0.15)
    add_span_event("payment.processed")
    return {"status": "charged"}


@trace("call_notification_service")
async def call_notification_service(order_id: int):
    """Simula chamada ao serviço de notificação."""
    logger.debug("Calling notification service", extra={"order_id": order_id})
    await asyncio.sleep(0.05)
    add_span_event("notification.sent")
    return {"status": "sent"}


if __name__ == "__main__":
    # Configurar variáveis de ambiente para desenvolvimento
    import os

    import uvicorn

    os.environ.setdefault("OTEL_SERVICE_NAME", "fastapi-example")
    os.environ.setdefault("OTEL_ENVIRONMENT", "development")
    os.environ.setdefault("OTEL_SERVICE_VERSION", "1.0.0")

    # Para desenvolvimento local, pode usar console exporter
    os.environ.setdefault("OTEL_CONSOLE_EXPORT", "true")

    uvicorn.run(app, host="0.0.0.0", port=8000)
