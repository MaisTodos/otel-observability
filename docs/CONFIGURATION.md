# Configuração

Este documento explica como configurar a biblioteca através de variáveis de ambiente e diferentes cenários de deployment.

## Variáveis de Ambiente

### Obrigatórias

```bash
OTEL_SERVICE_NAME=my-service        # Nome do serviço
OTEL_ENVIRONMENT=production         # Ambiente (dev, staging, prod)
DD_API_KEY=your-datadog-api-key     # Autenticação — injetado automaticamente como DD-API-KEY
```

### Endpoints por sinal (signal-specific)

A biblioteca usa endpoints separados por sinal de telemetria. A resolução segue a ordem:
`OTEL_EXPORTER_OTLP_{SIGNAL}_ENDPOINT` → `OTEL_EXPORTER_OTLP_ENDPOINT` → `None` (desabilitado)

```bash
# Logs — GA, disponível agora
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=<endpoint>

# Traces — Preview no Datadog, requer aprovação do CSM
# OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=<endpoint-fornecido-pelo-datadog>

# Fallback genérico (opcional) — usado por todos os sinais sem endpoint específico
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### Opcionais

```bash
OTEL_SERVICE_VERSION=1.0.0          # Versão do serviço (default: 0.0.0)
OTEL_TRACES_SAMPLER_ARG=1.0         # Taxa de sampling, 0.0 a 1.0 (default: 1.0); aplicada a spans raiz — decisão do pai é respeitada (ParentBased)
OTEL_TRACES_ENABLED=true            # Forçar desabilitar traces (default: true se endpoint disponível)
OTEL_LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
OTEL_CONSOLE_EXPORT=false           # Exportar spans para console (debug local)
```

### Desnecessárias

| Variável | Por quê não usar |
|---|---|
| `DD_SITE` | Injetada como `DD-SITE` header, mas o Datadog não usa esse header no OTLP. O site é definido pela URL do endpoint |
| `DD_DOGSTATSD_ENABLED/HOST/PORT` | DogStatsD requer Agent local na porta 8125 — indisponível em App Runner |
| `OTEL_EXPORTER_OTLP_HEADERS` | Redundante se `DD_API_KEY` já está configurado — a lib injeta `DD-API-KEY` automaticamente |

---

## Cenários de Deployment

### 1. AWS App Runner — Envio Direto ao Datadog (recomendado)

App Runner não suporta sidecars. O envio direto é o único modelo viável sem infraestrutura adicional.

```bash
OTEL_SERVICE_NAME=my-app-runner-service
OTEL_ENVIRONMENT=prod
OTEL_SERVICE_VERSION=1.0.0
DD_API_KEY=your-datadog-api-key
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=<endpoint-logs-datadog>
# OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=<aguarda-csm>
```

> Veja [APP_RUNNER.md](./APP_RUNNER.md) para detalhes e status do endpoint de traces.

### 2. AWS Lambda com Datadog Extension

A Extension escuta em `localhost:4318` dentro do Lambda e repassa os dados ao Datadog.

```bash
OTEL_SERVICE_NAME=my-lambda
OTEL_ENVIRONMENT=production
DD_API_KEY=your-api-key
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### 3. Container com Datadog Agent (ECS Fargate, Docker Compose)

O Agent roda como sidecar e recebe OTLP na porta 4318.

```bash
OTEL_SERVICE_NAME=my-service
OTEL_ENVIRONMENT=production
DD_API_KEY=your-api-key
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318   # Agent no mesmo namespace de rede
```

---

## Navegação

- [README](../README.md) - Visão geral e quick start
- [APP_RUNNER.md](./APP_RUNNER.md) - Configuração específica para AWS App Runner
- [CHANGELOG.md](./CHANGELOG.md) - Histórico de mudanças e roadmap
- [Arquitetura](./ARCHITECTURE.md) - Entenda o fluxo de dados
- [Datadog](./DATADOG.md) - Observabilidade e troubleshooting

## Referências Externas

- [OpenTelemetry OTLP Exporter Spec](https://opentelemetry.io/docs/specs/otel/protocol/exporter/) - Comportamento de endpoint resolution
- [Datadog OTLP Ingest](https://docs.datadoghq.com/opentelemetry/setup/otlp_ingest/) - Documentação oficial
