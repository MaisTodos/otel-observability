# AWS App Runner

Este documento explica como usar a biblioteca `otel-observability` com AWS App Runner e o modelo de envio direto ao Datadog.

---

## Limitação do App Runner

**App Runner não suporta sidecars.** Cada serviço roda um único container, o que inviabiliza o Datadog Agent no modelo tradicional (sidecar na porta 4318/8125).

Isso significa que as seguintes abordagens **não funcionam** no App Runner:
- Datadog Agent como sidecar
- DogStatsD via `localhost:8125`
- OTLP para `localhost:4318`

---

## Solução: Envio Direto ao Datadog (OTLP Intake)

O Datadog oferece endpoints OTLP nativos que recebem dados diretamente, sem necessidade de Agent.

```
App Runner A ──┐
App Runner B ──┼──► Datadog (OTLP direto)
App Runner C ──┘
```

### Status por sinal

| Sinal | Endpoint | Status | Ação necessária |
|---|---|---|---|
| Logs | `https://otlp.datadoghq.com/v1/logs` | GA | Disponível agora |
| Métricas | `https://otlp.datadoghq.com/v1/metrics` | GA — Phase 2 da lib | Aguarda implementação |
| Traces | Endpoint região-específico | Preview — requer CSM | Solicitar acesso ao Datadog |

---

## Fase 1 — Configuração atual (logs funcionando)

### Variáveis de ambiente no App Runner

```bash
OTEL_SERVICE_NAME=banking-back-office
OTEL_ENVIRONMENT=prod
OTEL_SERVICE_VERSION=1.0.0
DD_API_KEY=<sua_api_key>
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://otlp.datadoghq.com/v1/logs

# Traces: comentado até aprovação do CSM
# OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=<endpoint-fornecido-pelo-datadog>
```

A lib injeta `DD-API-KEY` automaticamente via `DD_API_KEY` — não é necessário configurar `OTEL_EXPORTER_OTLP_HEADERS` manualmente.

### O que funciona na Fase 1

- Logs estruturados com `trace_id` e `span_id` correlacionados
- Auto-instrumentação de FastAPI (request/response)
- Propagação de contexto W3C (entre serviços)
- Spans criados em memória (trace context disponível para correlação de logs, mas não exportados)

### O que não funciona ainda

- Traces não são exportados (sem endpoint aprovado)
- Métricas OTLP não exportadas (Phase 2)
- DogStatsD não funciona sem Agent

---

## Fase 2 — Roadmap

### Traces (bloqueado pelo Datadog)

O endpoint de traces OTLP direto está em **Preview** e requer aprovação do Customer Success Manager do Datadog.

**Ação:** Solicitar acesso ao CSM com a seguinte justificativa:
- Stack em AWS App Runner (sem suporte a sidecars)
- Lib compartilhada entre múltiplos serviços
- 2 dos 3 sinais já funcionando via OTLP direto

Quando aprovado, apenas adicionar a env:
```bash
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=<endpoint-fornecido-pelo-datadog>
```
Nenhuma mudança de código necessária — a lib já suporta a variável.

**Headers adicionais requeridos pelo Datadog (após aprovação):**
- `dd-api-key`: já injetado automaticamente pela lib
- `dd-otlp-source`: fornecido pelo Datadog junto com o endpoint

```bash
OTEL_EXPORTER_OTLP_HEADERS=dd-otlp-source=<source-id-fornecido>
```

### Métricas OTLP (bloqueado por implementação)

O endpoint `https://otlp.datadoghq.com/v1/metrics` está GA no Datadog, mas a lib ainda usa DogStatsD para métricas. A implementação do `OTLPMetricExporter` foi adiada para a Fase 2.

**Por que foi adiado:** A API de métricas atual (DogStatsD: `increment_counter`, `gauge`, `histogram`) é incompatível com o modelo OTLP (`MeterProvider`, `Counter`, `Histogram`). A migração exige mudanças na API pública da lib e nos call sites dos serviços.

**Dependências para implementar:**
- `opentelemetry-sdk>=1.20.0` — já presente como dependência core
- `OTLPMetricExporter` — já incluído no pacote `opentelemetry-exporter-otlp-proto-http`, sem nova dependência

**O que muda no código (Fase 2):**
- `config.py`: `otlp_metrics_endpoint` já existe, só precisa ser wired
- `metrics.py`: adicionar `MeterProvider` + `OTLPMetricExporter` como caminho paralelo ao DogStatsD
- Env: `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://otlp.datadoghq.com/v1/metrics`

---

## Comparação de Abordagens

| | Agent Centralizado (ECS) | Direto ao Datadog |
|---|---|---|
| App Runner | Possível (latência de rede) | Nativo |
| Infra extra | Sim (ECS service) | Não |
| Ponto de falha | Sim | Não |
| Traces (agora) | Sim | Preview (aguarda CSM) |
| Logs (agora) | Sim | Sim |
| Métricas (agora) | Sim (DogStatsD) | Phase 2 |

---

## Troubleshooting

### Logs não aparecem no Datadog

1. Verificar se `DD_API_KEY` está correto
2. Verificar se `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` está configurado
3. Ativar console export para confirmar que logs estão sendo gerados:
   ```bash
   OTEL_CONSOLE_EXPORT=true
   ```

### Warning "No OTLP traces endpoint configured"

Esperado na Fase 1. A lib emite esse warning quando `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` não está configurado. Traces ficam desabilitados mas a aplicação funciona normalmente — correlação de logs via `trace_id` ainda funciona.

### `DD-SITE` header sendo enviado

Versões anteriores da lib injetavam `DD-SITE` como header. Esse header não é usado pelo Datadog no endpoint OTLP. Se aparecer nos logs, atualize para a versão atual da lib e remova `DD_SITE` das suas variáveis de ambiente.

---

## Navegação

- [README](../README.md) - Visão geral
- [CONFIGURATION.md](./CONFIGURATION.md) - Referência completa de variáveis
- [CHANGELOG.md](./CHANGELOG.md) - Histórico de mudanças e roadmap
- [Datadog](./DATADOG.md) - Observabilidade no Datadog
