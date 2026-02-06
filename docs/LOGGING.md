# Logging com OpenTelemetry

Este documento explica como o sistema de logging funciona neste projeto e como adicionar contexto customizado aos logs.

## Visão Geral

O sistema de logging deste projeto fornece:

- **Correlação automática com traces**: Todos os logs incluem `trace_id` e `span_id` automaticamente
- **Formato estruturado**: Suporte a logs em formato JSON para facilitar análise em ferramentas de observabilidade
- **Contexto customizado**: Capacidade de adicionar informações de contexto (como headers HTTP, IDs de usuário, etc.) que são automaticamente incluídas em todos os logs
- **Thread-safe**: Usa `ContextVar` para garantir funcionamento correto com async/await

## Configuração Básica

### Configurar Logging

```python
from otel_observability import configure_logging, get_logger

# Configurar logging (geralmente feito uma vez no início da aplicação)
configure_logging(
    level="INFO",           # DEBUG, INFO, WARNING, ERROR, CRITICAL
    json_format=True,       # Use True em produção para logs estruturados
    logger_name=None       # None = root logger, ou especifique um nome
)

# Obter um logger
logger = get_logger(__name__)
```

### Usar o Logger

```python
logger.debug("Mensagem de debug")
logger.info("Informação importante")
logger.warning("Aviso")
logger.error("Erro ocorreu")
logger.exception("Exceção capturada")  # Inclui traceback automaticamente
```

## Formato dos Logs

### Formato JSON (Recomendado para Produção)

Quando `json_format=True`, os logs são estruturados em JSON:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "logger": "app.services.user_service",
  "message": "Usuário criado com sucesso",
  "trace_id": "a1b2c3d4e5f6g7h8",
  "span_id": "i9j0k1l2m3n4o5p6",
  "user_id": "123",
  "user_email": "user@example.com"
}
```

### Formato Legível (Desenvolvimento)

Quando `json_format=False`, os logs são formatados de forma legível:

```
2024-01-15 10:30:45 [INFO] [trace_id=a1b2c3d4e5f6g7h8 span_id=i9j0k1l2m3n4o5p6] app.services.user_service: Usuário criado com sucesso
```

## Adicionando Contexto Customizado

### Por que Adicionar Contexto?

Contexto customizado permite adicionar informações relevantes (como IDs de usuário, request IDs, headers HTTP) que serão automaticamente incluídas em **todos os logs** da requisição atual, sem precisar passar manualmente em cada chamada de log.

### Como Funciona

O sistema usa `ContextVar` do Python para armazenar contexto de forma thread-safe e compatível com async/await. O contexto é automaticamente injetado em todos os logs através do `TraceContextFilter`.

### Funções Disponíveis

```python
from otel_observability import (
    set_log_context,
    get_log_context,
    clear_log_context
)
```

#### `set_log_context(**kwargs)`

Define contexto customizado que será adicionado a todos os logs.

```python
set_log_context(
    user_id="123",
    user_email="user@example.com",
    request_id="req-abc-123"
)
```

#### `get_log_context() -> Dict[str, Any]`

Retorna o contexto atual (útil para debug ou lógica condicional).

```python
context = get_log_context()
print(context)  # {'user_id': '123', 'user_email': 'user@example.com', ...}
```

#### `clear_log_context()`

Limpa o contexto atual. **Importante**: Deve ser chamado após processar uma requisição para evitar vazamento de contexto entre requisições.

```python
clear_log_context()
```

## Exemplos Práticos

### Exemplo 1: FastAPI com Middleware

Este é o padrão recomendado para aplicações FastAPI:

```python
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from otel_observability import (
    get_logger,
    configure_logging,
    set_log_context,
    clear_log_context
)
from otel_observability.fastapi import instrument_fastapi

app = FastAPI()

# Configurar logging
configure_logging(level="INFO", json_format=True)

# Instrumentar FastAPI
instrument_fastapi(app, json_logs=True)

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware para capturar headers e armazenar no contexto de log."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Captura headers da requisição e armazena no contexto."""
        # Extrai headers da requisição
        user_email = request.headers.get("user_email", "")
        user_name = request.headers.get("user_name", "")
        user_groups = request.headers.get("user_groups", "")
        request_id = request.headers.get("x-request-id", "")
        client_ip = request.client.host if request.client else ""

        # Armazena no contexto de log
        if user_email or user_name or user_groups or request_id:
            set_log_context(
                user_email=user_email,
                user_name=user_name,
                user_groups=user_groups,
                request_id=request_id,
                client_ip=client_ip,
            )

        try:
            # Processa a requisição
            return await call_next(request)
        finally:
            # Limpa o contexto após processar a requisição
            clear_log_context()


# Adicionar middleware ANTES de definir rotas
app.add_middleware(RequestContextMiddleware)


@app.get("/api/users")
async def get_users():
    # Todos os logs desta requisição terão automaticamente:
    # - trace_id, span_id (do TraceContextFilter)
    # - user_email, user_name, user_groups, request_id, client_ip (do contexto customizado)

    logger.info("Buscando usuários")

    # ... sua lógica de negócio ...

    logger.info("Usuários encontrados", extra={"count": 10})

    # Campos extras podem ser adicionados para logs específicos
    return {"users": []}
