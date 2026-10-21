import json
import logging
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import opentelemetry.trace as trace_api
from opentelemetry.trace import StatusCode
import pytest

from otel_observability import chalice as chalice_module
from otel_observability import metrics
from otel_observability import tracer as tracer_module
from otel_observability.chalice import CHALICE_AVAILABLE, instrument_chalice
from otel_observability.config import TelemetryConfig
from otel_observability.logging import (
    ExceptionMessageFilter,
    FlattenAttributesLogRecordProcessor,
    RedactionFilter,
    init_otlp_log_export,
)
from otel_observability.tracer import get_tracer
from otel_observability.tracer import trace as trace_decorator

MARCADOR = "secret-value-123"
ENV_OPT_IN = "OTEL_RECORD_EXCEPTION_MESSAGE"


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    monkeypatch.delenv(ENV_OPT_IN, raising=False)
    chalice_module._instrumented = False
    yield
    chalice_module._instrumented = False


@pytest.fixture(name="spans")
def _spans(monkeypatch, reset_telemetry):
    """Provider global real, montado por init_telemetry, com um exporter em memória."""
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(trace_api._TRACER_PROVIDER_SET_ONCE, "_done", False)
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")
    config = TelemetryConfig.from_env()
    config.traces_enabled = False
    tracer_module.init_telemetry(config)
    exporter = InMemorySpanExporter()
    tracer_module._tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def _tudo(exporter) -> str:
    return json.dumps(
        [
            [s.status.description, [dict(e.attributes) for e in s.events]]
            for s in exporter.get_finished_spans()
        ],
        default=str,
    )


@pytest.mark.unit
class TestSpansDeQualquerOrigem:
    def test_span_filho_aberto_com_get_tracer_dentro_de_trace(self, spans):
        @trace_decorator("pai")
        def pai():
            with get_tracer("svc").start_as_current_span("filho"):
                raise ValueError(f"cpf {MARCADOR}")

        with pytest.raises(ValueError, match="cpf"):
            pai()

        assert len(spans.get_finished_spans()) == 2
        assert MARCADOR not in _tudo(spans)

    def test_uso_direto_de_get_tracer(self, spans):
        with (
            pytest.raises(ValueError, match="cpf"),
            get_tracer("svc").start_as_current_span("manual"),
        ):
            raise ValueError(f"cpf {MARCADOR}")

        (span,) = spans.get_finished_spans()
        assert span.status.status_code is StatusCode.ERROR
        assert MARCADOR not in _tudo(spans)
        assert span.events[0].attributes["exception.type"] == "ValueError"

    def test_auto_instrumentacao_do_fastapi(self, spans):
        from otel_observability.fastapi import instrument_fastapi

        app = FastAPI()
        instrument_fastapi(app, configure_logs=False, auto_instrument_libs=False)

        @app.get("/x")
        def _x():
            raise ValueError(f"cpf {MARCADOR}")

        resposta = TestClient(app, raise_server_exceptions=False).get("/x")

        assert resposta.status_code == 500
        assert spans.get_finished_spans()
        assert MARCADOR not in _tudo(spans)

    def test_descricao_escrita_pelo_consumidor_sem_formato_de_excecao_fica(self, spans):
        from opentelemetry.trace import Status

        with get_tracer("svc").start_as_current_span("manual") as span:
            span.set_status(Status(StatusCode.ERROR, "pagamento recusado"))

        (span,) = spans.get_finished_spans()
        assert span.status.description == "pagamento recusado"

    def test_opt_in_deixa_tudo_como_veio(self, spans, monkeypatch):
        monkeypatch.setenv(ENV_OPT_IN, "true")
        with (
            pytest.raises(ValueError, match="cpf"),
            get_tracer("svc").start_as_current_span("manual"),
        ):
            raise ValueError(f"cpf {MARCADOR}")

        assert MARCADOR in _tudo(spans)

    def test_init_telemetry_instala_o_processor_antes_dos_exporters(self, spans):
        processors = tracer_module._tracer_provider._active_span_processor._span_processors
        assert type(processors[0]).__name__ == "ExceptionSanitizingSpanProcessor"


