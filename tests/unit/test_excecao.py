"""A mensagem da exceção não sai em log nem em span, a não ser com opt-in."""

import io
import json
import logging
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
import pytest

from otel_observability import aws_lambda as aws_lambda_module
from otel_observability import chalice as chalice_module
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability.chalice import instrument_chalice, trace_sqs_message
from otel_observability.logging import (
    ExceptionMessageFilter,
    JSONFormatter,
    RedactionFilter,
)
from otel_observability.tracer import trace as trace_decorator

MARCADOR = "secret-value-123"
ENV_OPT_IN = "OTEL_RECORD_EXCEPTION_MESSAGE"


@pytest.fixture(name="exporter")
def _exporter():
    return InMemorySpanExporter()


@pytest.fixture(name="provider")
def _provider(exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


@pytest.fixture(name="log_stream")
def _log_stream():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(ExceptionMessageFilter())
    handler.addFilter(RedactionFilter())
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    nivel = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    yield stream
    root.removeHandler(handler)
    root.setLevel(nivel)


def _tudo_do_span(exporter) -> str:
    (span,) = exporter.get_finished_spans()
    eventos = [(e.name, dict(e.attributes)) for e in span.events]
    return json.dumps([span.status.description, eventos], default=str)


def _afirmar_span_sem_marcador(exporter):
    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "ValueError"
    assert MARCADOR not in _tudo_do_span(exporter)
    (evento,) = span.events
    assert evento.name == "exception"
    assert evento.attributes["exception.type"] == "ValueError"
    assert "exception.message" not in evento.attributes
    assert "exception.stacktrace" not in evento.attributes


def _afirmar_span_com_marcador(exporter):
    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert MARCADOR in span.status.description
    (evento,) = span.events
    assert MARCADOR in evento.attributes["exception.message"]


def _falha():
    raise ValueError(f"cpf {MARCADOR} invalido")


def _chalice_middleware(provider):
    app = MagicMock()
    capturado = []
    app.app_name = "app-teste"
    app.middleware.side_effect = lambda _tipo: lambda fn: capturado.append(fn) or fn
    with (
        patch.object(chalice_module, "init_telemetry"),
        patch.object(chalice_module, "configure_logging"),
        patch.object(chalice_module, "auto_instrument"),
    ):
        instrument_chalice(app)
    return capturado[0]


def _evento_http():
    evento = MagicMock()
    evento.method = "GET"
    evento.path = "/x"
    evento.headers = {}
    return evento


def _disparar(ponto, provider):
    tracer = provider.get_tracer("teste")
    modulo = {
        "lambda": "otel_observability.aws_lambda.get_tracer",
        "chalice_http": "otel_observability.chalice.get_tracer",
        "chalice_sqs": "otel_observability.chalice.get_tracer",
        "tracer_sync": "otel_observability.tracer.get_tracer",
        "tracer_async": "otel_observability.tracer.get_tracer",
    }[ponto]
    with (
        patch(modulo, return_value=tracer),
        patch("otel_observability.aws_lambda.flush_telemetry"),
        patch("otel_observability.chalice.flush_telemetry"),
    ):
        if ponto == "lambda":
            aws_lambda_module._instrumented = False
            handler = MagicMock(side_effect=ValueError(f"cpf {MARCADOR} invalido"))
            handler.__name__ = "h"
            contexto = MagicMock()
            contexto.function_name = "fn"
            with (
                patch.object(aws_lambda_module, "init_telemetry"),
                patch.object(aws_lambda_module, "configure_logging"),
                patch.object(aws_lambda_module, "auto_instrument"),
            ):
                decorado = instrument_lambda_handler()(handler)
            with pytest.raises(ValueError, match="invalido"):
                decorado({}, contexto)
        elif ponto == "chalice_http":
            middleware = _chalice_middleware(provider)
            resposta = MagicMock(side_effect=ValueError(f"cpf {MARCADOR} invalido"))
            with pytest.raises(ValueError, match="invalido"):
                middleware(_evento_http(), resposta)
        elif ponto == "chalice_sqs":
            handler = MagicMock(side_effect=ValueError(f"cpf {MARCADOR} invalido"))
            with pytest.raises(ValueError, match="invalido"):
                trace_sqs_message(handler)({"messageId": "m1"})
        elif ponto == "tracer_sync":
            with pytest.raises(ValueError, match="invalido"):
                trace_decorator("op")(_falha)()
        else:

            async def _afalha():
                _falha()

            import asyncio

            with pytest.raises(ValueError, match="invalido"):
                asyncio.run(trace_decorator("op")(_afalha)())


PONTOS = ["tracer_sync", "tracer_async", "lambda", "chalice_http", "chalice_sqs"]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv(ENV_OPT_IN, raising=False)
    chalice_module._instrumented = False
    aws_lambda_module._instrumented = False
    yield
    chalice_module._instrumented = False
    aws_lambda_module._instrumented = False


@pytest.mark.unit
class TestSpan:
    @pytest.mark.parametrize("ponto", PONTOS)
    def test_padrao_nao_vaza_mensagem_no_span(self, ponto, provider, exporter):
        _disparar(ponto, provider)
        _afirmar_span_sem_marcador(exporter)

    @pytest.mark.parametrize("ponto", PONTOS)
    def test_opt_in_restaura_mensagem_no_span(self, ponto, provider, exporter, monkeypatch):
        monkeypatch.setenv(ENV_OPT_IN, "true")
        _disparar(ponto, provider)
        _afirmar_span_com_marcador(exporter)

    @pytest.mark.parametrize("valor", ["false", "1", "yes", ""])
    def test_so_true_liga_o_opt_in(self, valor, provider, exporter, monkeypatch):
        monkeypatch.setenv(ENV_OPT_IN, valor)
        _disparar("tracer_sync", provider)
        _afirmar_span_sem_marcador(exporter)


@pytest.mark.unit
class TestLog:
    @pytest.mark.parametrize("ponto", ["lambda", "chalice_http", "chalice_sqs"])
    def test_padrao_nao_vaza_mensagem_no_log(self, ponto, provider, log_stream):
        _disparar(ponto, provider)
        saida = log_stream.getvalue()
        assert saida
        assert MARCADOR not in saida
        registro = json.loads(saida.splitlines()[-1])
        assert "ValueError" in registro["exception"]
        assert "File " in registro["exception"]

    @pytest.mark.parametrize("ponto", ["lambda", "chalice_http", "chalice_sqs"])
    def test_opt_in_restaura_mensagem_no_log(self, ponto, provider, log_stream, monkeypatch):
        monkeypatch.setenv(ENV_OPT_IN, "true")
        _disparar(ponto, provider)
        assert MARCADOR in log_stream.getvalue()

    def test_logger_do_consumidor_tambem_e_coberto(self, log_stream):
        try:
            _falha()
        except ValueError:
            logging.getLogger("consumidor").exception("falhou")
        assert MARCADOR not in log_stream.getvalue()

    def test_json_formatter_sozinho_nao_grava_mensagem(self):
        try:
            _falha()
        except ValueError:
            import sys

            registro = logging.LogRecord("n", logging.ERROR, "f", 1, "m", None, sys.exc_info())
        assert MARCADOR not in JSONFormatter().format(registro)

    def test_texto_comum_sem_json_tambem_sem_mensagem(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(ExceptionMessageFilter())
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger("texto-comum")
        logger.propagate = False
        logger.addHandler(handler)
        try:
            _falha()
        except ValueError:
            logger.exception("falhou")
        assert MARCADOR not in stream.getvalue()
        assert "ValueError" in stream.getvalue()

    def test_atributos_otlp_levam_tipo_e_frames_sem_mensagem(self):
        """O handler OTLP lê atributos do record: o filtro tem que deixá-los limpos."""
        try:
            _falha()
        except ValueError:
            import sys

            registro = logging.LogRecord("n", logging.ERROR, "f", 1, "m", None, sys.exc_info())
        ExceptionMessageFilter().filter(registro)
        assert registro.exc_info is None
        assert registro.__dict__["exception.type"] == "ValueError"
        assert MARCADOR not in json.dumps(registro.__dict__, default=str)

    def test_filtro_idempotente_nos_dois_handlers(self):
        try:
            _falha()
        except ValueError:
            import sys

            registro = logging.LogRecord("n", logging.ERROR, "f", 1, "m", None, sys.exc_info())
        filtro = ExceptionMessageFilter()
        filtro.filter(registro)
        primeiro = registro.exc_text
        filtro.filter(registro)
        assert registro.exc_text == primeiro


@pytest.mark.unit
class TestLogOtlp:
    @staticmethod
    def _emitir():
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import (
            InMemoryLogExporter,
            SimpleLogRecordProcessor,
        )

        exporter = InMemoryLogExporter()
        provider = LoggerProvider()
        provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
        handler = LoggingHandler(logger_provider=provider)
        handler.addFilter(ExceptionMessageFilter())
        handler.addFilter(RedactionFilter())
        logger = logging.getLogger("otlp-real")
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            _falha()
        except ValueError:
            logger.exception("falhou")
        logger.removeHandler(handler)
        (registro,) = exporter.get_finished_logs()
        return registro.log_record

    def test_padrao_sem_mensagem_nos_atributos(self):
        registro = self._emitir()
        assert MARCADOR not in json.dumps(dict(registro.attributes), default=str)
        assert registro.attributes["exception.type"] == "ValueError"

    def test_opt_in_leva_mensagem(self, monkeypatch):
        monkeypatch.setenv(ENV_OPT_IN, "true")
        registro = self._emitir()
        assert MARCADOR in json.dumps(dict(registro.attributes), default=str)