```

### Exemplo 2: Lambda Handler

Para AWS Lambda, você pode adicionar contexto no início do handler:

```python
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability import get_logger, set_log_context, clear_log_context

logger = get_logger(__name__)


@instrument_lambda_handler()
def lambda_handler(event, context):
    # Extrair informações do evento
    user_id = event.get("user_id", "")
    request_id = event.get("request_id", "")

    # Adicionar ao contexto
    if user_id or request_id:
        set_log_context(
            user_id=user_id,
            request_id=request_id,
        )

    try:
        logger.info("Processando requisição Lambda")
        # ... sua lógica ...
        return {"statusCode": 200, "body": "OK"}
    finally:
        # Limpar contexto
        clear_log_context()
```

### Exemplo 3: Adicionar Contexto em Qualquer Ponto

Você pode adicionar ou atualizar contexto em qualquer ponto do código:

```python
from otel_observability import get_logger, set_log_context

logger = get_logger(__name__)

def process_payment(user_id: str, amount: float):
    # Adicionar contexto específico para esta operação
    set_log_context(
        operation="process_payment",
        user_id=user_id,
        amount=amount
    )

    logger.info("Iniciando processamento de pagamento")

    # Todos os logs dentro desta função terão o contexto acima
    # ... lógica de pagamento ...

    logger.info("Pagamento processado com sucesso")
```

### Exemplo 4: Campos Extras em Logs Específicos

Você pode adicionar campos extras em logs específicos usando o parâmetro `extra`:

```python
logger.info(
    "Operação concluída",
    extra={
        "duration_ms": 150,
        "records_processed": 42
    }
)
```

Esses campos extras serão incluídos no log junto com o contexto customizado e trace_id/span_id.

## Campos Automáticos

Todos os logs incluem automaticamente:

- `timestamp`: Data e hora em ISO 8601 (UTC)
- `level`: Nível do log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `logger`: Nome do logger (geralmente o nome do módulo)
- `message`: Mensagem do log
- `trace_id`: ID do trace distribuído (correlaciona logs com spans)
- `span_id`: ID do span atual (identifica a operação específica)

## Boas Práticas

### 1. Sempre Limpe o Contexto

Sempre chame `clear_log_context()` no `finally` de middlewares ou handlers para evitar vazamento de contexto entre requisições:

```python
try:
    # processar requisição
    pass
finally:
    clear_log_context()
```

### 2. Use JSON em Produção

Configure `json_format=True` em produção para facilitar análise e agregação de logs:

```python
configure_logging(level="INFO", json_format=True)
```

### 3. Adicione Contexto Relevante

Adicione apenas informações relevantes ao contexto. Exemplos úteis:

- IDs de usuário/autenticação
- Request IDs para rastreabilidade
- Informações de ambiente (staging, production)
- IDs de transação ou operação

### 4. Não Adicione Dados Sensíveis

**Nunca** adicione dados sensíveis (senhas, tokens, dados pessoais) ao contexto de log, a menos que sejam necessários e devidamente sanitizados.

### 5. Use Campos Extras para Dados Específicos

Para dados que são específicos de um único log (não de toda a requisição), use o parâmetro `extra`:

```python
# Contexto: aplicado a todos os logs
set_log_context(user_id="123")

# Extra: aplicado apenas a este log
logger.info("Processando item", extra={"item_id": "item-456"})
```

## Integração com Tracing

Os logs são automaticamente correlacionados com traces através de `trace_id` e `span_id`. Isso permite:

- Encontrar todos os logs relacionados a um trace específico
- Correlacionar logs com spans de operações
- Rastrear o fluxo completo de uma requisição através de múltiplos serviços

## Troubleshooting

### Contexto não aparece nos logs

1. Verifique se `set_log_context()` foi chamado antes dos logs
2. Verifique se o logger está usando o handler configurado com `TraceContextFilter`
3. Em formato não-JSON, campos customizados podem não aparecer (use `json_format=True`)

### Contexto vazando entre requisições

1. Certifique-se de chamar `clear_log_context()` no `finally` do middleware/handler
2. Verifique se não há exceções não tratadas que impedem o `finally` de executar

### Logs duplicados

1. Verifique se `logger.propagate` está configurado corretamente
2. Certifique-se de não adicionar múltiplos handlers ao mesmo logger

## Navegação

- [README](../README.md) - Visão geral e quick start
- [Guia de Implementação](./IMPLEMENTATION_GUIDE.md) - Como combinar logs com traces e métricas
- [Conceitos](./CONCEPTS.md) - Conceitos de OpenTelemetry e propagação de contexto
- [Guia de Uso](./USAGE.md) - Exemplos práticos de uso
- [Configuração](./CONFIGURATION.md) - Configuração de variáveis de ambiente

## Referências Externas

- [Python Logging Documentation](https://docs.python.org/3/library/logging.html)
- [ContextVar Documentation](https://docs.python.org/3/library/contextvars.html)
- [OpenTelemetry Logging](https://opentelemetry.io/docs/specs/otel/logs/)
