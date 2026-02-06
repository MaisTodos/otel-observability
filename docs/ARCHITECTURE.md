# Arquitetura e Fluxo de Dados

Este documento explica a arquitetura do sistema, como os dados fluem da aplicação até o Datadog, e por que usar OpenTelemetry com Datadog.

## Por que usar com Datadog?

1. **Vendor-neutral** - OpenTelemetry permite trocar de backend sem reescrever código
2. **Padrão da indústria** - CNCF, adotado por AWS, Google, Microsoft
3. **Auto-instrumentação** - Instrumenta bibliotecas automaticamente
4. **Datadog suporta OTLP** - Envio direto via OTLP (OpenTelemetry Protocol)
5. **Futuro-proof** - Não fica preso a um vendor específico

## Como Funciona o Fluxo de Dados

### Arquitetura Completa

```
┌─────────────────┐
│  Sua Aplicação  │
│  (FastAPI/      │
│   Lambda)       │
└────────┬─────────┘
         │
         │ 1. OpenTelemetry SDK coleta traces/spans
         │
         ▼
┌─────────────────┐
│  OTLP Exporter  │
│  (otel-         │
│  observability) │
└────────┬─────────┘
         │
         │ 2. Envia via OTLP (HTTP) para endpoint
         │
         ▼
┌─────────────────┐      ┌─────────────────┐
│ Datadog Agent/  │      │  Datadog Intake  │
│ Extension       │ OU   │  (direto)        │
│ (localhost:4318)│      │  (cloud)         │
└────────┬─────────┘      └────────┬─────────┘
         │                         │
         │ 3. Processa e envia     │ 3. Recebe direto
         │                         │
         ▼                         ▼
┌─────────────────────────────────────────┐
│         Datadog Cloud                   │
│  (app.datadoghq.com)                    │
│                                         │
│  - APM (Traces)                         │
│  - Logs                                 │
│  - Metrics                              │
└─────────────────────────────────────────┘
```

### Explicação Detalhada

#### 1. Coleta (Sua Aplicação)
- OpenTelemetry SDK coleta **traces** (não logs diretamente)
- Cada operação cria **spans** (unidades de trabalho)
- Logs são correlacionados com traces via `trace_id` e `span_id`

#### 2. Exportação (OTLP Exporter)
- OTLP Exporter envia traces via **OTLP (OpenTelemetry Protocol)**
- Protocolo HTTP/JSON ou gRPC
- Endpoint configurado em `OTEL_EXPORTER_OTLP_ENDPOINT`

#### 3. Processamento (Datadog Agent/Extension)
- **Datadog Agent** ou **Extension** recebe traces via OTLP
- Processa, enriquece e envia para Datadog Cloud
- Funciona como um **proxy/buffer** local

#### 4. Visualização (Datadog Cloud)
- Traces aparecem no Datadog APM
- Logs correlacionados aparecem junto com traces
- Service Map mostra dependências entre serviços

## Dois Caminhos Possíveis

### Caminho A: Via Agent/Extension (Recomendado)

```
Aplicação → OTLP Exporter → Datadog Agent/Extension → Datadog Cloud
           (localhost:4318)   (processa localmente)    (app.datadoghq.com)
```

**Vantagens:**
- ✅ Buffer local (não perde dados se internet cair)
- ✅ Processamento local (menos carga na aplicação)
- ✅ Batching (envia em lote, mais eficiente)
- ✅ Retry automático

### Caminho B: Direto para Datadog (Não recomendado)

```
Aplicação → OTLP Exporter → Datadog Intake → Datadog Cloud
           (trace-intake.     (recebe direto)  (app.datadoghq.com)
            datadoghq.com)
```

**Desvantagens:**
- ❌ Sem buffer (pode perder dados)
- ❌ Mais carga na aplicação
- ❌ Sem retry automático
- ❌ Requer internet estável

## O que é Enviado?

### Traces (Spans)
- **O que é:** Árvore de operações (requisições, queries, chamadas HTTP)
- **Formato:** OTLP (OpenTelemetry Protocol)
- **Endpoint:** `http://localhost:4318/v1/traces` (adicionado automaticamente)

### Logs
- **O que é:** Eventos textuais com timestamp
- **Formato:** JSON estruturado com `trace_id` e `span_id`
- **Envio:** Via stdout/stderr (capturado pelo Agent/Extension)

### Metrics
- **O que é:** Medições numéricas (latência, throughput)
- **Formato:** OTLP Metrics
- **Endpoint:** `http://localhost:4318/v1/metrics`

## Fluxo de Dados Simplificado

A biblioteca envia traces e logs através do seguinte fluxo:

1. **Traces** (spans) são enviados via OTLP para o endpoint (`localhost:4318`)
2. **Logs** são enviados via stdout/stderr (capturados pelo Agent/Extension)
3. O **Datadog Agent/Extension** recebe ambos e envia para o Datadog Cloud
4. No Datadog, traces e logs aparecem correlacionados (mesmo `trace_id`)

**Fluxo:**
```
Aplicação → OTEL SDK → OTLP Exporter → Datadog Agent → Datadog Cloud
          (coleta)    (envia traces)  (processa)      (visualiza)
```

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Guia de Implementação](./IMPLEMENTATION_GUIDE.md) - Como aplicar este fluxo em serviços
- [Conceitos](./CONCEPTS.md) - Conceitos fundamentais de OpenTelemetry
- [Configuração](./CONFIGURATION.md) - Como configurar endpoints e variáveis de ambiente
- [Datadog](./DATADOG.md) - Observabilidade e troubleshooting no Datadog
