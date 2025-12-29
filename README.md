# otel-observability

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-1.20+-blueviolet.svg)](https://opentelemetry.io/)

Biblioteca Python simplificada de **OpenTelemetry** para **FastAPI**, **AWS Lambda** e **Chalice** com integração nativa ao **Datadog**.

---

## 📖 Documentação

- **[Conceitos](docs/CONCEPTS.md)** - O que é OpenTelemetry, traces, spans e propagação de contexto
- **[Arquitetura](docs/ARCHITECTURE.md)** - Como funciona o fluxo de dados e integração com Datadog
- **[Instalação](docs/INSTALLATION.md)** - Como instalar e extras disponíveis
- **[Guia de Uso](docs/USAGE.md)** - Exemplos completos para FastAPI e Lambda
- **[Configuração](docs/CONFIGURATION.md)** - Variáveis de ambiente e cenários de deployment
- **[Auto-Instrumentação](docs/AUTO_INSTRUMENTATION.md)** - Bibliotecas suportadas e como funciona
- **[Datadog](docs/DATADOG.md)** - Observabilidade e troubleshooting
- **[Métricas](docs/METRICS.md)** - Métricas customizadas com DogStatsD e funis de conversão
- **[App Runner](docs/APP_RUNNER.md)** - Guia de uso com AWS App Runner e padrão Sidecar
- **[Logging](docs/LOGGING.md)** - Sistema de logging estruturado com contexto customizado
- **[Testing](docs/TESTING.md)** - Guia de testes

---

## 🚀 Quick Start

### FastAPI

```python
from fastapi import FastAPI
from otel_observability.fastapi import instrument_fastapi
from otel_observability import get_logger, trace

app = FastAPI()

# Instrumentar ANTES de definir rotas
instrument_fastapi(app)

logger = get_logger(__name__)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    logger.info("Fetching user", extra={"user_id": user_id})
    return {"user_id": user_id, "name": f"User {user_id}"}

@trace("process_payment")
async def process_payment(amount: float):
    logger.info("Processing payment", extra={"amount": amount})
    return {"status": "success"}
```

### Métricas Customizadas

```python
from otel_observability.metrics import increment_counter, track_funnel_step

# Contar requisições
increment_counter("app.requests", tags=["endpoint:/api/users"])

# Rastrear funil de conversão
track_funnel_step("checkout", "start", tags=["region:us-east-1"])
track_funnel_step("checkout", "payment_success", tags=["region:us-east-1"])
track_funnel_step("checkout", "completed", tags=["region:us-east-1"])
```

### AWS Lambda

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability import get_logger, trace

logger = get_logger(__name__)

@instrument_lambda_handler()
def lambda_handler(event, context):
    logger.info("Processing request")

    # Trace context é extraído automaticamente de:
    # - API Gateway headers
    # - SQS messageAttributes
    # - SNS MessageAttributes
    # - EventBridge detail

    result = process_event(event)
    return {"statusCode": 200, "body": result}

@trace("process_event")
def process_event(event):
    logger.debug("Processing event", extra={"event_type": event.get("type")})
    return "processed"
```

### Chalice

```python
from chalice import Chalice
from otel_observability.chalice import instrument_chalice, trace_sqs_message
from otel_observability import get_logger, trace

app = Chalice(app_name='myapp')

# Instrumentar ANTES de definir rotas
instrument_chalice(app)

logger = get_logger(__name__)

@app.route('/users/{user_id}')
def get_user(user_id: int):
    logger.info("Fetching user", extra={"user_id": user_id})
    return {"user_id": user_id}

@app.on_sqs_message(queue_name='my-queue')
@trace_sqs_message()
def process_message(event):
    logger.info("Processing SQS message")
    return {"status": "processed"}
```

---

## 📦 Instalação

```bash
# FastAPI
poetry add otel-observability[fastapi]

# Lambda
poetry add otel-observability[lambda]

# Chalice
poetry add otel-observability[chalice]

# Métricas customizadas (DogStatsD)
poetry add otel-observability[metrics]

# Tudo
poetry add otel-observability[all]
```

Veja [Instalação](docs/INSTALLATION.md) para mais detalhes e outras opções de instalação.

---

## ⚙️ Configuração Básica

```bash
# Obrigatórias
export OTEL_SERVICE_NAME=my-service
export OTEL_ENVIRONMENT=production
export OTEL_SERVICE_VERSION=1.0.0
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export DD_API_KEY=your-datadog-api-key
export DD_SITE=datadoghq.com
```

Veja [Configuração](docs/CONFIGURATION.md) para configuração detalhada e diferentes cenários.

---

## 📝 Exemplos Completos

Veja exemplos detalhados em:
- [`examples/fastapi_example.py`](examples/fastapi_example.py) - FastAPI com múltiplos casos de uso
- [`examples/lambda_example.py`](examples/lambda_example.py) - Lambda com diferentes triggers
- [`examples/distributed_tracing_example.py`](examples/distributed_tracing_example.py) - Tracing distribuído completo
- [`examples/metrics_example.py`](examples/metrics_example.py) - Métricas customizadas (COUNT, GAUGE, HISTOGRAM)
- [`examples/funnel_metrics_example.py`](examples/funnel_metrics_example.py) - Funis de conversão completos
- [`examples/app_runner_example.py`](examples/app_runner_example.py) - App Runner com padrão Sidecar

---

## 🔑 Características Principais

- ✅ **Tracing Distribuído** - Rastreamento end-to-end entre serviços
- ✅ **Métricas Customizadas** - DogStatsD para métricas de negócio e funis de conversão
- ✅ **Auto-Instrumentação** - Instrumenta bibliotecas automaticamente (httpx, requests, boto3, etc.)
- ✅ **Logging Estruturado** - Logs correlacionados com traces via `trace_id` e `span_id`
- ✅ **Contexto Customizado** - Adicione contexto customizado aos logs automaticamente
- ✅ **Propagação Automática** - Contexto propagado automaticamente em chamadas HTTP
- ✅ **Integração Datadog** - Envio direto via OTLP para Datadog Agent/Extension

---

## 📚 Recursos Adicionais

- [OpenTelemetry Docs](https://opentelemetry.io/docs/)
- [Datadog APM](https://docs.datadoghq.com/tracing/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)

---