@pytest.mark.unit
@pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
class TestChaliceReal:
    """O Chalice captura a exceção da view e a loga em app.log: o except do middleware não roda."""

    @staticmethod
    def _rodar(capsys, tracer):
        from chalice import Chalice
        from chalice.test import Client

        app = Chalice(app_name="app-teste")
        with (
            patch.object(chalice_module, "init_telemetry"),
            patch.object(chalice_module, "auto_instrument"),
            patch.object(chalice_module, "flush_telemetry"),
            patch.object(chalice_module, "get_tracer", return_value=tracer),
        ):
            instrument_chalice(app, configure_logs=False)

            @app.route("/x")
            def _x():
                raise ValueError(f"cpf {MARCADOR}")

            otlp = InMemoryLogExporter()
            provedor = LoggerProvider()
            provedor.add_log_record_processor(SimpleLogRecordProcessor(otlp))
            handler = LoggingHandler(logger_provider=provedor)
            handler.addFilter(ExceptionMessageFilter())
            handler.addFilter(RedactionFilter())
            logging.getLogger().addHandler(handler)
            try:
                with Client(app) as cliente:
                    resposta = cliente.http.get("/x")
            finally:
                logging.getLogger().removeHandler(handler)
        saida = capsys.readouterr()
        return resposta, saida.out + saida.err, otlp

    @staticmethod
    def _provider():
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        return exporter, provider.get_tracer("teste")

    def test_padrao_nao_vaza_e_marca_erro_so_com_o_tipo(self, capsys):
        exporter, tracer = self._provider()
        resposta, saida, otlp = self._rodar(capsys, tracer)

        assert resposta.status_code == 500
        assert "Caught exception" in saida
        assert "ValueError" in saida
        assert MARCADOR not in saida
        assert MARCADOR not in _tudo(exporter)
        assert MARCADOR not in json.dumps(
            [str(r.log_record.attributes) for r in otlp.get_finished_logs()]
        )
        (span,) = exporter.get_finished_spans()
        assert span.status.status_code is StatusCode.ERROR
        assert span.status.description == "ValueError"
        assert [e.name for e in span.events] == ["exception"]

    def test_opt_in_leva_a_mensagem(self, capsys, monkeypatch):
        monkeypatch.setenv(ENV_OPT_IN, "true")
        exporter, tracer = self._provider()
        resposta, saida, _ = self._rodar(capsys, tracer)

        assert resposta.status_code == 500
        assert MARCADOR in saida
        (span,) = exporter.get_finished_spans()
        assert span.status.status_code is StatusCode.ERROR
        assert span.status.description == f"ValueError: cpf {MARCADOR}"


@pytest.mark.unit
class TestOptInPreservaOFormato:
    def test_status_tipo_dois_pontos_mensagem_e_um_evento(self, spans, monkeypatch):
        monkeypatch.setenv(ENV_OPT_IN, "true")

        @trace_decorator("op")
        def op():
            raise ValueError(MARCADOR)

        with pytest.raises(ValueError, match=MARCADOR):
            op()

        (span,) = spans.get_finished_spans()
        assert span.status.description == f"ValueError: {MARCADOR}"
        assert len(span.events) == 1
        assert span.events[0].attributes["exception.message"] == MARCADOR


@pytest.mark.unit
class TestFlagInternaNoOtlp:
    def test_atributos_otlp_nao_levam_flags_internas(self):
        exporter = InMemoryLogExporter()
        provedor = LoggerProvider()
        provedor.add_log_record_processor(FlattenAttributesLogRecordProcessor())
        provedor.add_log_record_processor(SimpleLogRecordProcessor(exporter))
        handler = LoggingHandler(logger_provider=provedor)
        handler.addFilter(ExceptionMessageFilter())
        handler.addFilter(RedactionFilter())
        logger = logging.getLogger("flag-otlp")
        logger.propagate = False
        logger.addHandler(handler)
        try:
            raise ValueError(MARCADOR)
        except ValueError:
            logger.exception("falhou", extra={"campo": "ok"})
        logger.removeHandler(handler)

        (registro,) = exporter.get_finished_logs()
        atributos = dict(registro.log_record.attributes)
        assert atributos["campo"] == "ok"
        assert atributos["exception.type"] == "ValueError"
        assert [k for k in atributos if k.startswith("_otel")] == []


