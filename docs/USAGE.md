# Uso

A API que os serviços de fato chamam, na ordem de adoção real. Todos os exemplos abaixo foram executados contra a versão atual do código.

## 1. Logging com contexto — `get_logger` e `set_log_context`

```python
import logging

from otel_observability import configure_logging, get_logger, set_log_context, get_log_context

configure_logging(level="INFO", json_format=True)
logger = get_logger(__name__)

set_log_context(user_id="123")
logger.info("processando pedido", extra={"count": 10})
```

Saída real (sem env de serviço configurada, os tags vêm com default):

```json
{"timestamp": "2026-09-07T00:07:49.265262Z", "level": "INFO", "logger": "__main__", "message": "processando pedido", "trace_id": "", "span_id": "", "env": "development", "service": "unknown-service", "version": "0.0.0", "count": 10, "user_id": "123"}
```

Como funciona:

- `get_logger(name)` é `logging.getLogger(name)` puro. A correlação de traces acontece no **handler** (`TraceContextFilter`), não no logger — qualquer logger do Python que passe pelo handler configurado ganha `trace_id`/`span_id` automaticamente.
- `set_log_context(**kwargs)` guarda contexto em uma `ContextVar` (thread-safe, seguro com async/await). O contexto entra em **todos** os logs da requisição. `get_log_context()` devolve uma cópia; `clear_log_context()` limpa.
- `extra={...}` vale para um log só. Dicts aninhados são achatados em notação de ponto (`{"output": {"count": 42}}` → `output.count: 42`), com profundidade máxima 3; valores `None` são descartados (o protocolo OTLP não aceita `None`); objetos não-primitivos viram `str(...)`.
- Campos automáticos de cada log: `timestamp`, `level`, `logger`, `message`, `trace_id`, `span_id`, `env`, `service`, `version`.
- Com `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` configurada, `init_telemetry` registra um `LoggingHandler` no root logger: os mesmos logs vão ao Datadog via OTLP **além** do stdout.

## 2. `RequestLoggingMiddleware`

Middleware de logging de request usado por todos os serviços FastAPI da stack. Loga `request.completed` com `method`, `path`, `status_code` e `duration_ms` após a resposta, e garante `clear_log_context()` no `finally` (evita vazamento de contexto entre requests no mesmo worker).

```python
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient  # só para demonstrar

from otel_observability.fastapi import RequestLoggingMiddleware
from otel_observability import set_log_context

logger = logging.getLogger("meu-servico")


class RequestContextMiddleware(RequestLoggingMiddleware):
    async def dispatch(self, request, call_next):
        user_id = request.headers.get("user_id", "")
        if user_id:
            set_log_context(user_id=user_id)
        return await super().dispatch(request, call_next)


app = FastAPI()
app.add_middleware(RequestContextMiddleware, logger=logger)


@app.get("/hello")
def hello():
    return {"ok": True}


client = TestClient(app)
client.get("/hello", headers={"user_id": "42"})
```

O middleware aceita `skip_log_paths` (default `{"/ping"}`) — paths nessa lista não geram o log `request.completed`, mas o `clear_log_context()` roda para toda request. O `logger` é obrigatório: qualquer objeto com `.info()`.

## 3. `instrument_fastapi`

```python
from fastapi import FastAPI
from otel_observability.fastapi import instrument_fastapi, add_span_attribute, add_span_event
from otel_observability import get_logger

app = FastAPI()
instrument_fastapi(app)  # chamar ANTES de definir rotas

logger = get_logger(__name__)


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    add_span_attribute("user.id", user_id)
    add_span_event("user.fetch_started")
    return {"user_id": user_id}
```

Parâmetros (assinatura real):

| Parâmetro | Default | Efeito |
|---|---|---|
| `config` | `None` | `TelemetryConfig` própria; se `None`, lê do ambiente |
| `configure_logs` | `True` | Chama `configure_logging` com o nível e formato resolvidos |
| `json_logs` | `None` | Precedência: parâmetro > `OTEL_LOG_FORMAT` > `False` (default deste entrypoint) |
| `excluded_urls` | `None` | Regex de paths fora do tracing, ex.: `"/health\|/metrics"` |
| `auto_instrument_libs` | `True` | Auto-instrumenta httpx, requests, sqlalchemy, psycopg2, pymongo, redis, boto3 (conforme instalados) |
| `redact_keys` | `None` | Chaves extras mascaradas por completo (mecanismo legado) |
| `mask_policy` | `None` | Mapa campo → `Mask`; ver seção 6 |
| `suppress_access_logs` | `True` | Com `excluded_urls` setado, descarta também o access log do uvicorn desses paths |

