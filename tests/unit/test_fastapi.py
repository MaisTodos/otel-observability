"""Testes unitários para o módulo fastapi."""

import logging
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
import pytest
from starlette.testclient import TestClient

from otel_observability.config import TelemetryConfig
from otel_observability.fastapi import (
    FASTAPI_AVAILABLE,
    RequestLoggingMiddleware,
    add_span_attribute,
    add_span_event,
    instrument_fastapi,
)


@pytest.mark.unit
class TestInstrumentFastapi:
    """Testes para instrument_fastapi."""

    def test_instrument_fastapi_without_fastapi_available(self):
        """Testa que levanta ImportError quando FastAPI não está disponível."""
        with patch("otel_observability.fastapi.FASTAPI_AVAILABLE", False):
            mock_app = MagicMock()

            with pytest.raises(ImportError, match="FastAPI instrumentation not available"):
                instrument_fastapi(mock_app)

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI instrumentation not available")
    def test_instrument_fastapi_with_config(self, telemetry_config: TelemetryConfig):
        """Testa instrumentação com configuração customizada."""
        mock_app = MagicMock()
        mock_instrumentor = MagicMock()

        with (
            patch("otel_observability.fastapi.FastAPIInstrumentor", mock_instrumentor),
            patch("otel_observability.fastapi.init_telemetry") as mock_init,
            patch("otel_observability.fastapi.configure_logging") as mock_configure_logs,
            patch("otel_observability.fastapi.auto_instrument") as mock_auto_instrument,
        ):
            mock_instrumentor.instrument_app = MagicMock()

            instrument_fastapi(mock_app, config=telemetry_config)

            mock_init.assert_called_once_with(telemetry_config)
            mock_configure_logs.assert_called_once()
            mock_auto_instrument.assert_called_once()
            mock_instrumentor.instrument_app.assert_called_once()

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI instrumentation not available")
    def test_instrument_fastapi_without_logs(self):
        """Testa instrumentação sem configurar logs."""
        mock_app = MagicMock()
        mock_instrumentor = MagicMock()

        with (
            patch("otel_observability.fastapi.FastAPIInstrumentor", mock_instrumentor),
            patch("otel_observability.fastapi.init_telemetry"),
            patch("otel_observability.fastapi.configure_logging") as mock_configure_logs,
            patch("otel_observability.fastapi.auto_instrument"),
        ):
            mock_instrumentor.instrument_app = MagicMock()

            instrument_fastapi(mock_app, configure_logs=False)

            mock_configure_logs.assert_not_called()

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI instrumentation not available")
    def test_instrument_fastapi_with_excluded_urls(self):
        """Testa instrumentação com URLs excluídas."""
        mock_app = MagicMock()
        mock_instrumentor = MagicMock()
        access_logger = logging.getLogger("uvicorn.access")
        before = list(access_logger.filters)

        try:
            with (
                patch("otel_observability.fastapi.FastAPIInstrumentor", mock_instrumentor),
                patch("otel_observability.fastapi.init_telemetry"),
                patch("otel_observability.fastapi.configure_logging"),
                patch("otel_observability.fastapi.auto_instrument"),
            ):
                mock_instrumentor.instrument_app = MagicMock()

                instrument_fastapi(mock_app, excluded_urls="/health|/metrics")

                call_args = mock_instrumentor.instrument_app.call_args
                assert call_args[1]["excluded_urls"] == "/health|/metrics"
        finally:
            access_logger.filters = before

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI instrumentation not available")
    def test_instrument_fastapi_without_auto_instrument(self):
        """Testa instrumentação sem auto-instrumentação."""
        mock_app = MagicMock()
        mock_instrumentor = MagicMock()

        with (
            patch("otel_observability.fastapi.FastAPIInstrumentor", mock_instrumentor),
            patch("otel_observability.fastapi.init_telemetry"),
            patch("otel_observability.fastapi.configure_logging"),
            patch("otel_observability.fastapi.auto_instrument") as mock_auto_instrument,
        ):
            mock_instrumentor.instrument_app = MagicMock()

            instrument_fastapi(mock_app, auto_instrument_libs=False)

            mock_auto_instrument.assert_not_called()

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI instrumentation not available")
    def test_instrument_fastapi_suppresses_access_logs(self):
        """excluded_urls instala o filtro de supressão no uvicorn.access."""
        from otel_observability.fastapi import _AccessLogPathFilter

        mock_app = MagicMock()
        mock_instrumentor = MagicMock()
        access_logger = logging.getLogger("uvicorn.access")
        before = list(access_logger.filters)

        def count_filter():
            return sum(isinstance(f, _AccessLogPathFilter) for f in access_logger.filters)

        before_count = count_filter()
        try:
            with (
                patch("otel_observability.fastapi.FastAPIInstrumentor", mock_instrumentor),
                patch("otel_observability.fastapi.init_telemetry"),
                patch("otel_observability.fastapi.configure_logging"),
                patch("otel_observability.fastapi.auto_instrument"),
            ):
                mock_instrumentor.instrument_app = MagicMock()
                instrument_fastapi(mock_app, excluded_urls="/ping")

            assert count_filter() == before_count + 1
        finally:
            access_logger.filters = before

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI instrumentation not available")
    def test_instrument_fastapi_suppress_access_logs_disabled(self):
        """suppress_access_logs=False não instala o filtro."""
        from otel_observability.fastapi import _AccessLogPathFilter

        mock_app = MagicMock()
        mock_instrumentor = MagicMock()
        access_logger = logging.getLogger("uvicorn.access")
        before = list(access_logger.filters)

        def count_filter():
            return sum(isinstance(f, _AccessLogPathFilter) for f in access_logger.filters)

        before_count = count_filter()
        try:
            with (
                patch("otel_observability.fastapi.FastAPIInstrumentor", mock_instrumentor),
                patch("otel_observability.fastapi.init_telemetry"),
                patch("otel_observability.fastapi.configure_logging"),
                patch("otel_observability.fastapi.auto_instrument"),
            ):
                mock_instrumentor.instrument_app = MagicMock()
                instrument_fastapi(mock_app, excluded_urls="/ping", suppress_access_logs=False)

            assert count_filter() == before_count
        finally:
            access_logger.filters = before


