"""
Exemplo de aplicação FastAPI configurada para AWS App Runner com padrão Sidecar.

Este exemplo demonstra:
- Configuração de FastAPI com otel-observability
- Envio de métricas para localhost:8125 (DogStatsD)
- Envio de traces para localhost:4318 (OTLP)
- Uso com Datadog Agent como sidecar

Para executar localmente com docker-compose:
    docker-compose -f docker-compose.apprunner.yml up

Para deploy no App Runner:
    1. Configure apprunner.yaml
    2. Configure o Datadog Agent como sidecar (veja docs/APP_RUNNER.md)
"""

import time

from fastapi import FastAPI, HTTPException

from otel_observability import get_logger
from otel_observability.fastapi import instrument_fastapi
from otel_observability.metrics import increment_counter, record_histogram, set_gauge

# Configurar logging
logger = get_logger(__name__)

# Criar aplicação FastAPI
app = FastAPI(
    title="App Runner Example",
    description="Exemplo de aplicação FastAPI para App Runner com Datadog Sidecar",
    version="1.0.0",
)

# Instrumentar com OpenTelemetry
# Traces serão enviados para localhost:4318 (OTLP)
instrument_fastapi(app)


@app.get("/")
async def root():
    """Endpoint raiz."""
    logger.info("Root endpoint accessed")
    increment_counter("app.requests", tags=["endpoint:/", "method:GET"])
    return {"message": "Hello from App Runner!", "status": "ok"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    logger.info("Health check accessed")
    return {"status": "healthy"}


@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    """
    Endpoint de exemplo que demonstra:
    - Tracing automático
    - Métricas customizadas
    - Logging estruturado
    """
    start_time = time.time()

    try:
        logger.info(f"Fetching user {user_id}")

        # Simular processamento
        await simulate_database_query()

        # Calcular latência
        latency = time.time() - start_time

        # Registrar métricas
        increment_counter(
            "app.requests",
            tags=["endpoint:/api/users", "method:GET", "status:success"],
        )
        record_histogram(
            "app.request.latency",
            latency,
            tags=["endpoint:/api/users", "method:GET"],
        )

        return {
            "user_id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com",
        }

    except Exception as e:
        # Registrar erro
        increment_counter(
            "app.errors",
            tags=["endpoint:/api/users", "error_type:database"],
        )
        logger.error(f"Error fetching user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/orders")
async def create_order(order_data: dict):
    """
    Endpoint de exemplo que demonstra funis de conversão.
    """
    logger.info("Creating order", extra={"order_data": order_data})

    try:
        # Simular criação de pedido
        await simulate_order_creation()

        # Registrar métricas de negócio
        increment_counter(
            "app.orders.created",
            tags=["region:us-east-1"],
        )

        return {
            "status": "created",
            "order_id": "order_123",
            "message": "Order created successfully",
        }

    except Exception as e:
        increment_counter(
            "app.errors",
            tags=["endpoint:/api/orders", "error_type:validation"],
        )
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/metrics/demo")
async def metrics_demo():
    """
    Endpoint de demonstração de diferentes tipos de métricas.
    """
    logger.info("Metrics demo endpoint accessed")

    # COUNT: Contar requisições
    increment_counter("app.demo.requests")

    # GAUGE: Simular usuários ativos
    active_users = 150
    set_gauge("app.demo.active_users", active_users, tags=["region:us-east-1"])

    # HISTOGRAM: Simular latência
    latency = 0.125
    record_histogram("app.demo.latency", latency, tags=["endpoint:/api/metrics/demo"])

    return {
        "message": "Metrics demo",
        "metrics_sent": {
            "count": "app.demo.requests",
            "gauge": "app.demo.active_users",
            "histogram": "app.demo.latency",
        },
    }


async def simulate_database_query():
    """Simular query de banco de dados."""
    time.sleep(0.05)  # Simular latência de DB


async def simulate_order_creation():
    """Simular criação de pedido."""
    time.sleep(0.1)  # Simular processamento


if __name__ == "__main__":
    import uvicorn

    print("🚀 Iniciando aplicação App Runner Example")
    print("\n📊 Configuração:")
    print("   - Traces: localhost:4318 (OTLP)")
    print("   - Métricas: localhost:8125 (DogStatsD)")
    print("   - Logs: stdout/stderr (coletados pelo Agent)")
    print("\n💡 Certifique-se de que o Datadog Agent está rodando como sidecar!")
    print("   Veja docs/APP_RUNNER.md para instruções.\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
