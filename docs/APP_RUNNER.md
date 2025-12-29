# AWS App Runner com Padrão Sidecar

Este documento explica como usar a biblioteca `otel-observability` com AWS App Runner usando o padrão Sidecar para telemetria.

---

## O que é o Padrão Sidecar?

O **padrão Sidecar** é um padrão arquitetural onde um container auxiliar (sidecar) é executado junto com o container principal da aplicação. No contexto de observabilidade, o Datadog Agent roda como sidecar para coletar métricas, traces e logs.

## Por que usar Sidecar no App Runner?

AWS App Runner abstrai a infraestrutura subjacente, impedindo a instalação de um Agente Datadog a nível de host (como em EC2). Para obter telemetria detalhada, você precisa:

1. **Métricas customizadas (DogStatsD)**: Requer um agente local para receber métricas via `localhost:8125`
2. **Traces detalhados**: O agente processa e envia traces via OTLP
3. **Logs estruturados**: O agente coleta logs do stdout/stderr

O padrão Sidecar resolve isso executando o Datadog Agent em um container separado que compartilha o mesmo namespace de rede com a aplicação.

---

## Arquitetura

```
┌─────────────────────────────────────┐
│     App Runner Service              │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │  Aplicação   │  │ Datadog     │ │
│  │  (Python)    │  │ Agent       │ │
│  │              │  │ (Sidecar)   │ │
│  │  localhost:  │  │             │ │
│  │  8125 (UDP)  │─>│ localhost:  │ │
│  │  4318 (HTTP) │─>│ 8125, 4318  │ │
│  └──────────────┘  └─────────────┘ │
│       │                    │         │
│       └────────┬───────────┘         │
│                │                     │
│                ▼                     │
│         Datadog Cloud                │
└─────────────────────────────────────┘
```

A aplicação e o Agent compartilham o mesmo namespace de rede, permitindo comunicação via `localhost`.

---

## Configuração

### Opção 1: App Runner Service (apprunner.yaml)

Crie um arquivo `apprunner.yaml` na raiz do seu projeto:

```yaml
version: 1.0
build:
  commands:
    build:
      - echo "No build commands needed"
run:
  runtime: python3
  command: uvicorn app:app --host 0.0.0.0 --port 8000
  network:
    port: 8000
    env: PORT
  env:
    - name: OTEL_SERVICE_NAME
      value: my-app-runner-service
    - name: OTEL_ENVIRONMENT
      value: production
    - name: OTEL_SERVICE_VERSION
      value: 1.0.0
    - name: DD_DOGSTATSD_ENABLED
      value: "true"
    - name: DD_DOGSTATSD_HOST
      value: localhost
    - name: DD_DOGSTATSD_PORT
      value: "8125"
    - name: OTEL_EXPORTER_OTLP_ENDPOINT
      value: http://localhost:4318
```

**⚠️ Nota:** App Runner não suporta nativamente múltiplos containers. Para usar o padrão Sidecar, você precisa usar a **Opção 2** (Dockerfile com docker-compose ou ECS).

### Opção 2: Docker Compose (Desenvolvimento Local)

Para desenvolvimento local, use `docker-compose.yml`:

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OTEL_SERVICE_NAME=my-app
      - OTEL_ENVIRONMENT=development
      - OTEL_SERVICE_VERSION=1.0.0
      - DD_DOGSTATSD_ENABLED=true
      - DD_DOGSTATSD_HOST=localhost
      - DD_DOGSTATSD_PORT=8125
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
    depends_on:
      - datadog-agent
    networks:
      - app-network

  datadog-agent:
    image: gcr.io/datadoghq/agent:7
    environment:
      - DD_API_KEY=${DD_API_KEY}
      - DD_SITE=datadoghq.com
      - DD_APM_ENABLED=true
      - DD_LOGS_ENABLED=true
      - DD_DOGSTATSD_NON_LOCAL_TRAFFIC=false
      - DD_APM_NON_LOCAL_TRAFFIC=false
    ports:
      - "8125:8125/udp"  # DogStatsD
      - "4318:4318"      # OTLP
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

**Executar:**
```bash
docker-compose up
```

### Opção 3: ECS Task Definition (Produção)

Para produção no AWS, use ECS com Task Definition:

