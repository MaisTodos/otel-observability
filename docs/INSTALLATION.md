# Instalação

Este documento explica como instalar a biblioteca usando diferentes métodos e gerenciadores de pacotes.

## Métodos de Instalação

### 1. PyPI (Produção)

Quando o pacote estiver publicado no PyPI:

#### Poetry

```bash
# FastAPI
poetry add otel-observability[fastapi]

# Lambda
poetry add otel-observability[lambda]

# Chalice
poetry add otel-observability[chalice]

# Tudo
poetry add otel-observability[all]

# Combinar extras
poetry add otel-observability[fastapi,database,redis]
```

#### UV

```bash
# FastAPI
uv add "otel-observability[fastapi]"

# Lambda
uv add "otel-observability[lambda]"

# Chalice
uv add "otel-observability[chalice]"

# Tudo
uv add "otel-observability[all]"

# Combinar extras
uv add "otel-observability[fastapi,database,redis]"
```

### 2. GitHub (Validação Inicial)

Para testar antes de publicar no PyPI ou usar versões específicas:

#### Poetry

```bash
# Versão específica (tag)
poetry add git+https://github.com/seu-usuario/otel-observability.git@v0.1.0

# Branch específica
poetry add git+https://github.com/seu-usuario/otel-observability.git@main

# Com extras
poetry add "git+https://github.com/seu-usuario/otel-observability.git@v0.1.0#egg=otel-observability[fastapi]"
```

#### UV

```bash
# Versão específica
uv add "git+https://github.com/seu-usuario/otel-observability.git@v0.1.0"

# Branch específica
uv add "git+https://github.com/seu-usuario/otel-observability.git@main"

# Com extras
uv add "git+https://github.com/seu-usuario/otel-observability.git@v0.1.0#egg=otel-observability[fastapi]"
```

#### SSH (Repositório Privado)

Se o repositório for privado e você tiver acesso SSH configurado:

```bash
# Poetry
poetry add git+ssh://git@github.com/seu-usuario/otel-observability.git@v0.1.0

# UV
uv add "git+ssh://git@github.com/seu-usuario/otel-observability.git@v0.1.0"
```

**Nota**: Para SSH funcionar, você precisa ter:
- Chave SSH configurada no GitHub/GitLab
- Acesso ao repositório

### 3. Instalação Local (Desenvolvimento)

Para desenvolvimento local ou testes:

```bash
# Poetry
poetry install
poetry install --extras "fastapi"
poetry install --extras "all"

# UV
uv sync
uv sync --extra fastapi
uv sync --extra all
```

### 4. Registry Privado (Empresa)

#### PyPI Privado

PyPI privado permite hospedar pacotes Python internamente. Opções populares: **pypiserver**, **devpi**, **bandersnatch**.

**Configurar Poetry:**

```bash
# Adicionar source privado
poetry source add --priority=supplemental private https://pypi.sua-empresa.com/simple

# Configurar autenticação (se necessário)
poetry config http-basic.private seu-usuario sua-senha

# Instalar do registry privado
poetry add otel-observability[fastapi] --source private
```

Ou adicionar no `pyproject.toml`:

```toml
[[tool.poetry.source]]
name = "private"
url = "https://pypi.sua-empresa.com/simple"
priority = "supplemental"
default = false
```

**Configurar UV:**

```bash
# Adicionar source no pyproject.toml
# [tool.uv.sources]
# otel-observability = { index = "private" }

# Ou usar variável de ambiente
export UV_INDEX_URL=https://pypi.sua-empresa.com/simple
export UV_INDEX_USERNAME=seu-usuario
export UV_INDEX_PASSWORD=sua-senha

uv add otel-observability[fastapi]
```

#### GitHub Packages

**Configurar Poetry:**

```bash
# Adicionar source
poetry source add --priority=supplemental github https://maven.pkg.github.com/sua-empresa/packages

# Configurar autenticação (token com permissão `read:packages`)
poetry config http-basic.github seu-usuario seu-token-github
```

**Configurar UV:**

```bash
# Adicionar source no pyproject.toml
# [tool.uv.sources]
# otel-observability = { index = "github" }

# Configurar autenticação
export UV_INDEX_URL=https://maven.pkg.github.com/sua-empresa/packages
export UV_INDEX_USERNAME=seu-usuario
export UV_INDEX_PASSWORD=seu-token-github

uv add otel-observability[fastapi]
```

#### AWS CodeArtifact

**Configurar Poetry:**