Comportamento embutido do tracing de request: atributos `http.method`, `http.route`, `http.status_code`, `http.user_agent`; `request.is_health_check` para `/health`, `/healthz`, `/readiness`, `/liveness`; e `tenant.id` extraído do header `x-tenant-id`.

`add_span_attribute(key, value)` e `add_span_event(name, attributes=None)` anotam o span atual e são importados de `otel_observability.fastapi` (não estão no `__all__` do pacote).

⚠️ Não adicione handlers ao root logger depois de instrumentar: `configure_logging` limpa os handlers existentes, e a ordem certa (logs primeiro, telemetria depois) é o que os entrypoints já fazem internamente.

## 4. `seed_otel_env` / `OTEL_ENV_KEYS` — a ponte Pydantic Settings → `os.environ`

A lib lê configuração direto de `os.environ`, mas os serviços configuram via Pydantic Settings (que carrega o `.env` sem exportar para o processo). `seed_otel_env` extrai as chaves de `OTEL_ENV_KEYS` do objeto de settings e injeta no `os.environ`:

```python
from otel_observability import seed_otel_env


class Settings:
    OTEL_SERVICE_NAME = "svc-exemplo"
    OTEL_ENVIRONMENT = "dev"
    OTEL_SERVICE_VERSION = "1.2.3"
    OTEL_LOG_FORMAT = "json"
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT = None
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = None
    OTEL_EXPORTER_OTLP_HEADERS = None
    DD_API_KEY = None


applied = seed_otel_env(Settings())
print(applied)
```

Saída real:

```python
{'OTEL_SERVICE_NAME': 'svc-exemplo', 'OTEL_ENVIRONMENT': 'dev', 'OTEL_SERVICE_VERSION': '1.2.3', 'OTEL_LOG_FORMAT': 'json'}
```

Regras: usa `setdefault` — env real do processo vence sobre o settings; `None` e `""` são pulados; overrides nomeados (`seed_otel_env(settings, OTEL_SERVICE_NAME="outro")`) vencem o `source`; o retorno é o dict efetivamente aplicado. `OTEL_ENV_KEYS` cobre exatamente: `OTEL_SERVICE_NAME`, `OTEL_ENVIRONMENT`, `OTEL_SERVICE_VERSION`, `OTEL_LOG_FORMAT`, `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `DD_API_KEY`.

## 5. `@trace`

⚠️ **Sempre com parênteses** — `@trace` é factory: `@trace()` ou `@trace("nome")`. Usar nu (`@trace` direto sobre a função) quebra com `AttributeError`.

```python
import asyncio

from otel_observability import trace


@trace("process_payment", attributes={"operation.type": "payment"})
async def process_payment(user_id: int, amount: float):
    return {"status": "success", "user_id": user_id}


