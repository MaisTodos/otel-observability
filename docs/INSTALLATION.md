# Instalação

Este documento explica como instalar a biblioteca usando diferentes gerenciadores de pacotes e quais extras estão disponíveis.

## Instalação

### Poetry

```bash
# FastAPI
poetry add otel-observability[fastapi]

# Lambda
poetry add otel-observability[lambda]

# Tudo
poetry add otel-observability[all]

# Combinar extras
poetry add otel-observability[fastapi,database,redis]
```

### UV

```bash
# FastAPI
uv pip install "otel-observability[fastapi]"

# Lambda
uv pip install "otel-observability[lambda]"

# Tudo
uv pip install "otel-observability[all]"
```

### Pip

```bash
# FastAPI
pip install "otel-observability[fastapi]"

# Lambda
pip install "otel-observability[lambda]"

# Tudo
pip install "otel-observability[all]"
```

## Extras Disponíveis

| Extra | Inclui | Quando Usar |
|-------|--------|-------------|
| `fastapi` | FastAPI + httpx + requests | Aplicações FastAPI |
| `lambda` | boto3 + AWS X-Ray | AWS Lambda |
| `database` | SQLAlchemy + PostgreSQL + MongoDB | Aplicações com DB |
| `redis` | Redis client | Cache/Queue Redis |
| `http` | httpx + requests | HTTP clients |
| `all` | Todas as dependências | Desenvolvimento completo |

## Próximos Passos

Após a instalação:

1. [Quick Start](../README.md#-quick-start) - Comece rapidamente
2. [Configuração](./CONFIGURATION.md) - Configure variáveis de ambiente
3. [Guia de Uso](./USAGE.md) - Aprenda a usar em detalhes

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Configuração](./CONFIGURATION.md) - Configuração detalhada
- [Guia de Uso](./USAGE.md) - Exemplos práticos
- [Quick Start](../README.md#-quick-start) - Comece rapidamente
