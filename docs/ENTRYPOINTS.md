# Entry points: Lambda e Chalice

Os dois entrypoints serverless da lib. FastAPI está coberto em [USAGE](./USAGE.md).

## Lambda pura — `@instrument_lambda_handler()`

Instalação com o extra `lambda` (propagador AWS X-Ray + instrumentação boto3sqs/botocore):

```bash
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git#egg=otel-observability[lambda]"
```

Decorator **com parênteses** (é uma factory):

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability import get_logger

logger = get_logger(__name__)


@instrument_lambda_handler()
def lambda_handler(event, context):
    logger.info("Processing request")
    return {"statusCode": 200, "body": "OK"}
```

Parâmetros (assinatura real):

| Parâmetro | Default | Efeito |
|---|---|---|
| `config` | `None` | `TelemetryConfig` própria; se `None`, lê do ambiente |
| `configure_logs` | `True` | Chama `configure_logging` (logs primeiro, telemetria depois — ordem que garante que o handler OTLP não seja removido) |
| `json_logs` | `None` | Precedência: parâmetro > `OTEL_LOG_FORMAT` > `True` (default deste entrypoint) |
| `auto_extract_context` | `True` | Extrai trace context do evento (ver abaixo) |
| `auto_instrument_libs` | `True` | Auto-instrumenta boto3 e as demais bibliotecas disponíveis |
| `redact_keys` | `None` | Chaves extras mascaradas por completo (legado) |
| `mask_policy` | `None` | Mapa campo → `Mask`; ver [USAGE](./USAGE.md) §6 |

A inicialização acontece uma única vez, no cold start. Em cada invocação o wrapper:

1. Extrai o contexto do evento quando `auto_extract_context=True` — headers HTTP (API Gateway), `messageAttributes` de SQS, `MessageAttributes` de SNS e `detail` de EventBridge. Sem contexto no evento, abre trace novo.
2. Cria o span `lambda.{function_name}` com atributos `faas.*` e `cloud.*` (incluindo `cloud.region` de `AWS_REGION`) e atributos semânticos por tipo de evento (messaging, db, s3).
3. No `finally`, chama `flush_telemetry(timeout=5)`.

### Ciclo de vida: flush, nunca shutdown

⚠️ O wrapper chama `flush_telemetry` **a cada invocação** e nunca `shutdown_telemetry`. O Lambda reaproveita o container: `shutdown_telemetry` desliga o `BatchSpanProcessor`, e toda a telemetria da 2ª invocação em diante se perde silenciosamente. `flush_telemetry` esvazia o buffer e mantém o provider utilizável. `shutdown_telemetry` só faz sentido no encerramento real do processo.

Em exceção: status `ERROR` no span + `record_exception` + `logger.exception`, e o erro re-raise.

## Chalice — `instrument_chalice(app)`

Instalação com o extra **`chalice`** — **não** `lambda`. O `pyproject.toml` separa os dois: `lambda` traz instrumentação de boto3/X-Ray, `chalice` traz o framework.

```bash
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git#egg=otel-observability[chalice]"
```

```python
from chalice import Chalice
from otel_observability.chalice import instrument_chalice
from otel_observability import get_logger

app = Chalice(app_name="myapp")
instrument_chalice(app)  # ANTES de definir rotas

logger = get_logger(__name__)


@app.route("/users/{user_id}")
def get_user(user_id: int):
    logger.info("Fetching user", extra={"user_id": user_id})
    return {"user_id": user_id}
```

Parâmetros: mesmos de Lambda menos `auto_extract_context` (o middleware extrai dos headers de cada request) e `suppress_access_logs` (não existe no Chalice). `json_logs` tem default `True`.

O que o `instrument_chalice` registra: um middleware HTTP que cria o span `"{method} {path}"` por request com atributos `http.*`, marca health checks (`/health`, `/healthz`, `/readiness`, `/liveness`) e, no `finally`, chama `flush_telemetry(timeout=5)` — mesma regra de ciclo de vida do Lambda: flush por request, nunca shutdown.

### SQS — `@trace_sqs_message`, decorator nu

⚠️ **Sem parênteses.** A assinatura é `trace_sqs_message(func)` — recebe a própria função. Com parênteses, `trace_sqs_message()` levanta `TypeError: missing 1 required positional argument: 'func'`.

```python
from otel_observability.chalice import trace_sqs_message


@app.on_sqs_message(queue_name="my-queue")
@trace_sqs_message
def process_message(event):
    logger.info("processing sqs", extra={"message_id": event.get("messageId")})
```

Ordem dos decorators: `@app.on_sqs_message` em cima, `@trace_sqs_message` embaixo (decorators são aplicados de baixo para cima; o Chalice precisa registrar o resultado já instrumentado). O span `sqs.process` ganha atributos `messaging.*` (id da mensagem, fila extraída do `eventSourceARN`) e o contexto é extraído de `messageAttributes` aceitando os formatos `stringValue` e `Value`.

## Métricas (DogStatsD) — leia o aviso primeiro

⚠️ **O caminho DogStatsD é no-op sem o extra `metrics` — e nenhum serviço da stack o instala hoje.** Sem o pacote `datadog` (que o extra instala), cada chamada loga o warning `datadog library not installed` e retorna sem enviar nada. Com o pacote, ainda é preciso um Datadog Agent ou Lambda Extension escutando em `DD_DOGSTATSD_HOST:DD_DOGSTATSD_PORT` (default `localhost:8125`); UDP não reporta erro — sem o Agent, as métricas somem em silêncio.

A API pública (exige `from otel_observability import ...` ou `otel_observability.metrics`):

| Função | Tipo | Notas |
|---|---|---|
| `increment_counter(metric, value=1.0, tags=None, sample_rate=1.0)` | COUNT | Eventos acumulativos |
| `set_gauge(metric, value, tags=None)` | GAUGE | Valor no ponto no tempo |
| `record_histogram(metric, value, tags=None, sample_rate=1.0)` | HISTOGRAM | Agregado por host |
| `record_distribution(metric, value, tags=None)` | DISTRIBUTION | Agregado global |
| `track_funnel_step(funnel, step, tags=None)` | COUNT | Gera `app.funnel.{funnel}.{step}` |
| `flush()` | — | Força o envio pendente (útil em Lambda antes de retornar) |

Comportamento embutido: tags automáticas `env`/`service`/`version` em todas as métricas; tags sem `:` são descartadas com warning; tags com `user_id`, `session_id`, `request_id` ou `trace_id` geram warning de alta cardinalidade (use logs para dados de alta cardinalidade). Falha de envio vira warning, nunca exceção.

## Navegação

- [CONFIGURATION](./CONFIGURATION.md) — env vars, tabela por plataforma e notas de ECS/EKS
- [USAGE](./USAGE.md) — API compartilhada pelos entrypoints
- [TROUBLESHOOTING](./TROUBLESHOOTING.md) — diagnóstico por sintoma
