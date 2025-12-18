# Configuração

Este documento fornece guias passo a passo completos para configurar a biblioteca em diferentes frameworks e ambientes.

## Índice

- [Guia Completo: Chalice (AWS Lambda)](#guia-completo-chalice-aws-lambda)
- [Guia Completo: FastAPI](#guia-completo-fastapi)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Endpoints OTLP por Cenário](#endpoints-otlp-por-cenário)

---

## Guia Completo: Chalice (AWS Lambda)

### Passo 1: Instalar a Biblioteca

#### Opção A: Poetry

```bash
# No diretório do seu projeto Chalice
poetry add otel-observability[chalice]
```

#### Opção B: UV

```bash
# No diretório do seu projeto Chalice
uv add "otel-observability[chalice]"
```

### Passo 2: Obter ARNs das Datadog Layers

As Datadog Layers são necessárias para enviar traces para o Datadog. Obtenha os ARNs mais recentes:

**Método 1: Via Datadog CLI**

```bash
# Instalar Datadog CLI
npm install -g @datadog/datadog-ci

# Obter ARNs das layers (substitua us-east-1 pela sua região)
datadog-ci lambda layers list --region us-east-1
```

**Método 2: Via Console AWS**

1. Acesse [Datadog Lambda Layers](https://docs.datadoghq.com/serverless/libraries_integrations/lambda_layers/)
2. Selecione sua região (ex: `us-east-1`)
3. Copie os ARNs:
   - **Datadog Extension**: `arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Extension:XX`
   - **Datadog Python**: `arn:aws:lambda:us-east-1:464622532012:layer:Datadog-PythonXX:XX`

**Nota**: O `XX` no final é a versão da layer. Use sempre a versão mais recente.

### Passo 3: Configurar `.chalice/config.json`

Adicione as layers e variáveis de ambiente no arquivo de configuração do Chalice:

```json
{
  "version": "2.0",
  "app_name": "my-chalice-app",
  "stages": {
    "dev": {
      "api_gateway_stage": "api",
      "lambda_memory_size": 512,
      "lambda_timeout": 60,
      "layers": [
        "arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Extension:XX",
        "arn:aws:lambda:us-east-1:464622532012:layer:Datadog-PythonXX:XX"
      ],
      "environment_variables": {
        "OTEL_SERVICE_NAME": "my-chalice-app",
        "OTEL_ENVIRONMENT": "development",
        "OTEL_SERVICE_VERSION": "1.0.0",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
        "DD_API_KEY": "your-datadog-api-key",
        "DD_SITE": "datadoghq.com",
        "OTEL_LOG_LEVEL": "INFO"
      }
    },
    "prod": {
      "api_gateway_stage": "api",
      "lambda_memory_size": 1024,
      "lambda_timeout": 300,
      "layers": [
        "arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Extension:XX",
        "arn:aws:lambda:us-east-1:464622532012:layer:Datadog-PythonXX:XX"
      ],
      "environment_variables": {
        "OTEL_SERVICE_NAME": "my-chalice-app",
        "OTEL_ENVIRONMENT": "production",
        "OTEL_SERVICE_VERSION": "1.0.0",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
        "DD_API_KEY": "${DD_API_KEY}",
        "DD_SITE": "datadoghq.com",
        "OTEL_LOG_LEVEL": "INFO",
        "OTEL_TRACES_SAMPLER_ARG": "0.1"
      }
    }
  }
}
```

**Importante:**
- Substitua `XX` pelos números de versão mais recentes das layers
- Use `${DD_API_KEY}` em produção e configure via AWS Systems Manager Parameter Store ou Secrets Manager
- A Datadog Extension escuta em `localhost:4318` dentro do Lambda

### Passo 4: Instrumentar o Código

No arquivo principal da sua aplicação Chalice (geralmente `app.py`):

```python
from chalice import Chalice
from otel_observability.chalice import instrument_chalice, trace_sqs_message
from otel_observability import get_logger, trace

app = Chalice(app_name='my-chalice-app')

# ⚠️ IMPORTANTE: Instrumentar ANTES de definir rotas
instrument_chalice(app)

logger = get_logger(__name__)

# Rotas HTTP (instrumentadas automaticamente)
@app.route('/users/{user_id}')
def get_user(user_id: int):
    logger.info("Fetching user", extra={"user_id": user_id})
    return {"user_id": user_id, "name": f"User {user_id}"}

@app.route('/users', methods=['POST'])
def create_user():
    logger.info("Creating user")
    return {"status": "created"}

# Eventos SQS (usar decorator auxiliar)
@app.on_sqs_message(queue_name='my-queue')
@trace_sqs_message()
def process_sqs_message(event):
    logger.info("Processing SQS message", extra={
        "message_id": event.get("messageId")
    })
    # Processar mensagem
    return {"status": "processed"}

# Funções auxiliares com tracing customizado
@trace("process_payment")
def process_payment(amount: float):
    logger.info("Processing payment", extra={"amount": amount})
    return {"status": "success"}
```

### Passo 5: Configurar DD_API_KEY em Produção

Para produção, não coloque a API key diretamente no código. Use AWS Systems Manager Parameter Store ou Secrets Manager:

#### Opção A: Systems Manager Parameter Store

```bash
# Criar parâmetro
aws ssm put-parameter \
  --name "/chalice/datadog/api-key" \
  --value "your-datadog-api-key" \
  --type "SecureString"
```

No `config.json`, referencie o parâmetro:

```json
{
  "stages": {
    "prod": {
      "environment_variables": {
        "DD_API_KEY": "${ssm:/chalice/datadog/api-key}"
      }
    }
  }
}
```

#### Opção B: Secrets Manager

```bash
# Criar secret
aws secretsmanager create-secret \
  --name chalice/datadog/api-key \
  --secret-string "your-datadog-api-key"
```

No `config.json`:

```json
{
  "stages": {
    "prod": {
      "environment_variables": {
        "DD_API_KEY": "${secretsmanager:chalice/datadog/api-key:SecretString}"
      }
    }
  }
}
```

### Passo 6: Deploy

```bash
# Deploy para dev
chalice deploy --stage dev

# Deploy para produção
chalice deploy --stage prod
```

### Passo 7: Verificar no Datadog

1. Acesse [Datadog APM](https://app.datadoghq.com/apm/traces)
2. Procure pelo serviço `my-chalice-app`
3. Verifique traces e logs correlacionados

---

## Guia Completo: FastAPI

### Passo 1: Instalar a Biblioteca

#### Opção A: Poetry

```bash
# No diretório do seu projeto FastAPI
poetry add otel-observability[fastapi]
```

#### Opção B: UV

```bash
# No diretório do seu projeto FastAPI
uv add "otel-observability[fastapi]"
```

### Passo 2: Escolher Cenário de Deployment

FastAPI pode ser deployado em diferentes ambientes. Escolha o cenário apropriado:

#### Cenário A: Docker com Datadog Agent

**Recomendado para produção**

#### Cenário B: Kubernetes com Datadog Agent

**Recomendado para produção em K8s**

#### Cenário C: Envio Direto para Datadog

**Apenas para desenvolvimento/testes**

### Passo 3: Configurar Variáveis de Ambiente

#### Para Docker Compose (Cenário A)

Crie um arquivo `.env`:

```bash
# .env
OTEL_SERVICE_NAME=fastapi-api
OTEL_ENVIRONMENT=production
OTEL_SERVICE_VERSION=1.0.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://datadog-agent:4318
DD_API_KEY=your-datadog-api-key
DD_SITE=datadoghq.com
OTEL_LOG_LEVEL=INFO
```

#### Para Kubernetes (Cenário B)

Crie um `ConfigMap` e `Secret`:

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-config
data:
  OTEL_SERVICE_NAME: "fastapi-api"
  OTEL_ENVIRONMENT: "production"
  OTEL_SERVICE_VERSION: "1.0.0"
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://datadog-agent.datadog.svc.cluster.local:4318"
  DD_SITE: "datadoghq.com"
  OTEL_LOG_LEVEL: "INFO"
---
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: datadog-secret
type: Opaque
stringData:
  DD_API_KEY: "your-datadog-api-key"
```

### Passo 4: Configurar Docker Compose (Cenário A)

Crie `docker-compose.yml`:

```yaml
version: '3.8'

services:
  app:
    build: .
    environment:
      - OTEL_SERVICE_NAME=${OTEL_SERVICE_NAME}
      - OTEL_ENVIRONMENT=${OTEL_ENVIRONMENT}
      - OTEL_SERVICE_VERSION=${OTEL_SERVICE_VERSION}
      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT}
      - DD_API_KEY=${DD_API_KEY}
      - DD_SITE=${DD_SITE}
      - OTEL_LOG_LEVEL=${OTEL_LOG_LEVEL}
    ports:
      - "8000:8000"
    depends_on:
      - datadog-agent
    networks:
      - app-network

  datadog-agent:
    image: gcr.io/datadoghq/agent:latest
    environment:
      - DD_API_KEY=${DD_API_KEY}
      - DD_SITE=${DD_SITE}
      - DD_OTLP_CONFIG_RECEIVER_PROTOCOLS_HTTP_ENDPOINT=0.0.0.0:4318
      - DD_LOGS_ENABLED=true
      - DD_APM_ENABLED=true
    ports:
      - "4318:4318"  # OTLP HTTP
      - "8126:8126"  # APM (opcional, para outros formatos)
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /proc/:/host/proc/:ro
      - /sys/fs/cgroup/:/host/sys/fs/cgroup:ro
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

### Passo 5: Configurar Dockerfile

Crie `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar Poetry ou UV
RUN pip install poetry

# Copiar arquivos de dependências
COPY pyproject.toml poetry.lock ./

# Instalar dependências
RUN poetry config virtualenvs.create false && \
    poetry install --no-dev --no-interaction --no-root

# Copiar código da aplicação
COPY . .

# Expor porta
EXPOSE 8000

# Comando para iniciar
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Passo 6: Instrumentar o Código

No arquivo principal da sua aplicação FastAPI (geralmente `main.py`):

```python
from fastapi import FastAPI
from otel_observability.fastapi import instrument_fastapi, add_span_attribute, add_span_event
from otel_observability import get_logger, trace
import httpx

app = FastAPI(title="My FastAPI App")

# ⚠️ IMPORTANTE: Instrumentar ANTES de definir rotas
instrument_fastapi(
    app,
    json_logs=True,  # Logs em formato JSON (recomendado)
    excluded_urls="/health|/metrics",  # Excluir health checks do tracing
    auto_instrument_libs=True  # Auto-instrumentar httpx, requests, etc.
)

logger = get_logger(__name__)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # Adicionar atributos customizados ao span
    add_span_attribute("user.id", user_id)

    logger.info("Fetching user", extra={"user_id": user_id})

    # Adicionar evento ao span
    add_span_event("user.fetch_started")

    # Chamada HTTP externa (automaticamente rastreada)
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.example.com/users/{user_id}")

    add_span_event("user.fetch_completed")

    return response.json()

@app.post("/users")
async def create_user(user_data: dict):
    logger.info("Creating user", extra=user_data)
    return {"status": "created"}

# Funções auxiliares com tracing customizado
@trace("process_payment", attributes={"operation.type": "payment"})
async def process_payment(user_id: int, amount: float):
    logger.info("Processing payment", extra={
        "user_id": user_id,
        "amount": amount
    })
    return {"status": "success", "transaction_id": "txn_123"}
```

### Passo 7: Configurar Kubernetes (Cenário B)

Crie `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: fastapi-app
  template:
    metadata:
      labels:
        app: fastapi-app
    spec:
      containers:
      - name: app
        image: your-registry/fastapi-app:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: otel-config
        - secretRef:
            name: datadog-secret
        env:
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://datadog-agent.datadog.svc.cluster.local:4318"
---
apiVersion: v1
kind: Service
metadata:
  name: fastapi-app
spec:
  selector:
    app: fastapi-app
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Passo 8: Executar

#### Docker Compose

```bash
# Carregar variáveis de ambiente
export $(cat .env | xargs)

# Iniciar serviços
docker-compose up -d

# Ver logs
docker-compose logs -f app
```

#### Kubernetes

```bash
# Aplicar configurações
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml

# Verificar pods
kubectl get pods -l app=fastapi-app

# Ver logs
kubectl logs -f deployment/fastapi-app
```

### Passo 9: Verificar no Datadog

1. Acesse [Datadog APM](https://app.datadoghq.com/apm/traces)
2. Procure pelo serviço `fastapi-api`
3. Verifique traces e logs correlacionados

---

## Variáveis de Ambiente

### Obrigatórias

```bash
# Identificação do serviço
export OTEL_SERVICE_NAME=my-service           # Nome do serviço
export OTEL_ENVIRONMENT=production            # Ambiente (dev, staging, prod)
export OTEL_SERVICE_VERSION=1.0.0             # Versão

# OTLP Exporter - IMPORTANTE: Escolha baseado no seu cenário abaixo!
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318  # SEM /v1/traces!

# Datadog API Key (sempre necessário)
export DD_API_KEY=your-datadog-api-key
export DD_SITE=datadoghq.com                  # ou datadoghq.eu, us3, etc.
```

### Opcionais

```bash
export OTEL_TRACES_SAMPLER_ARG=1.0            # Taxa de sampling (0.0 a 1.0)
export OTEL_LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
export OTEL_CONSOLE_EXPORT=false              # Debug: exportar para console
```

---

## Endpoints OTLP por Cenário

### 1. AWS Lambda com Datadog Extension

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

**Como funciona:**
- A Datadog Extension Layer escuta em `localhost:4318` dentro do Lambda
- A Extension gerencia o envio de traces para o Datadog Cloud
- Não precisa configurar nada além do endpoint

**Aplicável a:**
- Chalice (AWS Lambda)
- Lambda pura (com `instrument_lambda_handler`)

### 2. Container com Datadog Agent

```bash
# Agent no mesmo container/rede
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# Agent em container separado (Docker Compose)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://datadog-agent:4318

# Agent em Kubernetes
export OTEL_EXPORTER_OTLP_ENDPOINT=http://datadog-agent.datadog.svc.cluster.local:4318
```

**Como funciona:**
- O Datadog Agent escuta na porta `4318` para receber traces via OTLP
- O Agent envia traces para o Datadog Cloud
- Recomendado para produção (buffer, retry automático)

**Aplicável a:**
- FastAPI em Docker
- FastAPI em Kubernetes
- Qualquer aplicação containerizada

### 3. Envio Direto para Datadog Intake

```bash
# US1 (datadoghq.com)
export OTEL_EXPORTER_OTLP_ENDPOINT=https://trace-intake.datadoghq.com

# EU (datadoghq.eu)
export OTEL_EXPORTER_OTLP_ENDPOINT=https://trace-intake.datadoghq.eu

# US3 (us3.datadoghq.com)
export OTEL_EXPORTER_OTLP_ENDPOINT=https://trace-intake.us3.datadoghq.com
```

**Como funciona:**
- Envio direto para Datadog sem passar pelo Agent
- Não recomendado para produção (sem buffer, sem retry automático)

**Aplicável a:**
- Apenas desenvolvimento/testes
- Ambientes onde não é possível usar Agent/Extension

**Importante:**
- Não inclua `/v1/traces` no endpoint - o exporter adiciona automaticamente
- Use `http://` para localhost e `https://` para Datadog Intake
- Para produção, prefira Agent/Extension (opções 1 e 2)

---

## Troubleshooting

### Traces não aparecem no Datadog

1. **Verificar endpoint OTLP:**
   ```bash
   echo $OTEL_EXPORTER_OTLP_ENDPOINT
   # Deve ser http://localhost:4318 (SEM /v1/traces)
   ```

2. **Verificar Datadog Agent/Extension:**
   - Lambda: Verificar se Extension está na layer
   - Container: `curl http://localhost:4318/v1/traces` (deve retornar 200)

3. **Ativar console export para debug:**
   ```bash
   export OTEL_CONSOLE_EXPORT=true
   # Verá spans impressos no console
   ```

### Erro: "Could not connect to OTLP endpoint"

- Verifique se o Agent/Extension está rodando
- Verifique se a porta `4318` está acessível
- Para Docker: Verifique se containers estão na mesma rede

### Trace context não propaga

1. **Verificar injeção** - Produtor deve usar helpers de propagação
2. **Verificar extração** - Consumidor extrai automaticamente
3. **Logs debug:**
   ```bash
   export OTEL_LOG_LEVEL=DEBUG
   # Verá mensagens como "Extracted context from SQS"
   ```

---

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Arquitetura](./ARCHITECTURE.md) - Entenda o fluxo de dados
- [Datadog](./DATADOG.md) - Observabilidade e troubleshooting
- [Instalação](./INSTALLATION.md) - Como instalar a biblioteca
- [Guia de Uso](./USAGE.md) - Exemplos práticos

## Referências Externas

- [Datadog Docs](https://docs.datadoghq.com/tracing/) - Documentação oficial
- [Chalice Docs](https://aws.github.io/chalice/) - Documentação do Chalice
- [FastAPI Docs](https://fastapi.tiangolo.com/) - Documentação do FastAPI
