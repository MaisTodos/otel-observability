# Guia Completo de Uso

Este documento fornece exemplos detalhados de como usar a biblioteca com FastAPI e AWS Lambda.

## FastAPI - Uso Avançado

```python
from fastapi import FastAPI
from otel_observability.fastapi import instrument_fastapi, add_span_attribute, add_span_event
from otel_observability import get_logger, trace
import httpx

app = FastAPI()

# Instrumentar com configurações customizadas
instrument_fastapi(
    app,
    json_logs=True,  # Logs em formato JSON
    excluded_urls="/health|/metrics",  # Excluir health checks
    auto_instrument_libs=True  # Auto-instrumenta httpx, requests, etc.
)

logger = get_logger(__name__)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # Adicionar atributos customizados ao span
    add_span_attribute("user.id", user_id)
    add_span_attribute("user.premium", True)

    # Adicionar evento ao span
    add_span_event("user.fetch_started")

    # Chamada HTTP externa automaticamente rastreada
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.example.com/users/{user_id}")

    add_span_event("user.fetch_completed")

    return response.json()

@trace("process_payment", attributes={"operation.type": "payment"})
async def process_payment(user_id: int, amount: float):
    logger.info("Processing payment", extra={
        "user_id": user_id,
        "amount": amount
    })

    # Lógica de pagamento...
    return {"status": "success", "transaction_id": "txn_123"}
```

## Lambda - Diferentes Triggers

### API Gateway

```python
from otel_observability.aws_lambda import instrument_lambda_handler

@instrument_lambda_handler()
def api_handler(event, context):
    # Trace context extraído automaticamente dos headers HTTP
    return {
        "statusCode": 200,
        "body": "Hello from Lambda!"
    }
```

### SQS

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability.propagation import inject_context_into_sqs_message_attributes
import boto3
import json

@instrument_lambda_handler()
def sqs_handler(event, context):
    # Trace context extraído automaticamente dos messageAttributes
    for record in event['Records']:
        message = json.loads(record['body'])
        process_message(message)

    return {"statusCode": 200}

# Exemplo: Enviar mensagem para SQS com trace context
def send_to_sqs(queue_url, data):
    sqs = boto3.client('sqs')
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(data),
        MessageAttributes=inject_context_into_sqs_message_attributes()
    )
```

### SNS

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability.propagation import inject_context_into_sns_message_attributes
import boto3
import json

@instrument_lambda_handler()
def sns_handler(event, context):
    # Trace context extraído automaticamente dos MessageAttributes
    for record in event['Records']:
        sns_message = record['Sns']
        message = json.loads(sns_message['Message'])
        process_notification(message)

    return {"statusCode": 200}

# Exemplo: Publicar no SNS com trace context
def publish_to_sns(topic_arn, data):
    sns = boto3.client('sns')
    sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(data),
        MessageAttributes=inject_context_into_sns_message_attributes()
    )
```

### EventBridge

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability.propagation import inject_context_into_eventbridge_detail
import boto3
import json

@instrument_lambda_handler()
def eventbridge_handler(event, context):
    # Trace context extraído automaticamente do detail
    detail = event.get('detail', {})
    process_event(detail)

    return {"statusCode": 200}

# Exemplo: Enviar evento EventBridge com trace context
def send_event(source, detail_type, detail):
    events = boto3.client('events')
    detail_with_context = inject_context_into_eventbridge_detail(detail)

    events.put_events(
        Entries=[{
            'Source': source,
            'DetailType': detail_type,
            'Detail': json.dumps(detail_with_context)
        }]
    )
```

## Chalice - HTTP e SQS

### HTTP (Rotas)

O Chalice é instrumentado automaticamente via middleware HTTP. Todas as rotas HTTP são rastreadas automaticamente.

```python
from chalice import Chalice
from otel_observability.chalice import instrument_chalice
from otel_observability import get_logger, trace

app = Chalice(app_name='myapp')

# Instrumentar ANTES de definir rotas
instrument_chalice(app)

logger = get_logger(__name__)

@app.route('/users/{user_id}')
def get_user(user_id: int):
    logger.info("Fetching user", extra={"user_id": user_id})
    return {"user_id": user_id}

@app.route('/users', methods=['POST'])
def create_user():
    logger.info("Creating user")
    return {"status": "created"}

@trace("process_payment")
def process_payment(amount: float):
    logger.info("Processing payment", extra={"amount": amount})
    return {"status": "success"}
```

### SQS (Mensagens)

Para eventos SQS, use o decorator `trace_sqs_message()` junto com `@app.on_sqs_message()`:

```python
from chalice import Chalice
from otel_observability.chalice import instrument_chalice, trace_sqs_message
from otel_observability import get_logger

app = Chalice(app_name='myapp')
instrument_chalice(app)

logger = get_logger(__name__)

@app.on_sqs_message(queue_name='my-queue')
@trace_sqs_message()
def process_sqs_message(event):
    # event contém a mensagem SQS
    message_id = event.get('messageId')
    body = event.get('body', '')

    logger.info("Processing SQS message", extra={
        "message_id": message_id,
        "body_length": len(body)
    })

    # Processar mensagem
    # ...

    return {"status": "processed"}
```

**Nota importante**: O decorator `trace_sqs_message()` deve ser usado **depois** de `@app.on_sqs_message()` (decorators são aplicados de baixo para cima).

### Comparação: Chalice vs Lambda Pura

| Aspecto | Chalice | Lambda Pura |
|---------|---------|-------------|
| **HTTP** | `instrument_chalice(app)` - middleware automático | `@instrument_lambda_handler()` - decorator no handler |
| **SQS** | `@trace_sqs_message()` junto com `@app.on_sqs_message()` | `@instrument_lambda_handler()` - extração automática |
| **Ciclo de vida** | Gerenciado pelo Chalice (não faz shutdown) | Shutdown após cada invocação |
| **Uso recomendado** | Aplicações serverless com Chalice | Handlers Lambda diretos sem frameworks |

**Quando usar cada um:**
- **Chalice**: Se você está usando o framework Chalice para sua aplicação
- **Lambda Pura**: Se você tem handlers Lambda diretos sem frameworks

## Exemplos Completos

Veja exemplos detalhados em:
- [`examples/fastapi_example.py`](../examples/fastapi_example.py) - FastAPI com múltiplos casos de uso
- [`examples/lambda_example.py`](../examples/lambda_example.py) - Lambda com diferentes triggers
- [`examples/distributed_tracing_example.py`](../examples/distributed_tracing_example.py) - Tracing distribuído completo

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Conceitos](./CONCEPTS.md) - Entenda propagação de contexto
- [Auto-Instrumentação](./AUTO_INSTRUMENTATION.md) - Bibliotecas suportadas
- [Logging](./LOGGING.md) - Sistema de logging estruturado
- [Configuração](./CONFIGURATION.md) - Configuração de variáveis de ambiente