print(asyncio.run(process_payment(1, 10.0)))
```

Saída real:

```python
{'status': 'success', 'user_id': 1}
```

Funciona com funções sync e async (detecta automaticamente). Em exceção: status `ERROR` + `record_exception` e re-raise. Todo span ganha `code.function` e `code.namespace`.

Complementos de span em `otel_observability`:

- `get_tracer(name=None)` — sem argumento, resolve o `__name__` do módulo chamador
- `get_current_trace_id()` / `get_current_span_id()` — hex strings (`""` fora de trace)
- `get_current_span()` — o span ativo

## 6. Redação de PII — `mask_policy`

O `RedactionFilter` mascara valores sensíveis nos campos extra de cada log. Roda nos dois caminhos — handler de stdout **e** handler OTLP — então tanto o stream local quanto o exportado saem mascarados. A recursão cobre dicts, listas, tuplas e conjuntos, e também abre objetos pydantic v2, dataclasses e strings JSON (até 64 KB) que apareçam dentro de `extra`: `extra={"input": dto}` e `extra={"props": {"event": json.dumps(evento)}}` saem mascarados nos dois caminhos. Tipos que o JSON não conhece (`UUID`, `Decimal`, `datetime`) saem como texto em vez de derrubar a linha, e chaves de dict que não são texto viram `str(chave)`. Bytes com JSON seguem o mesmo caminho. O limite de 64 KB é em bytes UTF-8.

Limites conhecidos:

- O filtro troca o valor no próprio record. Um handler seu que roda depois dos handlers com o `RedactionFilter` recebe `dict` no lugar do objeto; um que roda antes vê o dado em claro. Se precisar do objeto original, ponha esse handler antes na lista `logger.handlers` e não exporte o dado por ele.
- Pydantic com `@model_serializer` que renomeia campos é mascarado pelos nomes novos. Pydantic v1 (`.dict()`) e attrs são abertos como pydantic v2 e dataclass; objeto com `__slots__` que não é nenhum desses sai como `str()`. Nesses casos use a chave exata na `mask_policy` ou converta para dict antes de logar.
- Conjunto de strings soltas (sem chave) não é mascarado. Estrutura com mais de 32 níveis sai com `*****` no corte.

Estratégias (`Mask`):

| Estratégia | Efeito | Para quê |
|---|---|---|
| `Mask.FULL` | `*****` | Credencial: nada aproveitável |
| `Mask.LAST4` | `*******8901` | Documento: sustentação localiza pelos 4 dígitos |
| `Mask.EMAIL` | `j*********@maistodos.com.br` | Domínio preservado |
| `Mask.PIX` | Detecta o formato (CPF, e-mail, telefone, aleatória) e delega | Chave Pix não tem formato único |
| `Mask.NAME` | `J. d. S.` (iniciais de cada palavra) | Nome de pessoa ou empresa |

`DEFAULT_MASK_POLICY` (sempre ativa): `authorization`, `access_token`, `refresh_token`, `client_secret`, `password`, `secret`, `api_key`, `dd_api_key` → FULL; `document`, `document_number`, `cpf`, `cnpj`, `phone` → LAST4; `email` → EMAIL.

`CONTA_DIGITAL_MASK_POLICY` (opt-in de serviços de Conta Digital):

- LAST4: `account_document`, `tax_id`, `account_number`, `account_branch` e os sufixos `*_document`, `*_cpf`, `*_cnpj`.
- EMAIL: o sufixo `*_email`.
- PIX: `pix_key`, `addressing_key`.
- NAME: `account_name`, `holder_name`, `trade_name`, `user_name`.
- Os nomes de conta, Pix e nome também valem como sufixo (`sender_account_number`, `recipient_pix_key`, `legal_holder_name`).
- `name`, `key`, `event_name` e `file_name` não estão na policy de propósito.

Como a chave é comparada:

1. A chave do log é normalizada: camelCase e kebab viram snake e depois lower (`documentNumber` → `document_number`, `pix-key` → `pix_key`).
2. Chave exata na policy.
3. Sufixo: entrada da policy com `*` na frente, `{"*_document": Mask.LAST4}` casa `sender_document` e `customerDocument`. O sufixo mais longo vence. A chave `document` sozinha não casa `*_document`.
4. Sem casamento, o valor sai intocado.

`bytes` sob chave sensível são decodificados antes de mascarar. A estratégia vale para cada elemento de lista, tupla e conjunto e para cada valor de dict sob a chave. Flags e contagens não são mascaradas: `bool` nunca, e número pequeno (abaixo de 10 000) ou `None` quando a estratégia veio de sufixo e a chave começa com `has_`, `is_`, `total_` ou `count_` (`has_document=False`, `total_cnpj=3`). Chave exata da policy sempre mascara, e `total_cpf=12345678901` também.

```python
from otel_observability import configure_logging, get_logger, mask_document, CONTA_DIGITAL_MASK_POLICY

print("mask_document:", mask_document("12345678901"))

