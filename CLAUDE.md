# CLAUDE.md — otel-observability

Leia também o `CLAUDE.md` na raiz do workspace (`../CLAUDE.md`) para contexto de infraestrutura e estratégia Datadog.

---

## O que é

Lib interna OpenTelemetry wrapper, compartilhada por todos os serviços da stack. Abstrai a inicialização do OTel e fornece integração direta com Datadog via OTLP.

Objetivo: qualquer serviço novo configura observabilidade completa (logs, traces, métricas) apenas com variáveis de ambiente.

---

## Arquitetura de envio ao Datadog

**OTLP direto** — sem Datadog Agent, sem OTel Collector intermediário. Ver `../CLAUDE.md` para o raciocínio arquitetural (App Runner não suporta sidecars).

---

## Pontos críticos de design

### `configure_logging()` limpa handlers existentes

`configure_logging()` faz `logger.handlers.clear()` no root logger antes de adicionar o handler do otel. Isso é intencional para evitar duplicação, mas **qualquer código que adicione handlers ao root logger após `instrument_fastapi()` vai criar duplicação**.

Consumidores da lib não devem adicionar handlers ao root logger manualmente.

### `init_otlp_log_export()` é condicional

O `OTLPLogExporter` só é registrado se `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` estiver definido. Sem essa env, logs só vão para stdout.

### `json_logs=False` por padrão em `instrument_fastapi()`

O formato JSON só é ativado se o chamador passar `json_logs=True`. Em `banking.back-office`, isso é controlado por `OTEL_LOG_FORMAT=json`. Produção deve sempre ter essa env configurada.

### `get_logger(name)` retorna `logging.getLogger(name)`

Não há lógica extra — a correlação de traces acontece via `TraceContextFilter` no handler, não no logger em si. Qualquer logger do Python que passe pelo root handler vai ter `trace_id`/`span_id` injetados automaticamente.

---

## Extras disponíveis

```
otel-observability[fastapi]    # FastAPI instrumentation
otel-observability[database]   # SQLAlchemy, Psycopg2, PyMongo
otel-observability[http]       # httpx, requests
otel-observability[redis]      # Redis
otel-observability[metrics]    # DogStatsD
otel-observability[lambda]     # AWS Lambda
otel-observability[all]        # Tudo
```

---

## Status dos sinais OTLP direto ao Datadog

| Sinal   | Status hoje (2026-03-17)                        |
|---------|-------------------------------------------------|
| Logs    | ✅ GA — `https://otlp.datadoghq.com/v1/logs`   |
| Métricas| ✅ GA — `https://otlp.datadoghq.com/v1/metrics`|
| Traces  | ⏳ Preview — aguarda aprovação do CSM           |
