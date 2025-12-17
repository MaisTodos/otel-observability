# 🧪 Plano de Testes - otel-observability

Guia completo para testar a biblioteca `otel-observability` em projetos FastAPI e AWS Lambda.

---

## 📋 Pré-requisitos

### Gerais

- ✅ Python 3.9+
- ✅ Conta Datadog (gratuita para testes)
- ✅ API Key do Datadog

### Para FastAPI

- ✅ FastAPI instalado
- ✅ Uvicorn ou similar (ASGI server)
- ✅ Datadog Agent (opcional para testes locais)

### Para Lambda

- ✅ Conta AWS
- ✅ AWS CLI configurado
- ✅ Serverless Framework ou SAM CLI (opcional)
- ✅ Datadog Extension Layer (para Lambda)

---

## 🎯 Teste 1: FastAPI Local

### Objetivo
Testar instrumentação FastAPI e visualizar traces no Datadog.

### Passo a Passo

#### 1. Instalar Dependências

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instalar biblioteca com extras FastAPI
pip install "otel-observability[fastapi]"
# ou com Poetry
poetry add otel-observability[fastapi]

# Instalar FastAPI e servidor
pip install fastapi uvicorn httpx
```

#### 2. Configurar Variáveis de Ambiente

```bash
export OTEL_SERVICE_NAME=fastapi-test
export OTEL_ENVIRONMENT=development
export OTEL_SERVICE_VERSION=1.0.0
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export DD_API_KEY=your-datadog-api-key
export DD_SITE=datadoghq.com
export OTEL_CONSOLE_EXPORT=true  # Para ver traces no console
export OTEL_LOG_LEVEL=DEBUG
```

#### 3. Criar Aplicação de Teste

Crie `test_fastapi.py`:

```python
from fastapi import FastAPI
from otel_observability.fastapi import instrument_fastapi, add_span_attribute
from otel_observability import get_logger, trace
import httpx

app = FastAPI()

# Instrumentar ANTES de definir rotas
instrument_fastapi(app)

logger = get_logger(__name__)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Hello World"}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    logger.info("Fetching user", extra={"user_id": user_id})
    add_span_attribute("user.id", user_id)

    # Chamada HTTP externa (automaticamente rastreada!)
    async with httpx.AsyncClient() as client:
        response = await client.get("https://jsonplaceholder.typicode.com/posts/1")

    return {
        "user_id": user_id,
        "external_data": response.json()
    }

@trace("process_payment")
async def process_payment(amount: float):
    logger.info("Processing payment", extra={"amount": amount})
    return {"status": "success", "amount": amount}

@app.post("/payments")
async def create_payment(amount: float):
    result = await process_payment(amount)
    return result
```

#### 4. Rodar Aplicação

```bash
uvicorn test_fastapi:app --reload --port 8000
```

#### 5. Fazer Requisições de Teste

```bash
# Teste 1: Endpoint raiz
curl http://localhost:8000/

# Teste 2: Endpoint com parâmetro
curl http://localhost:8000/users/123

# Teste 3: Endpoint POST
curl -X POST http://localhost:8000/payments -H "Content-Type: application/json" -d '{"amount": 99.99}'
```

#### 6. Verificar Traces

**Opção A: Console (se `OTEL_CONSOLE_EXPORT=true`)**
- Verificar o terminal onde a aplicação está rodando
- Spans são impressos em formato JSON

**Opção B: Datadog (se Datadog Agent estiver rodando)**
1. Acessar https://app.datadoghq.com/apm/traces
2. Filtrar por `service:fastapi-test`
3. Verificar traces com spans de cada requisição

#### 7. Verificar Logs Correlacionados

Os logs no console incluem `trace_id` e `span_id`:

```
2024-01-15 10:30:45 [INFO] [trace_id=abc123... span_id=def456...] __main__: Fetching user
```

---

## 🎯 Teste 2: FastAPI com Datadog Agent Local

### Objetivo
Testar integração completa com Datadog Agent local.

### Passo a Passo

#### 1. Instalar Datadog Agent

```bash
# Docker
docker run -d \
  --name datadog-agent \
  -e DD_API_KEY=your-datadog-api-key \
  -e DD_SITE=datadoghq.com \
  -e DD_OTLP_CONFIG_RECEIVER_PROTOCOLS_HTTP_ENDPOINT=0.0.0.0:4318 \
  -e DD_LOGS_ENABLED=true \
  -p 4318:4318 \
  gcr.io/datadoghq/agent:latest
