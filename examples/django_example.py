"""
Exemplo de uso da biblioteca otel-observability com Django.

Este exemplo demonstra:
1. Inicialização da instrumentação (wsgi.py / AppConfig.ready)
2. Middleware de logging de requests
3. Logging correlacionado com traces (trace_id / span_id automáticos)
4. Contexto customizado por request (user_id, tenant_id)
5. Spans e atributos customizados em views
6. Decorator @trace para funções de serviço

Para executar:
    export OTEL_SERVICE_NAME=django-example
    export OTEL_ENVIRONMENT=development
    export OTEL_SERVICE_VERSION=1.0.0
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
    python manage.py runserver
"""

# ==============================================================================
# PASSO 1: Inicialização — wsgi.py (uma única vez, antes de get_wsgi_application)
# ==============================================================================
#
# wsgi.py
# -------
#
#   from otel_observability.django import instrument_django
#   instrument_django(
#       json_logs=True,           # JSON em produção; False em desenvolvimento
#       excluded_urls="/health|/readiness|/static",
#   )
#
#   from django.core.wsgi import get_wsgi_application
#   application = get_wsgi_application()
#
# Para ASGI (asgi.py):
#
#   from otel_observability.django import instrument_django
#   instrument_django(json_logs=True)
#
#   from django.core.asgi import get_asgi_application
#   application = get_asgi_application()


# ==============================================================================
# PASSO 2: Middleware em settings.py
# ==============================================================================
#
# MIDDLEWARE = [
#     "otel_observability.django.DjangoRequestLoggingMiddleware",
#     "django.middleware.security.SecurityMiddleware",
#     ...
# ]
#
# O DjangoRequestLoggingMiddleware:
# - Loga "request.completed" com method, path, status_code, duration_ms
# - Chama clear_log_context() no finally (evita vazamento entre requests)
# - Suprime /ping por padrão (configurável via skip_log_paths)


# ==============================================================================
# PASSO 3: Middleware customizado para contexto de negócio (opcional)
# ==============================================================================

import logging

from otel_observability import get_logger, set_log_context, trace
from otel_observability.django import (
    DjangoRequestLoggingMiddleware,
    add_span_attribute,
    add_span_event,
)

# Logger com correlação automática de trace_id e span_id
logger = get_logger(__name__)


class RequestContextMiddleware(DjangoRequestLoggingMiddleware):
    """
    Estende DjangoRequestLoggingMiddleware para injetar contexto de negócio.

    set_log_context() garante que todos os logs gerados durante o request
    incluam os campos definidos (user_id, tenant_id, etc.), sem precisar
    passá-los manualmente em cada logger.info().

    Adicionar em settings.py no lugar de DjangoRequestLoggingMiddleware:
        MIDDLEWARE = [
            "myapp.middleware.RequestContextMiddleware",
            ...
        ]
    """

    def _sync_call(self, request):
        set_log_context(
            user_id=getattr(getattr(request, "user", None), "id", None),
            tenant_id=request.headers.get("x-tenant-id", ""),
        )
        return super()._sync_call(request)

    async def _acall(self, request):
        set_log_context(
            user_id=getattr(getattr(request, "user", None), "id", None),
            tenant_id=request.headers.get("x-tenant-id", ""),
        )
        return await super()._acall(request)


# ==============================================================================
# PASSO 4: Views — logging e tracing
# ==============================================================================

# views.py (exemplo)
# ------------------
#
# Todos os logs abaixo saem automaticamente com trace_id e span_id no formato:
#   {"timestamp": "...", "level": "INFO", "message": "...", "trace_id": "abc123", ...}


def get_user_view(request, user_id: int):
    """View simples — instrumentação automática via DjangoInstrumentor."""
    # add_span_attribute enriquece o span do DjangoInstrumentor com dados de negócio
    add_span_attribute("user.id", user_id)

    logger.info("Fetching user", extra={"user_id": user_id})

    user = _fetch_user(user_id)

    if not user:
        logger.warning("User not found", extra={"user_id": user_id})
        # retornaria 404

    return user


def create_order_view(request):
    """View com múltiplos eventos no span."""
    # Dados do body (simplificado)
    user_id = 42
    amount = 150.0

    add_span_attribute("order.user_id", user_id)
    add_span_attribute("order.amount", amount)
    add_span_event("order.validation_started")

    logger.info("Creating order", extra={"user_id": user_id, "amount": amount})

    try:
        order = _process_order(user_id, amount)
        add_span_event("order.created", {"order_id": order["id"]})
        logger.info("Order created", extra={"order_id": order["id"]})
        return order
    except Exception:
        logger.exception("Order creation failed", extra={"user_id": user_id})
        raise


# ==============================================================================
# PASSO 5: Camada de serviço — @trace para rastrear funções de negócio
# ==============================================================================


@trace("fetch_user")
def _fetch_user(user_id: int) -> dict | None:
    """
    @trace cria um span filho do span da view.

    Logs emitidos aqui herdam o contexto: trace_id, span_id e qualquer
    campo definido via set_log_context() no middleware.
    """
    logger.debug("Querying database", extra={"user_id": user_id})

    # Simulação de query
    if user_id == 0:
        return None

    return {"id": user_id, "name": f"User {user_id}"}


@trace("process_order")
def _process_order(user_id: int, amount: float) -> dict:
    """
    Funções de serviço com @trace geram spans automáticos.

    Se a função levantar exceção, o span é marcado como ERROR
    e o stack trace é registrado no span.
    """
    logger.info("Processing order", extra={"user_id": user_id, "amount": amount})

    # Simulação de lógica de negócio
    order_id = f"ORD-{user_id}-001"

    logger.info("Order processed", extra={"order_id": order_id})
    return {"id": order_id, "status": "created", "amount": amount}


# ==============================================================================
# REFERÊNCIA: O que aparece nos logs
# ==============================================================================
#
# Com json_logs=True (produção), cada linha de log é um JSON:
#
# {
#   "timestamp": "2026-03-26T10:00:00.000Z",
#   "level": "INFO",
#   "message": "Creating order",
#   "logger": "myapp.views",
#   "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",  <- correlação automática
#   "span_id": "00f067aa0ba902b7",                    <- correlação automática
#   "service": "django-example",
#   "env": "production",
#   "version": "1.0.0",
#   "user_id": 42,        <- via set_log_context() no middleware
#   "tenant_id": "acme",  <- via set_log_context() no middleware
#   "amount": 150.0       <- via extra={}
# }
#
# Com json_logs=False (desenvolvimento), formato legível:
#
#   2026-03-26 10:00:00 INFO  [trace_id=4bf92f35 span_id=00f067aa] Creating order
