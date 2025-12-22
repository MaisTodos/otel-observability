# Configuração

Este documento explica como configurar a biblioteca através de variáveis de ambiente e diferentes cenários de deployment.

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

## OTEL_EXPORTER_OTLP_ENDPOINT - Valores por Cenário

### 1. AWS Lambda com Datadog Extension

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

A Datadog Extension Layer escuta em `localhost:4318` dentro do Lambda e gerencia o envio para o Datadog Cloud.

**Exemplo serverless.yml:**

```yaml
# serverless.yml
functions:
  my-function:
    handler: app.handler
    layers:
      - arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Extension:XX
      - arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Python:XX
    environment:
      OTEL_SERVICE_NAME: my-lambda
      OTEL_ENVIRONMENT: production
      DD_API_KEY: ${DD_API_KEY}
      DD_SITE: datadoghq.com
      # Extension escuta em localhost:4318
      OTEL_EXPORTER_OTLP_ENDPOINT: http://localhost:4318
```

A Datadog Extension Layer gerencia o envio de traces para o Datadog. Configure o endpoint como `localhost:4318`.

### 2. FastAPI/Container com Datadog Agent

```bash
# Datadog Agent no mesmo container/rede
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# Datadog Agent em container separado (Docker Compose)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://datadog-agent:4318
```

O Datadog Agent escuta na porta `4318` para receber traces via OTLP e envia para o Datadog Cloud.

**Exemplo docker-compose.yml:**

```yaml
# docker-compose.yml
services:
  app:
    build: .
    environment:
      OTEL_SERVICE_NAME: fastapi-api
      OTEL_ENVIRONMENT: production
      DD_API_KEY: ${DD_API_KEY}
      DD_SITE: datadoghq.com
      # Agent escuta em datadog-agent:4318 (mesma rede Docker)
      OTEL_EXPORTER_OTLP_ENDPOINT: http://datadog-agent:4318
    depends_on:
      - datadog-agent

  datadog-agent:
    image: gcr.io/datadoghq/agent:latest
    environment:
      DD_API_KEY: ${DD_API_KEY}
      DD_SITE: datadoghq.com
      # Habilitar OTLP receiver na porta 4318
      DD_OTLP_CONFIG_RECEIVER_PROTOCOLS_HTTP_ENDPOINT: 0.0.0.0:4318
      DD_LOGS_ENABLED: true
    ports:
      - "4318:4318"  # Expor porta para acesso externo (opcional)
```

O Datadog Agent recebe traces via OTLP e envia para o Datadog. Use `datadog-agent:4318` quando em containers separados, ou `localhost:4318` se o Agent estiver no mesmo container.

### 3. Envio Direto para Datadog Intake

```bash
# US1 (datadoghq.com)
export OTEL_EXPORTER_OTLP_ENDPOINT=https://trace-intake.datadoghq.com

# EU (datadoghq.eu)
export OTEL_EXPORTER_OTLP_ENDPOINT=https://trace-intake.datadoghq.eu

# US3 (us3.datadoghq.com)
export OTEL_EXPORTER_OTLP_ENDPOINT=https://trace-intake.us3.datadoghq.com
```

**Nota:** Envio direto para Datadog sem passar pelo Agent. Não recomendado para produção devido à falta de buffer e retry automático.

**Importante:**
- Não inclua `/v1/traces` no endpoint - o exporter adiciona automaticamente
- Use `http://` para localhost e `https://` para Datadog Intake
- Para produção, prefira Agent/Extension (opções 1 e 2)

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Arquitetura](./ARCHITECTURE.md) - Entenda o fluxo de dados
- [Datadog](./DATADOG.md) - Observabilidade e troubleshooting
- [Instalação](./INSTALLATION.md) - Como instalar a biblioteca

## Referências Externas

- [Datadog Docs](https://docs.datadoghq.com/tracing/) - Documentação oficial