```bash
# Obter token de autenticação
TOKEN=$(aws codeartifact get-authorization-token \
  --domain sua-empresa \
  --domain-owner 123456789012 \
  --query authorizationToken \
  --output text)

# Configurar autenticação
poetry config http-basic.codeartifact aws $TOKEN

# Adicionar source
poetry source add codeartifact \
  https://sua-empresa-123456789012.d.codeartifact.us-east-1.amazonaws.com/pypi/pacotes/simple/
```

**Configurar UV:**

```bash
# Obter token
TOKEN=$(aws codeartifact get-authorization-token \
  --domain sua-empresa \
  --domain-owner 123456789012 \
  --query authorizationToken \
  --output text)

# Configurar
export UV_INDEX_URL=https://sua-empresa-123456789012.d.codeartifact.us-east-1.amazonaws.com/pypi/pacotes/simple/
export UV_INDEX_USERNAME=aws
export UV_INDEX_PASSWORD=$TOKEN

uv add otel-observability[fastapi]
```

## Extras Disponíveis

| Extra | Inclui | Quando Usar |
|-------|--------|-------------|
| `fastapi` | FastAPI + httpx + requests | Aplicações FastAPI |
| `lambda` | boto3 + AWS X-Ray | AWS Lambda (pura) |
| `chalice` | Chalice framework | Aplicações Chalice |
| `database` | SQLAlchemy + PostgreSQL + MongoDB | Aplicações com DB |
| `redis` | Redis client | Cache/Queue Redis |
| `http` | httpx + requests | HTTP clients |
| `all` | Todas as dependências | Desenvolvimento completo |

## Exemplos de Uso por Cenário

### FastAPI

```bash
poetry add otel-observability[fastapi]
# ou
uv add "otel-observability[fastapi]"
```

### AWS Lambda

```bash
poetry add otel-observability[lambda]
# ou
uv add "otel-observability[lambda]"
```

### Chalice

```bash
poetry add otel-observability[chalice]
# ou
uv add "otel-observability[chalice]"
```

### Desenvolvimento Completo

```bash
poetry add otel-observability[all]
# ou
uv add "otel-observability[all]"
```

## Publicando no Registry Privado

### Pré-requisitos

Antes de publicar, você precisa:

1. **Build do pacote:**
   ```bash
   python -m build
   # Isso cria dist/otel_observability-X.Y.Z.tar.gz e dist/otel_observability-X.Y.Z-py3-none-any.whl
   ```

2. **Instalar twine:**
   ```bash
   poetry add --group dev twine
   # ou
   uv add --dev twine
   ```

### PyPI Privado

```bash
# Upload com autenticação
twine upload \
  --repository-url https://pypi.sua-empresa.com \
  --username seu-usuario \
  --password sua-senha \
  dist/*

# Ou configurar ~/.pypirc
[distutils]
index-servers =
    private

[private]
repository = https://pypi.sua-empresa.com
username = seu-usuario
password = sua-senha

# Depois usar:
twine upload --repository private dist/*
```

### GitHub Packages

```bash
# Configurar ~/.pypirc
[distutils]
index-servers =
    github

[github]
repository = https://maven.pkg.github.com/sua-empresa/packages
username = seu-usuario
password = seu-token-github  # Token com permissão write:packages

# Upload
twine upload --repository github dist/*
```

**Nota**: O nome do pacote no GitHub Packages deve seguir o padrão: `OWNER/REPO-NAME`

### AWS CodeArtifact

```bash
# Autenticar
aws codeartifact login --tool twine \
  --domain sua-empresa \
  --domain-owner 123456789012 \
  --repository pacotes \
  --region us-east-1

# Upload (twine usa as credenciais configuradas pelo comando acima)
twine upload --repository codeartifact dist/*
```

**Nota**: O comando `aws codeartifact login` configura automaticamente o `~/.pypirc` com as credenciais temporárias.

## Troubleshooting

### Erro: "Could not find a version that satisfies the requirement"

**Solução**: Verifique se:
- O nome do pacote está correto
- A versão especificada existe
- O registry está acessível
- As credenciais estão configuradas corretamente (para registries privados)

### Erro: "Authentication failed" (Registry Privado)

**Solução**:
- Verifique se o token/senha está correto
- Confirme que você tem permissão para acessar o registry
- Para Poetry: `poetry config http-basic.<source-name> usuario senha`
- Para UV: configure `UV_INDEX_USERNAME` e `UV_INDEX_PASSWORD` ou use `uv tool run twine`

### Erro: "Module not found" após instalação

**Solução**:
- Verifique se está no ambiente virtual correto
- Reinstale o pacote:
  - Poetry: `poetry remove otel-observability && poetry add otel-observability[fastapi]`
  - UV: `uv remove otel-observability && uv add "otel-observability[fastapi]"`
- Verifique se os extras necessários foram instalados

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
