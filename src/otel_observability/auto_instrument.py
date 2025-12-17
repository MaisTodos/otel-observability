"""Auto-instrumentation para bibliotecas comuns."""

import logging

logger = logging.getLogger(__name__)

_INSTRUMENTED = set()


def auto_instrument(
    libraries: list[str] | None = None,
    exclude: list[str] | None = None,
) -> None:
    """
    Auto-instrumenta bibliotecas comuns automaticamente.

    Args:
        libraries: Lista de bibliotecas para instrumentar. Se None, instrumenta todas disponíveis.
        exclude: Lista de bibliotecas para excluir da instrumentação.

    Bibliotecas suportadas:
        - httpx: HTTP client assíncrono
        - requests: HTTP client síncrono
        - sqlalchemy: ORM
        - psycopg2: PostgreSQL driver
        - pymongo: MongoDB driver
        - redis: Redis client
        - boto3: AWS SDK

    Example:
        >>> from otel_observability.auto_instrument import auto_instrument
        >>>
        >>> # Instrumentar todas as bibliotecas disponíveis
        >>> auto_instrument()
        >>>
        >>> # Instrumentar apenas específicas
        >>> auto_instrument(libraries=["httpx", "sqlalchemy"])
        >>>
        >>> # Instrumentar todas exceto algumas
        >>> auto_instrument(exclude=["boto3"])
    """
    global _INSTRUMENTED

    available_libraries = {
        "httpx": _instrument_httpx,
        "requests": _instrument_requests,
        "sqlalchemy": _instrument_sqlalchemy,
        "psycopg2": _instrument_psycopg2,
        "pymongo": _instrument_pymongo,
        "redis": _instrument_redis,
        "boto3": _instrument_boto3,
    }

    exclude = exclude or []

    if libraries:
        to_instrument = {lib: func for lib, func in available_libraries.items() if lib in libraries}
    else:
        to_instrument = {
            lib: func for lib, func in available_libraries.items() if lib not in exclude
        }

    for lib_name, instrument_func in to_instrument.items():
        if lib_name in _INSTRUMENTED:
            logger.debug(f"{lib_name} already instrumented, skipping")
            continue

        try:
            instrument_func()
            _INSTRUMENTED.add(lib_name)
            logger.info(f"Auto-instrumented {lib_name}")
        except ImportError:
            logger.debug(f"{lib_name} not available, skipping")
        except Exception as e:
            logger.warning(f"Failed to instrument {lib_name}: {e}")


def _instrument_httpx():
    """Instrumenta httpx."""
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def _instrument_requests():
    """Instrumenta requests."""
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    RequestsInstrumentor().instrument()


def _instrument_sqlalchemy():
    """Instrumenta SQLAlchemy."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument()


def _instrument_psycopg2():
    """Instrumenta psycopg2."""
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

    Psycopg2Instrumentor().instrument()


def _instrument_pymongo():
    """Instrumenta pymongo."""
    from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

    PymongoInstrumentor().instrument()


def _instrument_redis():
    """Instrumenta redis."""
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    RedisInstrumentor().instrument()


def _instrument_boto3():
    """Instrumenta boto3."""
    from opentelemetry.instrumentation.boto3sqs import Boto3SQSInstrumentor
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

    Boto3SQSInstrumentor().instrument()
    BotocoreInstrumentor().instrument()


def get_instrumented() -> list[str]:
    """Retorna lista de bibliotecas já instrumentadas."""
    return list(_INSTRUMENTED)
