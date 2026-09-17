# Configuração

Referência única de variáveis de ambiente. Toda variável listada aqui é lida de `os.environ` pelo código em `src/otel_observability/` — se não está nesta lista, a lib não lê.

## Endpoints: como a lib resolve

Resolução por sinal, em `config.py::_resolve_signal_endpoint`:

| Env | Comportamento |
|---|---|
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` / `_LOGS_ENDPOINT` / `_METRICS_ENDPOINT` | Vai **verbatim** ao exporter — precisa do path completo (ex.: `.../v1/traces`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | É **base**: a lib completa o path do sinal (`/v1/traces`, `/v1/logs`, `/v1/metrics`) |

Precedência: específico > genérico > `None` (sinal desligado).

Sem endpoint de traces (nenhuma das duas setada), a lib emite no startup o warning `No OTLP traces endpoint configured` e não cria o exporter — a aplicação funciona normalmente e a correlação de logs via `trace_id` continua, porque o `TracerProvider` existe de qualquer forma. **Não existe detecção automática de ambiente que preencha endpoint**: sem env, não sai telemetria.

## Referência de variáveis

### Identidade do serviço

| Variável | Default | O que faz | Obrigatória? |
|---|---|---|---|
| `OTEL_SERVICE_NAME` | `unknown-service` (com warning no startup) | Nome do serviço; vira a tag `service` | Sim |
| `OTEL_ENVIRONMENT` | `development` | Ambiente; vira a tag `env` | Sim |
| `OTEL_SERVICE_VERSION` | `0.0.0` | Versão; vira a tag `version` | Recomendada |

### Export OTLP

| Variável | Default | O que faz | Obrigatória? |
|---|---|---|---|
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | — | Endpoint de logs, com path completo. Ativa o export OTLP de logs (além do stdout) | Não — sem ela, logs saem só no stdout |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | — | Endpoint de traces, com path completo | Não — sem ela, traces ficam desligados |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Base comum: a lib completa o path por sinal. Use as específicas OU esta | Não |
| `OTEL_EXPORTER_OTLP_HEADERS` | — | Headers extras, formato `chave1=valor1,chave2=valor2` | Não |
| `OTEL_EXPORTER_OTLP_TIMEOUT` | `3` | Timeout do export em segundos. É o cap do retry interno do exporter — protege o flush de Lambda contra backend fora do ar | Não |
| `OTEL_TRACES_ENABLED` | `true` | `false` desliga o exporter de traces explicitamente | Não |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Taxa de amostragem de spans raiz (0.0 a 1.0, fora da faixa levanta `ValueError`). Envolto em `ParentBased`: a decisão do chamador é respeitada | Não |
| `OTEL_CONSOLE_EXPORT` | `false` | Imprime spans no console (debug local) | Não |
| `DD_API_KEY` | — | Vira o header `dd-api-key` automaticamente | Sim no intake direto ao Datadog |
| `DD_SITE` | — | Vira o header `dd-site` — que o Datadog **não usa** no intake OTLP. Não configure; o site é definido pela URL do endpoint | Não |

### Logs

| Variável | Default | O que faz | Obrigatória? |
|---|---|---|---|
| `OTEL_LOG_LEVEL` | `INFO` | Nível do logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | Não |
| `OTEL_LOG_FORMAT` | — | `json` (case-insensitive) liga logs JSON | Sim em produção |

### Métricas (DogStatsD)

| Variável | Default | O que faz | Obrigatória? |
|---|---|---|---|
| `DD_DOGSTATSD_ENABLED` | `true` | Liga o cliente DogStatsD | Não |
| `DD_DOGSTATSD_HOST` | `localhost` | Host do Agent/Extension | Não |
| `DD_DOGSTATSD_PORT` | `8125` | Porta UDP do Agent/Extension | Não |

O envio de métricas exige o extra `metrics` (pacote `datadog`) **e** um Agent/Extension escutando em `host:porta`. UDP não reporta erro: sem o Agent, as métricas somem em silêncio. Ver `docs/ENTRYPOINTS.md`.

### Lidas em runtime AWS

| Variável | Uso |
|---|---|
| `AWS_LAMBDA_FUNCTION_NAME` | Presença marca `is_lambda=True` (resource ganha `runtime=lambda`) |
| `AWS_REGION` | Vira atributo `cloud.region` no span do handler Lambda |

## Formato de log: precedência

Definida em `config.py::resolve_json_logs`:

1. Parâmetro explícito `json_logs=` no entrypoint (vence sempre)
2. `OTEL_LOG_FORMAT=json`
3. Default do entrypoint: `False` no `instrument_fastapi`, `True` em Lambda e Chalice

Produção deve ter `OTEL_LOG_FORMAT=json`: sem JSON, o Datadog não facetiza por atributo e a busca vira texto corrido.

## Campos de config mortos

Dois campos do dataclass `TelemetryConfig` são preenchidos no `from_env()` e **não são lidos por módulo nenhum** (confirmado por grep em `src/`):

- `otlp_endpoint` — o exporter de traces usa `otlp_traces_endpoint`; o de logs, `otlp_logs_endpoint`. O campo genérico fica para trás.
- `otlp_metrics_endpoint` — não existe export de métricas via OTLP. A env `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` é lida e armazenada, mas nenhum módulo consome o valor: **configurá-la hoje não faz nada**.

Métricas hoje são DogStatsD exclusivamente. O caminho OTLP de métricas é roadmap — ver `docs/CHANGELOG.md`.

## Cenários por plataforma

| Plataforma | Traces | Logs | Métricas | Auth |
|---|---|---|---|---|
| App Runner | OTLP direto — endpoint região-específico do Datadog (Preview, fornecido via CSM) | OTLP direto — `https://otlp.datadoghq.com/v1/logs` | — (não há Agent) | `DD_API_KEY` |
| Lambda | idem App Runner | idem App Runner | — | idem |
| ECS + Agent sidecar | `http://localhost:4318/v1/traces` | ver nota 1 | DogStatsD `localhost:8125` | do Agent |
| EKS + Agent | idem ECS se sidecar; se Agent em DaemonSet, aponte pro nó: `http://$(DD_AGENT_HOST):4318/v1/traces` | ver nota 1 | idem ECS, com a ressalva da nota 2 | do Agent |

