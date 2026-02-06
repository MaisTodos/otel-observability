# Auto-Instrumentação

Este documento explica como a biblioteca auto-instrumenta bibliotecas comuns automaticamente e como controlar esse comportamento.

## Bibliotecas Suportadas

A biblioteca auto-instrumenta as seguintes bibliotecas:

- ✅ **httpx** - HTTP client assíncrono
- ✅ **requests** - HTTP client síncrono
- ✅ **sqlalchemy** - ORM
- ✅ **psycopg2** - PostgreSQL driver
- ✅ **pymongo** - MongoDB driver
- ✅ **redis** - Redis client
- ✅ **boto3** - AWS SDK (S3, DynamoDB, SQS, etc.)

## Como Funciona

### Automático

A auto-instrumentação é ativada automaticamente quando você usa os helpers principais:

```python
# FastAPI - Auto-instrumentação ativada por padrão
instrument_fastapi(app)  # httpx, requests são instrumentados automaticamente

# Lambda - Auto-instrumentação ativada por padrão
@instrument_lambda_handler()  # boto3 é instrumentado automaticamente
```

### Manual

Você também pode controlar a auto-instrumentação manualmente:

```python
from otel_observability.auto_instrument import auto_instrument

# Todas as bibliotecas disponíveis
auto_instrument()

# Apenas específicas
auto_instrument(libraries=["httpx", "sqlalchemy"])

# Todas exceto algumas
auto_instrument(exclude=["boto3"])
```

## Exemplo de Uso

```python
from otel_observability.fastapi import instrument_fastapi
from fastapi import FastAPI
import httpx
from sqlalchemy import create_engine

app = FastAPI()
instrument_fastapi(app)  # Auto-instrumenta httpx, requests, sqlalchemy

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # Chamada HTTP automaticamente rastreada
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/users")

    # Query SQL automaticamente rastreada
    engine = create_engine("postgresql://...")
    result = engine.execute("SELECT * FROM users")

    return {"user_id": user_id}
```

## Benefícios

- **Zero configuração** - Funciona automaticamente
- **Rastreamento completo** - Todas as operações são rastreadas
- **Propagação automática** - Contexto é propagado automaticamente entre serviços
- **Baixo overhead** - Performance otimizada

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Guia de Implementação](./IMPLEMENTATION_GUIDE.md) - Quando e como ativar auto-instrumentação
- [Guia de Uso](./USAGE.md) - Exemplos práticos
- [Conceitos](./CONCEPTS.md) - Entenda propagação de contexto
- [Arquitetura](./ARCHITECTURE.md) - Como funciona o fluxo de dados

## Referências Externas

- [OpenTelemetry Auto-Instrumentation](https://opentelemetry.io/docs/instrumentation/python/automatic/)
