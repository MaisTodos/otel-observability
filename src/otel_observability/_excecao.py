import os
import re
import traceback
from types import TracebackType

from opentelemetry.sdk.trace import Event, ReadableSpan, SpanProcessor
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
        span.set_status(Status(StatusCode.ERROR, f"{type(exc).__name__}: {exc}"))
        span.record_exception(exc)
        return
    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
    span.add_event("exception", {"exception.type": exception_type_name(type(exc))})


_CAMPOS_COM_MENSAGEM = ("exception.message", "exception.stacktrace")
_DESCRICAO_DE_EXCECAO = re.compile(r"^[A-Za-z_][\w.]*: ")


class ExceptionSanitizingSpanProcessor(SpanProcessor):
    """Tira a mensagem da exceção de qualquer span, inclusive os que a lib não criou.

    Roda antes dos exporters, então vale para o OTLP e para quem mais ler o span.
    Mexe em `_events` e `_status` porque o SDK não expõe escrita num span já
    encerrado; o teste com o SDK real quebra se uma atualização mudar isso.
    """

    def on_end(self, span: ReadableSpan) -> None:
        if record_exception_message():
            return
        eventos = getattr(span, "_events", None)
        if eventos:
            span._events = [self._evento(e) for e in eventos]
        status = span.status
        descricao = status.description or ""
        if status.status_code is StatusCode.ERROR and _DESCRICAO_DE_EXCECAO.match(descricao):
            span._status = Status(StatusCode.ERROR, descricao.split(":", 1)[0])

    @staticmethod
    def _evento(evento: Event) -> Event:
        if evento.name != "exception" or not evento.attributes:
            return evento
        limpos = {k: v for k, v in evento.attributes.items() if k not in _CAMPOS_COM_MENSAGEM}
        return Event(evento.name, limpos, evento.timestamp)
