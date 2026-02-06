# Guia de Implementação da Biblioteca `otel-observability`

## 1. Objetivo do Guia

Este guia orienta a implementação da biblioteca `otel-observability` em serviços Python
com foco em AWS (Lambda, Chalice, App Runner) e FastAPI. Foi escrito para ser
autoexplicativo e fácil de interpretar por desenvolvedores e por agentes de IA.

---

## 2. Visão Geral da Biblioteca

### 2.1 Problema que resolve

- Tracing distribuído end-to-end entre serviços.
- Logging estruturado com correlação automática com traces.
- Métricas customizadas de negócio via DogStatsD.
- Propagação de contexto em HTTP, SQS, SNS, EventBridge.

### 2.2 Principais módulos

- `otel_observability.tracer` – configuração base de OpenTelemetry.
- `otel_observability.fastapi` – integração com FastAPI.
- `otel_observability.aws_lambda` – integração com AWS Lambda.
- `otel_observability.chalice` – integração com Chalice.
- `otel_observability.logging` – logging estruturado e contexto de logs.
- `otel_observability.propagation` – propagação de contexto (SQS, SNS, EventBridge).
- `otel_observability.metrics` – métricas customizadas via DogStatsD.

---

## 3. Configuração Inicial

### 3.1 Instalação

Use o extra adequado para o seu cenário.

**FastAPI:**

```bash
pip install "otel-observability[fastapi]"
```

**Lambda / Chalice:**

```bash
pip install "otel-observability[lambda]"
```

**Métricas DogStatsD:**

```bash
pip install "otel-observability[metrics]"
```

Combine extras quando necessário (exemplo: Lambda + métricas):

```bash
pip install "otel-observability[lambda,metrics]"
```

Para instalação via `uv` ou `poetry`, consulte [INSTALLATION.md](./INSTALLATION.md).

### 3.2 Variáveis de ambiente mínimas

Defina sempre as tags de serviço padrão:

```bash
export OTEL_SERVICE_NAME=my-service
export OTEL_ENVIRONMENT=production    # dev, staging, production
export OTEL_SERVICE_VERSION=1.0.0

export DD_API_KEY=your-datadog-api-key
export DD_SITE=datadoghq.com          # datadoghq.com, datadoghq.eu, us3, etc.
```

Configure o endpoint OTLP conforme o cenário (Lambda Extension, Agent, ou intake
direto). Detalhes em [CONFIGURATION.md](./CONFIGURATION.md).

### 3.3 Ordem recomendada de adoção

1. Tracing básico no serviço principal.
2. Logging estruturado com correlação de traces.
3. Propagação de contexto entre serviços.
4. Métricas customizadas para KPIs de negócio.

---

## 4. Casos de Uso Comuns

### 4.1 FastAPI

**Objetivo:** instrumentar uma API FastAPI com tracing, logs estruturados e
auto-instrumentação de clientes HTTP.

**Passos:**

1. Instalar com extra `fastapi`.
2. Configurar variáveis de ambiente.
3. Chamar `instrument_fastapi(app)` logo após criar o app.

**Exemplo mínimo:**

```python
from fastapi import FastAPI
from otel_observability.fastapi import instrument_fastapi
from otel_observability import get_logger

app = FastAPI()
instrument_fastapi(app)

logger = get_logger(__name__)


@app.get("/health")
async def health():
    logger.info("healthcheck")
    return {"status": "ok"}
```

Casos avançados e exemplos completos em [USAGE.md](./USAGE.md).

### 4.2 AWS Lambda (handlers diretos)

**Objetivo:** instrumentar funções Lambda com extração automática de
`traceparent` de API Gateway, SQS, SNS e EventBridge.

**Passos:**

1. Instalar com extra `lambda`.
2. Configurar variáveis de ambiente e Datadog Lambda Extension.
3. Decorar handlers com `@instrument_lambda_handler()`.

**Exemplo mínimo:**

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability import get_logger

logger = get_logger(__name__)


@instrument_lambda_handler()
def handler(event, context):
    logger.info("Lambda invoked", extra={"event_type": event.get("source")})
    return {"statusCode": 200, "body": "ok"}
```

Mais exemplos em [USAGE.md](./USAGE.md) e [DATADOG.md](./DATADOG.md).

### 4.3 Chalice (HTTP + SQS)

**Objetivo:** instrumentar aplicações Chalice que expõem rotas HTTP e
consomem mensagens SQS.

**Passos:**

1. Instalar com extra `lambda`.
2. Configurar variáveis de ambiente.
3. Chamar `instrument_chalice(app)` logo após criar o app.
4. Em handlers SQS, combinar `@app.on_sqs_message` com `@trace_sqs_message()`.

**Exemplo mínimo:**

```python
from chalice import Chalice
from otel_observability.chalice import instrument_chalice, trace_sqs_message
from otel_observability import get_logger

