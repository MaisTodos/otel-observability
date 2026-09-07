# Troubleshooting

Três fluxos, por sintoma. Cada um: sintoma → causas prováveis (em ordem) → como confirmar.

## 1. Trace não aparece no Datadog

**Sintoma:** spans não chegam no APM (ou warning no startup).

**Causas prováveis, em ordem:**

1. **Nenhuma env de endpoint configurada.** A lib não detecta Lambda nem preenche endpoint sozinha — sem env, o exporter não é criado e **não sai trace nenhum** (é o caso que falha em silêncio). Correção: `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` — base, a lib completa com `/v1/traces`; ou `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` com path completo.
2. **Endpoint específico (por sinal) sem path.** Endpoint declarado em `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` vai verbatim ao exporter — o SDK **não** completa path de endpoint específico, e o POST vai para a raiz. Só a env **genérica** é tratada como base.
3. `OTEL_TRACES_ENABLED=false` no ambiente.
4. **Amostragem.** `OTEL_TRACES_SAMPLER_ARG` < 1.0 amostra spans raiz; com `ParentBased`, a decisão do chamador é respeitada — se o serviço de borda amostrou o trace fora, nada downstream grava span.
5. **Lambda/Chalice: telemetria some a partir da 2ª invocação.** Alguém chamou `shutdown_telemetry` por invocação — isso mata o `BatchSpanProcessor` em container warm. O padrão da lib é `flush_telemetry` por invocação (ver [ENTRYPOINTS](./ENTRYPOINTS.md)).

**Como confirmar:**

- Procure no startup o warning `No OTLP traces endpoint configured` — presente = causa 1.
- `OTEL_CONSOLE_EXPORT=true` imprime os spans no console: separa "o app não gera span" de "o export não chega ao backend".
- Com Agent local: `curl -X POST http://localhost:4318/v1/traces` responde do receiver (a lib faz POST nesse path quando a env genérica é a base).

## 2. Log não aparece (ou aparece sem estrutura)

**Sintoma:** log chega no Datadog como texto corrido, sem facetar por atributo; ou não chega.

**Causas prováveis, em ordem:**

1. **`OTEL_LOG_FORMAT` não setada com entrypoint FastAPI.** O default do `instrument_fastapi` é **não**-JSON — logs textuais não facetam no Datadog. Correção: `OTEL_LOG_FORMAT=json` (Lambda/Chalice já são JSON por default; a env padroniza todos).
2. **Sem `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`.** O export OTLP de logs é opt-in: sem a env, logs saem só no stdout. Se você usa FireLens/Forwarder, isso é o esperado — configure a env só quando não haveria outro caminho de ingestão (e cuidado com duplicação, ver [CONFIGURATION](./CONFIGURATION.md) nota 1).
3. **Handler do root logger reconfigurado depois de instrumentar.** `configure_logging` faz `handlers.clear()` no root; a ordem dos entrypoints (logs antes da telemetria) é a certa, mas código que adiciona handler ao root **depois** de `instrument_*` remove o handler OTLP recém-instalado. Consumidores não devem adicionar handlers ao root logger.
4. Log abaixo do nível: `OTEL_LOG_LEVEL` (default `INFO`).

**Como confirmar:**

- Linha no stdout em JSON com `trace_id`, `span_id`, `env`, `service`, `version` — formato e correlação corretos.
- `OTEL_LOG_LEVEL=DEBUG` mostra `OTLP log exporter initialized: endpoint=...` quando o export OTLP está ligado.
- Contexto e `extra` aparecem como atributos no JSON; dicts aninhados viram notação de ponto e `None` é descartado (ver [USAGE](./USAGE.md) §1).

## 3. Contexto de trace não propaga entre serviços

**Sintoma:** trace quebrado no Datadog — o span do consumidor abre trace novo, sem pai.

**Causa mais provável:** **produtor não-instrumentado no SQS** — a mensagem sai sem `traceparent`. O consumidor só extrai quando o carrier tem `traceparent` ou `baggage`; carrier com atributo de negócio apenas **não** dispara extract (evita abrir span órfão que perderia o pai de verdade).

**Correções, por lado:**

- **Produtor boto3:** com `auto_instrument_libs=True` (default nos três entrypoints) a lib instrumenta boto3/botocore e injeta o contexto no envio. Sem auto-instrumentação, injete manual: `inject_context_into_sqs_message_attributes()` (ou as variantes SNS/EventBridge/Lambda payload de `otel_observability.propagation`).
- **Consumidor Lambda:** `@instrument_lambda_handler()` extrai automaticamente de SQS/SNS/EventBridge/API Gateway.
- **Consumidor Chalice:** `@trace_sqs_message` (decorator nu) sobre o handler SQS.
- **HTTP entre serviços:** httpx/requests instrumentados propagam o header `traceparent` sozinhos — se a chamada é manual, use `inject_context_into_http_headers()`.

**Como confirmar:**

- `OTEL_LOG_LEVEL=DEBUG`: procure `Extracted context from SQS` versus `No trace context found in SQS message - starting new trace`.
- Inspecione a mensagem na fila: existe o atributo `traceparent` em `messageAttributes`? Ausente = produtor sem instrumentação (a causa nº 1).
- Round-trip de ponta a ponta do mecanismo, executável, está em [USAGE](./USAGE.md) §7.

## Navegação

- [CONFIGURATION](./CONFIGURATION.md) — env vars e precedência de endpoints
- [ENTRYPOINTS](./ENTRYPOINTS.md) — ciclo de vida de Lambda/Chalice
- [USAGE](./USAGE.md) — API e exemplos executados