configure_logging(level="INFO", json_format=True, mask_policy=CONTA_DIGITAL_MASK_POLICY)
logger = get_logger("pagamentos")
logger.info("pagamento recebido", extra={
    "email": "joao.silva@maistodos.com.br",
    "cpf": "12345678901",
    "authorization": "Bearer abc.def.ghi",
    "pix_key": "joao.silva@maistodos.com.br",
})
```

Saída real:

```json
{"timestamp": "2026-09-07T00:08:39.112888Z", "level": "INFO", "logger": "pagamentos", "message": "pagamento recebido", "trace_id": "", "span_id": "", "env": "development", "service": "unknown-service", "version": "0.0.0", "email": "j*********@maistodos.com.br", "cpf": "*******8901", "authorization": "*****", "pix_key": "j*********@maistodos.com.br"}
```

Regras do merge: o default universal sempre entra; o que o consumidor passar em `mask_policy` faz merge por cima e pode sobrescrever um default (chave case-insensitive); estratégia inválida levanta `ValueError` no startup, não em runtime. `redact_keys` (legado, 1 serviço em produção) equivale a `Mask.FULL` via `setdefault` — a policy vence se a chave já tiver estratégia.

`mask_policy` entra por `configure_logging(mask_policy=...)` ou direto nos três entrypoints (`instrument_fastapi`, `instrument_lambda_handler`, `instrument_chalice`). `mask_document(value, visible=4)` é público para os serviços que mascaram fora de logs.

## 7. Propagação manual — produtor

Consumidores instrumentados extraem contexto automaticamente. O **produtor** é que precisa injetar. No envio SQS via boto3, passe o retorno de `inject_context_into_sqs_message_attributes()` como `MessageAttributes` do `send_message`; o módulo `otel_observability.propagation` tem os pares injetar/extrair para HTTP headers, SQS, SNS, EventBridge (`detail`) e payload de Lambda-to-Lambda. Nota: a injeção SQS/SNS consome até 3 dos 10 `MessageAttributes` da mensagem (traceparent, tracestate, baggage).

Round-trip verificado (executado): o produtor injeta dentro de um span ativo, e o consumidor reconstrói o mesmo trace id a partir do evento:

```python
from opentelemetry import trace
from opentelemetry import context as otel_context

from otel_observability import init_telemetry
from otel_observability.config import TelemetryConfig
from otel_observability.propagation import (
    inject_context_into_sqs_message_attributes,
    extract_context_from_sqs_message,
)

cfg = TelemetryConfig(
    service_name="demo", environment="dev", service_version="0.1.0",
    otlp_endpoint="", otlp_traces_endpoint=None, otlp_metrics_endpoint=None,
    otlp_logs_endpoint=None, traces_enabled=False, otlp_headers=None,
    is_lambda=False, enable_console_export=False, log_level="INFO",
    sample_rate=1.0, dogstatsd_enabled=False, dogstatsd_host="localhost",
    dogstatsd_port=8125,
)
init_telemetry(cfg)

# Produtor: dentro de um span ativo, injeta o contexto nos MessageAttributes
tracer = trace.get_tracer("produtor")
with tracer.start_as_current_span("envio") as span:
    esperado = span.get_span_context()
    attrs = inject_context_into_sqs_message_attributes()  # formato da API de envio

# Consumidor: o evento Lambda chega com 'stringValue' (formato wire do SQS)
record = {"messageAttributes": {"traceparent": {"stringValue": attrs["traceparent"]["StringValue"]}}}
otel_context.attach(extract_context_from_sqs_message(record))
atual = trace.get_current_span().get_span_context()
assert format(atual.trace_id, "032x") == format(esperado.trace_id, "032x")
```

## Auto-instrumentação

Os três entrypoints rodam `auto_instrument()` por default (`auto_instrument_libs=True`): httpx, requests, sqlalchemy, psycopg2, pymongo, redis e boto3 — conforme disponíveis no processo. Controle manual:

```python
from otel_observability.auto_instrument import auto_instrument

auto_instrument(libraries=["httpx", "sqlalchemy"])  # ou exclude=["boto3"]
```

## Navegação

- [CONFIGURATION](./CONFIGURATION.md) — env vars e cenários por plataforma
- [ENTRYPOINTS](./ENTRYPOINTS.md) — Lambda e Chalice em detalhe
- [TROUBLESHOOTING](./TROUBLESHOOTING.md) — diagnóstico por sintoma
- [CHANGELOG](./CHANGELOG.md) — histórico e roadmap
