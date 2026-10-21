import os
import traceback
from types import TracebackType

from opentelemetry.trace import Span, Status, StatusCode

ENV_RECORD_MESSAGE = "OTEL_RECORD_EXCEPTION_MESSAGE"

# `start_as_current_span` registra a exceção sozinho na saída do `with`, com a
# mensagem; estes kwargs desligam isso para o helper ser a única via.
SPAN_SEM_REGISTRO_AUTOMATICO = {"record_exception": False, "set_status_on_exception": False}


def record_exception_message() -> bool:
    return os.getenv(ENV_RECORD_MESSAGE, "false").lower() == "true"


def exception_type_name(exc_type: type[BaseException]) -> str:
    module = exc_type.__module__
    if module in ("builtins", "__main__"):
        return exc_type.__qualname__
    return f"{module}.{exc_type.__qualname__}"


def safe_exception_text(exc_type: type[BaseException], tb: TracebackType | None) -> str:
    linhas = []
    if tb is not None:
        linhas.append("Traceback (most recent call last):")
        for frame in traceback.extract_tb(tb):
            linhas.append(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}')
    linhas.append(exception_type_name(exc_type))
    return "\n".join(linhas)


def mark_span_error(span: Span, exc: BaseException) -> None:
    if record_exception_message():
        span.set_status(Status(StatusCode.ERROR, str(exc)))
        span.record_exception(exc)
        return
    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
    span.add_event("exception", {"exception.type": exception_type_name(type(exc))})
