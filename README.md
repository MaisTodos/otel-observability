# otel-observability

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-1.20+-blueviolet.svg)](https://opentelemetry.io/)

Biblioteca Python de **OpenTelemetry** para **FastAPI**, **AWS Lambda** e **Chalice** com integração ao **Datadog** via OTLP: tracing distribuído, logs estruturados correlacionados a traces, redação de PII e métricas DogStatsD.

> **Aviso de Visibilidade**
>
> Este repositório está temporariamente público para facilitar a configuração do pipeline de deploy, sem a necessidade de configurar autenticação SSH no CI/CD.
>
> Uma auditoria de segurança foi realizada antes desta mudança: nenhuma credencial, segredo ou referência interna sensível foi encontrada no código-fonte ou no histórico do git. Todos os valores sensíveis são injetados exclusivamente via variáveis de ambiente em tempo de execução.
>
> O repositório será tornado privado novamente assim que a autenticação do pipeline estiver devidamente configurada.

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Referência única de env vars, precedência, campos mortos e cenários por plataforma (App Runner, Lambda, ECS, EKS) |
| [docs/USAGE.md](docs/USAGE.md) | A API que os serviços chamam: logging com contexto, `RequestLoggingMiddleware`, `instrument_fastapi`, `seed_otel_env`, `@trace`, redação de PII, propagação |
| [docs/ENTRYPOINTS.md](docs/ENTRYPOINTS.md) | Lambda e Chalice: decorators, extras corretos, ciclo de vida (flush vs shutdown), métricas DogStatsD |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Trace não aparece / log não aparece / contexto não propaga |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Histórico de mudanças e roadmap |
| [tests/README.md](tests/README.md) | Como rodar e escrever os testes da lib |

Contexto de agente: [CLAUDE.md](CLAUDE.md).

## Instalação

**A lib não está publicada no PyPI.** Instale direto do Git via SSH (chave SSH configurada no GitHub — teste com `ssh -T git@github.com`):

```bash
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git"

# Com extras
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git#egg=otel-observability[fastapi]"

# Fixando ref (branch ou tag)
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git@main"
```

No Poetry:

```toml
[tool.poetry.dependencies]
otel-observability = { git = "ssh://git@github.com/MaisTodos/otel-observability.git", extras = ["fastapi"] }
```

Extras disponíveis:

| Extra | Inclui |
|---|---|
| `fastapi` | FastAPI + instrumentações httpx/requests |
| `lambda` | Propagador AWS X-Ray + instrumentação boto3sqs/botocore |
| `chalice` | Framework Chalice |
| `database` | SQLAlchemy, psycopg2, pymongo |
| `redis` | Redis |
| `http` | httpx, requests |
| `metrics` | datadog (DogStatsD) |
| `all` | Tudo |

## Quick start — FastAPI

```python
from fastapi import FastAPI
from otel_observability.fastapi import instrument_fastapi
from otel_observability import get_logger

app = FastAPI()
instrument_fastapi(app)  # ANTES de definir rotas
logger = get_logger(__name__)


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    logger.info("buscando usuário", extra={"user_id": user_id})
    return {"user_id": user_id}
```

Configuração mínima (referência completa em [docs/CONFIGURATION.md](docs/CONFIGURATION.md)):

```bash
OTEL_SERVICE_NAME=my-service
OTEL_ENVIRONMENT=production
OTEL_SERVICE_VERSION=1.0.0
OTEL_LOG_FORMAT=json
DD_API_KEY=<sua-api-key>
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://otlp.datadoghq.com/v1/logs
```

## Lambda e Chalice

```python
from otel_observability.aws_lambda import instrument_lambda_handler

@instrument_lambda_handler()
def lambda_handler(event, context):
    # trace context extraído automaticamente de API Gateway, SQS, SNS e EventBridge
    ...
```

```python
from chalice import Chalice
from otel_observability.chalice import instrument_chalice, trace_sqs_message

app = Chalice(app_name="myapp")
instrument_chalice(app)

@app.on_sqs_message(queue_name="my-queue")
@trace_sqs_message  # decorator nu — SEM parênteses
def process_message(event):
    ...
```

Lambda usa o extra `lambda`; Chalice usa o extra `chalice`. Ciclo de vida: `flush_telemetry` a cada invocação, nunca `shutdown_telemetry` — detalhes em [docs/ENTRYPOINTS.md](docs/ENTRYPOINTS.md).

## Métricas

```python
from otel_observability import increment_counter, track_funnel_step

increment_counter("app.checkout.start", tags=["region:us-east-1"])
track_funnel_step("checkout", "completed")
```

⚠️ O caminho DogStatsD é no-op sem o extra `metrics` (nenhum serviço da stack o instala hoje) e sem um Agent/Extension escutando em `localhost:8125`. Detalhes em [docs/ENTRYPOINTS.md](docs/ENTRYPOINTS.md).

## Exemplos

- [`examples/fastapi_example.py`](examples/fastapi_example.py) — FastAPI com múltiplos casos de uso
- [`examples/lambda_example.py`](examples/lambda_example.py) — Lambda com diferentes triggers
- [`examples/distributed_tracing_example.py`](examples/distributed_tracing_example.py) — tracing distribuído
- [`examples/metrics_example.py`](examples/metrics_example.py) — métricas DogStatsD
- [`examples/funnel_metrics_example.py`](examples/funnel_metrics_example.py) — funis de conversão
- [`examples/app_runner_example.py`](examples/app_runner_example.py) — App Runner

## Desenvolvimento

```bash
make install   # dependências
make lint      # ruff check
make test      # pytest
```

Como estruturar e rodar testes: [tests/README.md](tests/README.md).

## Recursos

- [OpenTelemetry Docs](https://opentelemetry.io/docs/)
- [Datadog OTLP Ingest](https://docs.datadoghq.com/opentelemetry/setup/otlp_ingest/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
