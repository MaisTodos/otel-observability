# Instalação

Este documento explica como instalar a biblioteca usando diferentes gerenciadores de pacotes e quais extras estão disponíveis.

## Instalação

### Poetry

```bash
# FastAPI
poetry add otel-observability[fastapi]

# Lambda
poetry add otel-observability[lambda]

# Métricas customizadas (DogStatsD)
poetry add otel-observability[metrics]

# Combinar extras - Exemplos comuns
poetry add otel-observability[fastapi,metrics]      # FastAPI + Métricas
poetry add otel-observability[lambda,metrics]       # Lambda + Métricas
poetry add otel-observability[fastapi,database]     # FastAPI + Database
poetry add otel-observability[fastapi,database,redis,metrics]  # Múltiplos extras

# Tudo
poetry add otel-observability[all]
```

### UV

```bash
# FastAPI
uv pip install "otel-observability[fastapi]"

# Lambda
uv pip install "otel-observability[lambda]"

# Métricas customizadas (DogStatsD)
uv pip install "otel-observability[metrics]"

# Combinar extras - Exemplos comuns
uv pip install "otel-observability[fastapi,metrics]"      # FastAPI + Métricas
uv pip install "otel-observability[lambda,metrics]"       # Lambda + Métricas
uv pip install "otel-observability[fastapi,database]"     # FastAPI + Database

# Tudo
uv pip install "otel-observability[all]"
```

### Pip

```bash
# FastAPI
pip install "otel-observability[fastapi]"

# Lambda
pip install "otel-observability[lambda]"

# Métricas customizadas (DogStatsD)
pip install "otel-observability[metrics]"

# Combinar extras - Exemplos comuns
pip install "otel-observability[fastapi,metrics]"      # FastAPI + Métricas
pip install "otel-observability[lambda,metrics]"       # Lambda + Métricas
pip install "otel-observability[fastapi,database]"     # FastAPI + Database

# Tudo
pip install "otel-observability[all]"
```

### Instalação via Git (SSH)

Para instalar diretamente do repositório usando Git SSH (útil para desenvolvimento, forks ou versões ainda não publicadas no PyPI):

**Requisito:** chave SSH configurada no GitHub. Teste com: `ssh -T git@github.com`

#### Pip

```bash
# Instalação básica
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git"

# Com extras (ex.: FastAPI + métricas)
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git#egg=otel-observability[fastapi,metrics]"

# Lambda
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git#egg=otel-observability[lambda]"

# Todas as dependências
pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git#egg=otel-observability[all]"
```

#### Poetry

```bash
# Instalação básica
poetry add "git+ssh://git@github.com/MaisTodos/otel-observability.git"
```

Para usar extras com Poetry, edite o `pyproject.toml` e rode `poetry lock && poetry install`:

```toml
[tool.poetry.dependencies]
# Exemplo: FastAPI + métricas a partir do repositório
otel-observability = { git = "ssh://git@github.com/MaisTodos/otel-observability.git", extras = ["fastapi", "metrics"] }
```

#### UV

```bash
# Instalação básica
uv pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git"

# Com extras
uv pip install "git+ssh://git@github.com/MaisTodos/otel-observability.git#egg=otel-observability[fastapi,metrics]"
```

**Dica:** Para fixar uma versão ou branch, use `git+ssh://...@github.com/MaisTodos/otel-observability.git@main` (ou `@v1.0.0` para tag).

## Extras Disponíveis

| Extra | Inclui | Quando Usar |
|-------|--------|-------------|
| `fastapi` | FastAPI + httpx + requests | Aplicações FastAPI |
| `lambda` | boto3 + AWS X-Ray | AWS Lambda |
| `database` | SQLAlchemy + PostgreSQL + MongoDB | Aplicações com DB |
| `redis` | Redis client | Cache/Queue Redis |
| `http` | httpx + requests | HTTP clients |
| `metrics` | datadog (DogStatsD) | Métricas customizadas e funis de conversão |
| `all` | Todas as dependências | Desenvolvimento completo |

## Combinações Comuns

### FastAPI + Métricas

Para aplicações FastAPI que precisam de métricas customizadas:

```bash
poetry add otel-observability[fastapi,metrics]
# ou
pip install "otel-observability[fastapi,metrics]"
```

**Inclui:**
- FastAPI instrumentation
- HTTP clients (httpx, requests)
- DogStatsD para métricas customizadas

### Lambda + Métricas

Para funções AWS Lambda que precisam de métricas customizadas:

```bash
poetry add otel-observability[lambda,metrics]
# ou
pip install "otel-observability[lambda,metrics]"
```

**Inclui:**
- AWS Lambda instrumentation
- boto3 e AWS X-Ray
- DogStatsD para métricas customizadas (via Lambda Extension)

**Nota:** Em Lambda, certifique-se de que a Datadog Lambda Extension está configurada para receber métricas DogStatsD em `localhost:8125`.

## Próximos Passos

Após a instalação:

1. [Guia de Implementação](./IMPLEMENTATION_GUIDE.md) - Roteiro de adoção passo a passo
2. [Quick Start](../README.md#-quick-start) - Comece rapidamente
3. [Configuração](./CONFIGURATION.md) - Configure variáveis de ambiente
4. [Guia de Uso](./USAGE.md) - Aprenda a usar em detalhes

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Guia de Implementação](./IMPLEMENTATION_GUIDE.md) - Guia orientativo para times e IA
- [Configuração](./CONFIGURATION.md) - Configuração detalhada
- [Guia de Uso](./USAGE.md) - Exemplos práticos
- [Quick Start](../README.md#-quick-start) - Comece rapidamente