**Nota 1 — ECS/EKS com FireLens:** se o stdout já chega no Datadog via FireLens, **não** configure `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`. Cada log seria ingerido duas vezes (OTLP + FireLens), duplicando ingestão e conta.

**Nota 2 — EKS com Agent como DaemonSet:** o default `DD_DOGSTATSD_HOST=localhost` fica **errado** — aponta pro próprio pod, não pro nó onde roda o Agent. UDP não levanta erro, então as métricas somem em silêncio. Configure `DD_DOGSTATSD_HOST` com o IP do nó (o mesmo valor que o DaemonSet injeta em `DD_AGENT_HOST`). A lib não lê `DD_AGENT_HOST` — ele existe para você referenciar nos valores de endpoint/host.

## Intake OTLP do Datadog

| Sinal | Endpoint | Status |
|---|---|---|
| Logs | `https://otlp.datadoghq.com/v1/logs` | GA |
| Métricas | `https://otlp.datadoghq.com/v1/metrics` | GA no Datadog; a lib ainda não exporta métricas via OTLP |
| Traces | Endpoint região-específico, fornecido pelo CSM junto do valor do header `dd-otlp-source` | Preview |

Autenticação no intake direto: `DD_API_KEY`. Quando o CSM liberar traces, o header `dd-otlp-source` fornecido entra em `OTEL_EXPORTER_OTLP_HEADERS` — nenhuma mudança de código.

## Navegação

- [README](../README.md) — visão geral e quick start
- [USAGE](./USAGE.md) — a API que os serviços chamam
- [ENTRYPOINTS](./ENTRYPOINTS.md) — Lambda e Chalice
- [TROUBLESHOOTING](./TROUBLESHOOTING.md) — diagnóstico por sintoma
- [CHANGELOG](./CHANGELOG.md) — histórico e roadmap