app = Chalice(app_name="myapp")
instrument_chalice(app)

logger = get_logger(__name__)


@app.route("/ping")
def ping():
    logger.info("ping")
    return {"pong": True}


@app.on_sqs_message(queue_name="my-queue")
@trace_sqs_message()
def process_message(event):
    logger.info("processing sqs", extra={"message_id": event.get("messageId")})
```

Detalhes em [USAGE.md](./USAGE.md).

### 4.4 Métricas de negócio com DogStatsD

**Objetivo:** acompanhar funis e KPIs de negócio (ex.: checkout, aprovação de
pagamento) usando DogStatsD.

**Pré-requisito:** Datadog Agent ou Lambda Extension aceitando DogStatsD em
`localhost:8125`.

**Exemplo mínimo:**

```python
from otel_observability.metrics import increment_counter, set_gauge


def iniciar_checkout(user_id: str):
    increment_counter("checkout.start", tags=["step:initiated"])


def finalizar_checkout(user_id: str, sucesso: bool):
    tag_status = "success" if sucesso else "failed"
    increment_counter("checkout.completed", tags=[f"status:{tag_status}"])


def atualizar_usuarios_ativos(qtd: int):
    set_gauge("users.active", qtd)
```

Conceitos e práticas em [METRICS.md](./METRICS.md).

---

## 5. Boas Práticas de Implementação

### 5.1 Traces

- Nomear spans de forma descritiva (ex.: `process_payment`, `GET /orders`).
- Evitar spans extremamente curtos e com altíssima cardinalidade de atributos.
- Usar o decorator `@trace()` para operações críticas de negócio.

### 5.2 Logs

- Habilitar logs JSON em produção.
- Incluir apenas dados necessários e não sensíveis.
- Usar `set_log_context()` para contexto compartilhado em uma requisição.

### 5.3 Métricas

- Usar tags com baixa cardinalidade (`region`, `env`, `status`).
- Evitar tags como `user_id`, `session_id` em métricas; prefira logs.
- Padronizar nomes de métricas com prefixo de serviço.

### 5.4 Configuração

- Manter variáveis de ambiente versionadas em infraestrutura (IaC).
- Usar `OTEL_TRACES_SAMPLER_ARG` < 1.0 em serviços de alta carga.

---

## 6. Solução de Problemas Frequentes

### 6.1 Traces não aparecem

- Validar `OTEL_EXPORTER_OTLP_ENDPOINT` (sem `/v1/traces`).
- Confirmar se o Datadog Agent ou Lambda Extension está ativo.
- Ativar export para console para debug:

```bash
export OTEL_CONSOLE_EXPORT=true
export OTEL_LOG_LEVEL=DEBUG
```

### 6.2 Contexto não propaga entre serviços

- Verificar se o produtor está usando os helpers de propagação:

```python
from otel_observability.propagation import (
    inject_context_into_sqs_message_attributes,
    inject_context_into_sns_message_attributes,
    inject_context_into_eventbridge_detail,
)
```

- Verificar se o consumidor usa `@instrument_lambda_handler()` ou
`trace_sqs_message()` no caso de Chalice.

### 6.3 Métricas não aparecem no Datadog

- Verificar se DogStatsD está habilitado e acessível em `localhost:8125`.
- Checar se as tags não têm cardinalidade excessiva.

### 6.4 Performance

- Ajustar sampling em serviços de alta taxa de requisições.
- Minimizar criação de spans manuais desnecessários.

---

## 7. Integração com Projetos Existentes

### 7.1 Passos para adoção gradual

1. Habilitar tracing e logging em um único serviço crítico.
2. Propagar contexto para os serviços diretamente dependentes.
3. Adicionar métricas de negócio para o fluxo principal (ex.: checkout).
4. Expandir para demais serviços à medida que a equipe ganha confiança.

### 7.2 Pontos críticos para Chalice + SQS

- Garantir que `instrument_chalice(app)` seja chamado logo após criar o app.
- Garantir a ordem correta dos decorators `@app.on_sqs_message` e
  `@trace_sqs_message()`.
- Configurar corretamente variáveis de ambiente na definição da Lambda
  gerada pelo Chalice.

---

## 8. Navegação Recomendada para a IA

Quando um agente de IA for auxiliar na implementação, a navegação sugerida é:

1. Ler este guia para entender o fluxo de adoção.
2. Consultar [INSTALLATION.md](./INSTALLATION.md) para detalhes de instalação.
3. Consultar [CONFIGURATION.md](./CONFIGURATION.md) para variáveis de ambiente.
4. Consultar [USAGE.md](./USAGE.md) para exemplos de FastAPI, Lambda e Chalice.
5. Consultar [METRICS.md](./METRICS.md) para desenhar métricas de negócio.
6. Consultar [DATADOG.md](./DATADOG.md) para troubleshooting no Datadog.