def test_instrument_fastapi_respeita_otel_log_format(monkeypatch, mocker, reset_telemetry):
    """OTEL_LOG_FORMAT=json liga log JSON no FastAPI sem parâmetro explícito."""
    import otel_observability.tracer as tracer_module

    # init_telemetry tem guarda de idempotência sobre globais de módulo — resetar
    # antes para a instrumentação não virar no-op; a fixture reset_telemetry limpa depois.
    tracer_module._tracer_provider = None
    tracer_module._config = None

    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")
    monkeypatch.setenv("OTEL_LOG_FORMAT", "json")
    spy = mocker.patch("otel_observability.fastapi.configure_logging")

    instrument_fastapi(FastAPI())

    assert spy.call_args.kwargs["json_format"] is True


@pytest.mark.unit
class TestAccessLogPathFilter:
    """Testes para o filtro de supressão de access log por path."""

    def test_drops_excluded_path(self):
        from otel_observability.fastapi import _AccessLogPathFilter

        f = _AccessLogPathFilter("/ping")
        rec = _access_record("/ping")
        assert f.filter(rec) is False

    def test_keeps_other_path(self):
        from otel_observability.fastapi import _AccessLogPathFilter

        f = _AccessLogPathFilter("/ping")
        rec = _access_record("/accounts")
        assert f.filter(rec) is True

    def test_parses_pipe_and_comma_separators(self):
        """Vírgula separa; pipe vira alternância de regex (semântica do OTel)."""
        from otel_observability.fastapi import _AccessLogPathFilter

        f = _AccessLogPathFilter("/health|/metrics, /ping")
        for path in ("/health", "/metrics", "/ping"):
            rec = _access_record(path)
            assert f.filter(rec) is False


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:0", "GET", path, "1.1", 200),
        exc_info=None,
    )


def test_filtro_suprime_path_excluido():
    from otel_observability.fastapi import _AccessLogPathFilter

    f = _AccessLogPathFilter("/ping")
    assert f.filter(_access_record("/ping")) is False


def test_filtro_nao_suprime_path_de_negocio():
    from otel_observability.fastapi import _AccessLogPathFilter

    f = _AccessLogPathFilter("/ping")
    assert f.filter(_access_record("/api/v1/accounts")) is True


