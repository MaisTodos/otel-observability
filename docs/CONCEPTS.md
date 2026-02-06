# Conceitos de OpenTelemetry

Este documento explica os conceitos fundamentais de OpenTelemetry e como a biblioteca implementa propagação de contexto distribuído.

## O que é OpenTelemetry?

**OpenTelemetry (OTel)** é o padrão CNCF para observabilidade cloud-native. Ele unifica:

1. **Traces** - Rastreamento de requisições através de múltiplos serviços
2. **Metrics** - Medições numéricas (latência, throughput, etc.)
3. **Logs** - Eventos estruturados correlacionados com traces

## Conceitos Principais

### Trace

Uma árvore de **spans** representando uma operação completa:

```
Trace: Processar Pedido (trace_id: abc123)
├─ Span: POST /orders [200ms]
   ├─ Span: validate_order [10ms]
   ├─ Span: check_inventory [50ms]
   │  └─ Span: query_database [40ms]
   ├─ Span: process_payment [100ms]
   │  └─ Span: call_payment_gateway [90ms]
   └─ Span: send_notification [30ms]
```

Todos os spans compartilham o mesmo **trace_id**, permitindo rastrear a requisição end-to-end.

### Span

Unidade básica de trabalho com:
- **Nome** - Operação realizada (`GET /users`, `process_payment`)
- **Timestamps** - Início e fim
- **Atributos** - Metadados (`http.status_code`, `user.id`)
- **Eventos** - Pontos no tempo (`cache.hit`, `validation.failed`)
- **Status** - `OK`, `ERROR`
- **Parent Span ID** - Para formar hierarquia

## Context Propagation (Propagação de Contexto)

**CRÍTICO para tracing distribuído!**

Quando um serviço chama outro, o **trace context** precisa ser **propagado**:

```
┌─────────────┐     HTTP Headers      ┌─────────────┐
│  Service A  │ ──────────────────────>│  Service B  │
│ trace_id: X │   traceparent: 00-X... │ trace_id: X │
│ span_id: Y  │                        │ span_id: Z  │
└─────────────┘                        └─────────────┘
                                        Parent: Y
```

**Formato W3C Trace Context:** `traceparent: 00-{trace_id}-{span_id}-{flags}`

## Propagação de Contexto no Projeto

A biblioteca implementa propagação de contexto distribuído automaticamente:

### 1. Configuração Global (tracer.py)

```python
# Propagators configurados globalmente
propagators = [
    TraceContextTextMapPropagator(),  # W3C Trace Context
    W3CBaggagePropagator(),           # W3C Baggage
]
set_global_textmap(CompositeHTTPPropagator(propagators))
```

### 2. FastAPI - Propagação Automática

```python
instrument_fastapi(app)

# Requisições HTTP INCOMING: Contexto extraído automaticamente dos headers
# Requisições HTTP OUTGOING: Contexto propagado automaticamente (httpx/requests)
```

**Exemplo:**
```python
# Serviço A chama Serviço B
async with httpx.AsyncClient() as client:
    # traceparent é adicionado automaticamente nos headers
    response = await client.get("https://service-b.com/api")
```

### 3. Lambda - Extração Automática

```python
@instrument_lambda_handler()
def lambda_handler(event, context):
    # Contexto extraído automaticamente de:
    #    - API Gateway headers
    #    - SQS messageAttributes
    #    - SNS MessageAttributes
    #    - EventBridge detail
    pass
```

### 4. Lambda - Injeção Manual

```python
# Ao enviar mensagem para SQS, use helpers de propagação
from otel_observability.propagation import inject_context_into_sqs_message_attributes

sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=json.dumps(data),
    MessageAttributes=inject_context_into_sqs_message_attributes()  # Injeta traceparent
)
```

### 5. Auto-Instrumentação

```python
# Bibliotecas instrumentadas propagam contexto automaticamente:
# - httpx: Propaga em chamadas HTTP
# - requests: Propaga em chamadas HTTP
# - boto3: Propaga em chamadas AWS (quando configurado)
```

## Resumo: Propagação Automática vs Manual

| Cenário | Propagação | Implementação |
|---------|------------|---------------|
| **FastAPI → HTTP (httpx/requests)** | Automática | Via auto-instrumentação |
| **Lambda recebe de API Gateway** | Automática | Via `@instrument_lambda_handler()` |
| **Lambda recebe de SQS/SNS/EventBridge** | Automática | Via `@instrument_lambda_handler()` |
| **Lambda envia para SQS/SNS/EventBridge** | Manual | Use helpers de `propagation.py` |
| **Lambda → Lambda (invoke)** | Manual | Use helpers de `propagation.py` |

## Exemplo Completo de Tracing Distribuído

```python
# Serviço A (FastAPI)
@app.get("/orders")
async def create_order():
    # Span 1: POST /orders (trace_id: abc123, span_id: 001)

    # Chamada HTTP com propagação automática
    async with httpx.AsyncClient() as client:
        # traceparent injetado automaticamente
        response = await client.post("https://payment-service.com/pay")
        # Span 2: POST payment-service.com (trace_id: abc123, span_id: 002, parent: 001)

    # Enviar para SQS com injeção manual de contexto
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"order_id": 123}),
        MessageAttributes=inject_context_into_sqs_message_attributes()
    )

# Serviço B (Lambda - SQS)
@instrument_lambda_handler()
def process_payment(event, context):
    # Extrai traceparent automaticamente dos messageAttributes
    # Span 3: process_payment (trace_id: abc123, span_id: 003, parent: 001)
    pass
```

**Resultado:** Um trace completo com 3 spans correlacionados no Datadog.

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Guia de Implementação](./IMPLEMENTATION_GUIDE.md) - Aplique estes conceitos em serviços reais
- [Arquitetura](./ARCHITECTURE.md) - Como funciona o fluxo de dados
- [Guia de Uso](./USAGE.md) - Exemplos práticos de uso
- [Auto-Instrumentação](./AUTO_INSTRUMENTATION.md) - Bibliotecas suportadas

## Referências Externas

- [OpenTelemetry Docs](https://opentelemetry.io/docs/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