```json
{
  "family": "my-app-with-datadog",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "app",
      "image": "your-ecr-repo/my-app:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "OTEL_SERVICE_NAME",
          "value": "my-app"
        },
        {
          "name": "OTEL_ENVIRONMENT",
          "value": "production"
        },
        {
          "name": "OTEL_SERVICE_VERSION",
          "value": "1.0.0"
        },
        {
          "name": "DD_DOGSTATSD_ENABLED",
          "value": "true"
        },
        {
          "name": "DD_DOGSTATSD_HOST",
          "value": "localhost"
        },
        {
          "name": "DD_DOGSTATSD_PORT",
          "value": "8125"
        },
        {
          "name": "OTEL_EXPORTER_OTLP_ENDPOINT",
          "value": "http://localhost:4318"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/my-app",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    },
    {
      "name": "datadog-agent",
      "image": "public.ecr.aws/datadog/agent:7",
      "essential": true,
      "environment": [
        {
          "name": "DD_API_KEY",
          "value": "your-api-key"
        },
        {
          "name": "DD_SITE",
          "value": "datadoghq.com"
        },
        {
          "name": "DD_APM_ENABLED",
          "value": "true"
        },
        {
          "name": "DD_LOGS_ENABLED",
          "value": "true"
        },
        {
          "name": "DD_DOGSTATSD_NON_LOCAL_TRAFFIC",
          "value": "false"
        },
        {
          "name": "DD_APM_NON_LOCAL_TRAFFIC",
          "value": "false"
        }
      ]
    }
  ]
}
```

---

## Configuração do Datadog Agent

### Variáveis de Ambiente do Agent

```bash
DD_API_KEY=your-api-key          # Obrigatório
DD_SITE=datadoghq.com            # datadoghq.com ou datadoghq.eu
DD_APM_ENABLED=true              # Habilitar APM (traces)
DD_LOGS_ENABLED=true             # Habilitar coleta de logs
DD_DOGSTATSD_NON_LOCAL_TRAFFIC=false  # Aceitar apenas localhost
DD_APM_NON_LOCAL_TRAFFIC=false        # Aceitar apenas localhost
```

### Portas do Agent

- **8125/udp**: DogStatsD (métricas customizadas)
- **4318/tcp**: OTLP (traces e métricas OpenTelemetry)

---

## Envio de Métricas para localhost:8125

A biblioteca `otel-observability` envia métricas automaticamente para `localhost:8125` quando configurada:

```python
from otel_observability.metrics import increment_counter

# Métrica será enviada para localhost:8125
increment_counter("app.requests", tags=["region:us-east-1"])
```

**Configuração:**
```bash
export DD_DOGSTATSD_ENABLED=true
export DD_DOGSTATSD_HOST=localhost
export DD_DOGSTATSD_PORT=8125
```

---

## Envio de Traces para localhost:4318

A biblioteca envia traces via OTLP para `localhost:4318`:

```python
from otel_observability.fastapi import instrument_fastapi
from fastapi import FastAPI

app = FastAPI()
instrument_fastapi(app)  # Traces enviados para localhost:4318
```

**Configuração:**
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

---

## Considerações de Dimensionamento

### Recursos Compartilhados

⚠️ **Importante:** O Agent sidecar consome recursos da instância App Runner/ECS:

- **Memória:** ~512MB adicionais
- **CPU:** ~0.1-0.2 vCPU adicionais

**Recomendação:**
- Aumente a memória total da instância em ~512MB
- Aumente a CPU se necessário (depende do volume de métricas)

### Exemplo de Dimensionamento

**App Runner:**
- CPU: 1 vCPU → 1.2 vCPU (recomendado)
- Memória: 2 GB → 2.5 GB (recomendado)

**ECS Fargate:**
- CPU: 512 → 1024 (para acomodar Agent)
- Memória: 1024 → 1536 (para acomodar Agent)

---

## Troubleshooting

### Métricas não aparecem

1. **Verificar se Agent está rodando:**
   ```bash
   docker ps | grep datadog
   # Ou no ECS: verificar logs do container datadog-agent
   ```

2. **Verificar conectividade:**
   ```bash
   # Do container da aplicação
   nc -u localhost 8125
   ```

3. **Verificar logs do Agent:**
   ```bash
   docker logs <datadog-agent-container-id>
   ```

### Traces não aparecem

1. **Verificar endpoint OTLP:**
   ```bash
   echo $OTEL_EXPORTER_OTLP_ENDPOINT
   # Deve ser: http://localhost:4318
   ```

2. **Verificar se Agent está escutando:**
   ```bash
   curl http://localhost:4318/v1/traces
   ```

### Logs não aparecem

1. **Verificar se DD_LOGS_ENABLED=true no Agent**
2. **Verificar se logs estão sendo enviados para stdout/stderr**
3. **Verificar configuração de logs no Agent**

---

## Exemplo Completo

Veja `examples/app_runner_example.py` para um exemplo completo de aplicação FastAPI configurada para App Runner com sidecar.

---

## Navegação

- [README](../README.md) - Visão geral
- [Configuração](./CONFIGURATION.md) - Configuração detalhada
- [Métricas](./METRICS.md) - Guia de métricas customizadas
- [Datadog](./DATADOG.md) - Observabilidade no Datadog