```

#### 2. Configurar Variáveis de Ambiente

```bash
export OTEL_SERVICE_NAME=fastapi-test
export OTEL_ENVIRONMENT=development
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_CONSOLE_EXPORT=false  # Desabilitar console, usar Datadog
```

#### 3. Rodar Aplicação

```bash
uvicorn test_fastapi:app --reload
```

#### 4. Fazer Requisições

```bash
curl http://localhost:8000/users/123
```

#### 5. Verificar no Datadog

1. Acessar https://app.datadoghq.com/apm/traces
2. Aguardar 1-2 minutos (tempo de flush)
3. Filtrar por `service:fastapi-test`
4. Verificar traces completos com todos os spans

---

## 🎯 Teste 3: AWS Lambda Local (SAM)

### Objetivo
Testar Lambda handler localmente antes de deploy.

### Passo a Passo

#### 1. Instalar SAM CLI

```bash
# macOS
brew install aws-sam-cli

# Linux
pip install aws-sam-cli

# Windows
# Baixar do site da AWS
```

#### 2. Criar Estrutura do Projeto

```
lambda-test/
├── app.py
├── template.yaml
└── requirements.txt
```

#### 3. Criar `app.py`

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability import get_logger, trace
import json

logger = get_logger(__name__)

@instrument_lambda_handler()
def lambda_handler(event, context):
    logger.info("Lambda handler invoked", extra={"event": event})

    # Processar evento
    result = process_event(event)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result)
    }

@trace("process_event")
def process_event(event):
    logger.debug("Processing event", extra={"event_type": event.get("type")})

    # Simular processamento
    return {
        "message": "Event processed successfully",
        "event": event
    }
```

#### 4. Criar `template.yaml`

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  TestFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: app.lambda_handler
      Runtime: python3.9
      CodeUri: .
      Environment:
        Variables:
          OTEL_SERVICE_NAME: lambda-test
          OTEL_ENVIRONMENT: development
          OTEL_EXPORTER_OTLP_ENDPOINT: http://localhost:4318
          OTEL_CONSOLE_EXPORT: "true"
      Events:
        ApiEvent:
          Type: Api
          Properties:
            Path: /test
            Method: get
```

#### 5. Criar `requirements.txt`

```
otel-observability[lambda]
```

#### 6. Testar Localmente

```bash
# Build
sam build

# Invocar localmente
sam local invoke TestFunction --event event.json

# Ou com API Gateway local
sam local start-api
```

#### 7. Criar `event.json` para Teste

```json
{
  "httpMethod": "GET",
  "path": "/test",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": null
}
```

---

## 🎯 Teste 4: AWS Lambda Deploy (Serverless Framework)

### Objetivo
Fazer deploy real de Lambda e testar integração com Datadog.

### Passo a Passo

#### 1. Instalar Serverless Framework

```bash
npm install -g serverless
```

#### 2. Configurar AWS Credentials

```bash
aws configure
```

#### 3. Criar `serverless.yml`

```yaml
service: otel-test

provider:
  name: aws
  runtime: python3.9
  region: us-east-1
  environment:
    OTEL_SERVICE_NAME: ${self:service}
    OTEL_ENVIRONMENT: production
    DD_API_KEY: ${env:DD_API_KEY}
    DD_SITE: datadoghq.com
    OTEL_EXPORTER_OTLP_ENDPOINT: http://localhost:4318

functions:
  test:
    handler: app.lambda_handler
    layers:
      - arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Extension:XX
      - arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Python:XX
    events:
      - http:
          path: test
          method: get

plugins:
  - serverless-python-requirements

custom:
  pythonRequirements:
    dockerizePip: non-linux
```

#### 4. Criar `app.py`

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability import get_logger
import json

logger = get_logger(__name__)

@instrument_lambda_handler()
def lambda_handler(event, context):
    logger.info("Lambda invoked", extra={
        "request_id": context.aws_request_id,
        "function_name": context.function_name
    })

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "message": "Hello from Lambda!",
            "service": "otel-test"
        })
    }
```

#### 5. Deploy

```bash
# Instalar plugin
serverless plugin install -n serverless-python-requirements

# Deploy
export DD_API_KEY=your-datadog-api-key
serverless deploy
```