@pytest.mark.unit
class TestLogsDaPropriaLib:
    def test_metricas_logam_so_o_tipo(self, caplog, reset_metrics_module):
        cliente = MagicMock()
        for metodo in ("increment", "gauge", "histogram", "distribution", "flush"):
            getattr(cliente, metodo).side_effect = RuntimeError(MARCADOR)
        with patch.object(metrics, "_get_statsd_client", return_value=cliente):
            caplog.set_level(logging.WARNING)
            metrics.increment_counter("m")
            metrics.set_gauge("m", 1)
            metrics.record_histogram("m", 1)
            metrics.record_distribution("m", 1)
            metrics.flush()

        assert len(caplog.records) == 5
        assert MARCADOR not in caplog.text
        assert "RuntimeError" in caplog.text

    def test_falha_ao_criar_cliente_dogstatsd_loga_so_o_tipo(self, caplog, reset_metrics_module):
        modulo = MagicMock()
        modulo.DogStatsd.side_effect = RuntimeError(MARCADOR)
        with patch.dict("sys.modules", {"datadog": modulo}):
            caplog.set_level(logging.WARNING)
            metrics._get_statsd_client()

        assert MARCADOR not in caplog.text
        assert "RuntimeError" in caplog.text

    def test_auto_instrument_loga_so_o_tipo(self, caplog):
        from otel_observability import auto_instrument as ai

        def quebra():
            raise RuntimeError(MARCADOR)

        with (
            patch.object(ai, "_INSTRUMENTED", set()),
            patch.object(ai, "_instrument_httpx", quebra),
        ):
            caplog.set_level(logging.WARNING)
            ai.auto_instrument(libraries=["httpx"])

        assert MARCADOR not in caplog.text
        assert "RuntimeError" in caplog.text

    def test_flush_de_logs_loga_so_o_tipo(self, caplog):
        from otel_observability import logging as lib_logging

        provedor = MagicMock()
        provedor.force_flush.side_effect = RuntimeError(MARCADOR)
        with patch.object(lib_logging, "_logger_provider", provedor):
            caplog.set_level(logging.WARNING)
            lib_logging.flush_log_export()
            lib_logging.shutdown_log_export()

        assert MARCADOR not in caplog.text
        assert "RuntimeError" in caplog.text

    def test_endpoint_logado_sem_query_string_nem_credencial(self, caplog):
        config = MagicMock()
        config.otlp_logs_endpoint = (
            f"https://usuario:{MARCADOR}@coletor.exemplo.com:4318/v1/logs?token={MARCADOR}"
        )
        config.otlp_headers = {}
        config.export_timeout = 1.0
        root = logging.getLogger()
        antes = list(root.handlers)
        try:
            caplog.set_level(logging.INFO)
            init_otlp_log_export(config, None)
        finally:
            for h in list(root.handlers):
                if h not in antes:
                    root.removeHandler(h)

        assert "coletor.exemplo.com" in caplog.text
        assert MARCADOR not in caplog.text
        assert "usuario" not in caplog.text


@pytest.mark.unit
def test_log_de_inicializacao_nao_traz_query_string_nem_credencial(
    caplog, monkeypatch, reset_telemetry
):
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(trace_api._TRACER_PROVIDER_SET_ONCE, "_done", False)
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        f"https://usuario:{MARCADOR}@coletor.exemplo.com/v1/traces?token={MARCADOR}",
    )
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", f"https://coletor.exemplo.com/v1/logs?token={MARCADOR}"
    )
    caplog.set_level(logging.INFO)
    with (
        patch("otel_observability.tracer.BatchSpanProcessor"),
        patch("otel_observability.logging.init_otlp_log_export"),
    ):
        tracer_module.init_telemetry(TelemetryConfig.from_env())

    assert "Telemetry initialized" in caplog.text
    assert "coletor.exemplo.com" in caplog.text
    assert MARCADOR not in caplog.text
    assert "usuario" not in caplog.text


@pytest.mark.unit
@pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
class TestChaliceErroTratado:
    @staticmethod
    def _rodar(capsys, excecao):
        from chalice import Chalice
        from chalice.test import Client

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        app = Chalice(app_name="app-teste")
        with (
            patch.object(chalice_module, "init_telemetry"),
            patch.object(chalice_module, "auto_instrument"),
            patch.object(chalice_module, "flush_telemetry"),
            patch.object(chalice_module, "get_tracer", return_value=provider.get_tracer("t")),
        ):
            instrument_chalice(app, configure_logs=False)

            @app.route("/x")
            def _x():
                raise excecao

            with Client(app) as cliente:
                resposta = cliente.http.get("/x")
        capsys.readouterr()
        return resposta, exporter.get_finished_spans()

    @pytest.mark.parametrize("nome", ["BadRequestError", "NotFoundError", "ForbiddenError"])
    def test_erro_de_view_tratado_nao_marca_erro_no_span(self, capsys, nome):
        import chalice

        resposta, (span,) = self._rodar(capsys, getattr(chalice, nome)(f"cpf {MARCADOR}"))

        assert 400 <= resposta.status_code < 500
        assert span.status.status_code is not StatusCode.ERROR
        assert MARCADOR not in _tudo_de(span)

    def test_erro_nao_tratado_marca_erro(self, capsys):
        resposta, (span,) = self._rodar(capsys, ValueError(f"cpf {MARCADOR}"))

        assert resposta.status_code == 500
        assert span.status.status_code is StatusCode.ERROR


def _tudo_de(span) -> str:
    return json.dumps([span.status.description, [dict(e.attributes) for e in span.events]])