def test_filtro_ignora_ocorrencia_fora_do_path():
    """Antes: a substring '/ping' no user-agent derrubava o log. Agora não."""
    from otel_observability.fastapi import _AccessLogPathFilter

    f = _AccessLogPathFilter("/ping")
    record = _access_record("/api/v1/accounts")
    record.args = ("bot/ping-checker", "GET", "/api/v1/accounts", "1.1", 200)
    assert f.filter(record) is True


def test_filtro_deixa_passar_record_sem_args_esperados():
    from otel_observability.fastapi import _AccessLogPathFilter

    f = _AccessLogPathFilter("/ping")
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "texto solto", (), None)
    assert f.filter(record) is True


@pytest.mark.unit
class TestAddSpanAttribute:
    """Testes para add_span_attribute."""

    def test_add_span_attribute(self):
        """Testa adição de atributo ao span."""
        mock_span = MagicMock()
        mock_trace_module = MagicMock()
        mock_trace_module.get_current_span.return_value = mock_span

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            add_span_attribute("user.id", 123)

            mock_span.set_attribute.assert_called_once_with("user.id", 123)


@pytest.mark.unit
class TestAddSpanEvent:
    """Testes para add_span_event."""

    def test_add_span_event_with_attributes(self):
        """Testa adição de evento com atributos."""
        mock_span = MagicMock()
        mock_trace_module = MagicMock()
        mock_trace_module.get_current_span.return_value = mock_span

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            add_span_event("payment.processed", {"amount": 100.0})

            mock_span.add_event.assert_called_once_with(
                "payment.processed", attributes={"amount": 100.0}
            )

    def test_add_span_event_without_attributes(self):
        """Testa adição de evento sem atributos."""
        mock_span = MagicMock()
        mock_trace_module = MagicMock()
        mock_trace_module.get_current_span.return_value = mock_span

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            add_span_event("payment.processed")

            mock_span.add_event.assert_called_once_with("payment.processed", attributes={})


def _build_logging_app(logger, skip_log_paths=None) -> FastAPI:
    app = FastAPI()

    @app.get("/test")
    async def test_route():
        return {"ok": True}

    @app.get("/ping")
    async def ping_route():
        return {"ok": True}

    kwargs = {"logger": logger}
    if skip_log_paths is not None:
        kwargs["skip_log_paths"] = skip_log_paths
    app.add_middleware(RequestLoggingMiddleware, **kwargs)
    return app


@pytest.mark.unit
class TestRequestLoggingMiddleware:
    """Testes para RequestLoggingMiddleware."""

    def test_logs_request_completed_with_correct_fields(self):
        """Verifica que request.completed é logado com os campos corretos."""
        mock_logger = MagicMock()
        client = TestClient(_build_logging_app(mock_logger), raise_server_exceptions=False)

        client.get("/test")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args.args[0] == "request.completed"
        extra = call_args.kwargs["extra"]
        assert extra["method"] == "GET"
        assert extra["path"] == "/test"
        assert extra["status_code"] == 200
        assert isinstance(extra["duration_ms"], int)

    def test_skip_log_paths_default_suppresses_ping(self):
        """Verifica que /ping não gera log com o default."""
        mock_logger = MagicMock()
        client = TestClient(_build_logging_app(mock_logger), raise_server_exceptions=False)

        client.get("/ping")

        mock_logger.info.assert_not_called()

    def test_custom_skip_log_paths(self):
        """Verifica que skip_log_paths customizado é respeitado."""
        mock_logger = MagicMock()
        client = TestClient(
            _build_logging_app(mock_logger, skip_log_paths={"/test"}),
            raise_server_exceptions=False,
        )

        client.get("/test")

        mock_logger.info.assert_not_called()

    def test_clear_log_context_called_after_request(self):
        """Verifica que clear_log_context é chamado no finally após cada request."""
        mock_logger = MagicMock()
        client = TestClient(_build_logging_app(mock_logger), raise_server_exceptions=False)

        with patch("otel_observability.fastapi.clear_log_context") as mock_clear:
            client.get("/test")

        mock_clear.assert_called_once()