#### 6. Testar

```bash
# Invocar função
serverless invoke -f test

# Ou via API Gateway (se configurado)
curl https://your-api-id.execute-api.us-east-1.amazonaws.com/dev/test
```

#### 7. Verificar no Datadog

1. Acessar https://app.datadoghq.com/apm/traces
2. Filtrar por `service:otel-test`
3. Verificar traces da Lambda

---

## 🎯 Teste 5: Tracing Distribuído (Lambda → SQS → Lambda)

### Objetivo
Testar propagação de trace context entre Lambdas via SQS.

### Passo a Passo

#### 1. Criar Lambda Produtora

```python
# producer.py
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability.propagation import inject_context_into_sqs_message_attributes
from otel_observability import get_logger
import boto3
import json

logger = get_logger(__name__)
sqs = boto3.client('sqs')

@instrument_lambda_handler()
def lambda_handler(event, context):
    logger.info("Producer Lambda invoked")

    # Enviar mensagem para SQS com trace context
    queue_url = os.getenv('QUEUE_URL')

    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"order_id": 123, "amount": 99.99}),
        MessageAttributes=inject_context_into_sqs_message_attributes()
    )

    logger.info("Message sent to SQS")

    return {"statusCode": 200, "body": "Message sent"}
```

#### 2. Criar Lambda Consumidora

```python
# consumer.py
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability import get_logger
import json

logger = get_logger(__name__)

@instrument_lambda_handler()
def lambda_handler(event, context):
    logger.info("Consumer Lambda invoked")

    # Trace context é extraído automaticamente dos messageAttributes
    for record in event['Records']:
        message = json.loads(record['body'])
        logger.info("Processing message", extra=message)

        # Processar mensagem...
        process_order(message)

    return {"statusCode": 200}

def process_order(order):
    logger.info("Processing order", extra=order)
    # Lógica de processamento...
```

#### 3. Configurar SQS Trigger

```yaml
# serverless.yml
functions:
  producer:
    handler: producer.lambda_handler
    environment:
      QUEUE_URL: ${self:custom.queueUrl}

  consumer:
    handler: consumer.lambda_handler
    events:
      - sqs:
          arn: ${self:custom.queueArn}
          batchSize: 1
```

#### 4. Testar

1. Invocar Lambda produtora
2. Verificar mensagem na fila SQS
3. Lambda consumidora será invocada automaticamente
4. Verificar no Datadog que ambos os spans estão no mesmo trace

---

## ✅ Checklist de Validação

### FastAPI

- [ ] Traces aparecem no Datadog
- [ ] Logs têm `trace_id` e `span_id`
- [ ] Chamadas HTTP externas são rastreadas
- [ ] Spans customizados funcionam (`@trace`)
- [ ] Atributos customizados aparecem nos spans
- [ ] Service Map mostra dependências

### Lambda

- [ ] Traces aparecem no Datadog
- [ ] Trace context é extraído de eventos
- [ ] Chamadas boto3 são rastreadas
- [ ] Tracing distribuído funciona (SQS/SNS/EventBridge)
- [ ] Logs têm `trace_id` e `span_id`
- [ ] Service Map mostra Lambdas conectadas

---

## 🐛 Troubleshooting

### Traces não aparecem

1. Verificar `OTEL_EXPORTER_OTLP_ENDPOINT`
2. Verificar Datadog Agent/Extension está rodando
3. Ativar `OTEL_CONSOLE_EXPORT=true` para debug
4. Verificar logs de erro

### Trace context não propaga

1. Verificar injeção de contexto (helpers de propagação)
2. Verificar extração automática está funcionando
3. Ativar `OTEL_LOG_LEVEL=DEBUG`

### Performance

- Reduzir `OTEL_TRACES_SAMPLER_ARG` se muitos traces
- Verificar overhead de instrumentação

---

## Próximos Passos

1. Testar em ambiente de desenvolvimento
2. Validar traces no Datadog
3. Testar tracing distribuído
4. Implementar em projeto piloto
5. Expandir para produção

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Conceitos](./CONCEPTS.md) - Conceitos de OpenTelemetry
- [Guia de Uso](./USAGE.md) - Exemplos práticos
- [Configuração](./CONFIGURATION.md) - Configuração de variáveis de ambiente
- [Datadog](./DATADOG.md) - Observabilidade e troubleshooting
