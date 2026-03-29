"""Testes unitários para o módulo django."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from otel_observability.config import TelemetryConfig
from otel_observability.django import (
    DJANGO_AVAILABLE,
    DjangoRequestLoggingMiddleware,
    add_span_attribute,
    add_span_event,
    instrument_django,
)


def _make_mock_request(path="/test", method="GET"):
    mock_request = MagicMock()
    mock_request.path = path
    mock_request.method = method
    return mock_request


def _make_mock_response(status_code=200):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    return mock_response


@pytest.mark.unit
class TestInstrumentDjango:
    """Testes para instrument_django."""

    def test_instrument_django_without_django_available(self):
        """Testa que levanta ImportError quando Django não está disponível."""
        with (
            patch("otel_observability.django.DJANGO_AVAILABLE", False),
            pytest.raises(ImportError, match="Django instrumentation not available"),
        ):
            instrument_django()

    @pytest.mark.skipif(not DJANGO_AVAILABLE, reason="Django instrumentation not available")
    def test_instrument_django_with_config(self, telemetry_config: TelemetryConfig):
        """Testa instrumentação com configuração customizada."""
        mock_instrumentor_class = MagicMock()
        mock_instance = MagicMock()
        mock_instrumentor_class.return_value = mock_instance

        with (
            patch("otel_observability.django.DjangoInstrumentor", mock_instrumentor_class),
            patch("otel_observability.django.init_telemetry") as mock_init,
            patch("otel_observability.django.configure_logging") as mock_configure_logs,
            patch("otel_observability.django.auto_instrument") as mock_auto_instrument,
        ):
            instrument_django(config=telemetry_config)

            mock_init.assert_called_once_with(telemetry_config)
            mock_configure_logs.assert_called_once()
            mock_auto_instrument.assert_called_once()
            mock_instance.instrument.assert_called_once()

    @pytest.mark.skipif(not DJANGO_AVAILABLE, reason="Django instrumentation not available")
    def test_instrument_django_without_logs(self):
        """Testa instrumentação sem configurar logs."""
        mock_instrumentor_class = MagicMock()
        mock_instrumentor_class.return_value = MagicMock()

        with (
            patch("otel_observability.django.DjangoInstrumentor", mock_instrumentor_class),
            patch("otel_observability.django.init_telemetry"),
            patch("otel_observability.django.configure_logging") as mock_configure_logs,
            patch("otel_observability.django.auto_instrument"),
        ):
            instrument_django(configure_logs=False)

            mock_configure_logs.assert_not_called()

    @pytest.mark.skipif(not DJANGO_AVAILABLE, reason="Django instrumentation not available")
    def test_instrument_django_with_excluded_urls(self):
        """Testa instrumentação com URLs excluídas."""
        mock_instrumentor_class = MagicMock()
        mock_instance = MagicMock()
        mock_instrumentor_class.return_value = mock_instance

        with (
            patch("otel_observability.django.DjangoInstrumentor", mock_instrumentor_class),
            patch("otel_observability.django.init_telemetry"),
            patch("otel_observability.django.configure_logging"),
            patch("otel_observability.django.auto_instrument"),
        ):
            instrument_django(excluded_urls="/health|/metrics")

            call_kwargs = mock_instance.instrument.call_args[1]
            assert call_kwargs["excluded_urls"] == "/health|/metrics"

    @pytest.mark.skipif(not DJANGO_AVAILABLE, reason="Django instrumentation not available")
    def test_instrument_django_without_auto_instrument(self):
        """Testa instrumentação sem auto-instrumentação."""
        mock_instrumentor_class = MagicMock()
        mock_instrumentor_class.return_value = MagicMock()

        with (
            patch("otel_observability.django.DjangoInstrumentor", mock_instrumentor_class),
            patch("otel_observability.django.init_telemetry"),
            patch("otel_observability.django.configure_logging"),
            patch("otel_observability.django.auto_instrument") as mock_auto_instrument,
        ):
            instrument_django(auto_instrument_libs=False)

            mock_auto_instrument.assert_not_called()


@pytest.mark.unit
class TestAddSpanAttribute:
    """Testes para add_span_attribute."""

    def test_add_span_attribute(self):
        """Testa adição de atributo ao span."""
        mock_span = MagicMock()

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            add_span_attribute("user.id", 123)

            mock_span.set_attribute.assert_called_once_with("user.id", 123)


@pytest.mark.unit
class TestAddSpanEvent:
    """Testes para add_span_event."""

    def test_add_span_event_with_attributes(self):
        """Testa adição de evento com atributos."""
        mock_span = MagicMock()

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            add_span_event("payment.processed", {"amount": 100.0})

            mock_span.add_event.assert_called_once_with(
                "payment.processed", attributes={"amount": 100.0}
            )

    def test_add_span_event_without_attributes(self):
        """Testa adição de evento sem atributos."""
        mock_span = MagicMock()

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            add_span_event("payment.processed")

            mock_span.add_event.assert_called_once_with("payment.processed", attributes={})


@pytest.mark.unit
class TestDjangoRequestLoggingMiddleware:
    """Testes para DjangoRequestLoggingMiddleware."""

    def test_logs_request_completed_with_correct_fields(self):
        """Verifica que request.completed é logado com os campos corretos."""
        mock_logger = MagicMock()
        mock_request = _make_mock_request(path="/test", method="GET")
        mock_response = _make_mock_response(status_code=200)
        get_response = MagicMock(return_value=mock_response)

        middleware = DjangoRequestLoggingMiddleware(get_response, logger=mock_logger)
        result = middleware(mock_request)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args.args[0] == "request.completed"
        extra = call_args.kwargs["extra"]
        assert extra["method"] == "GET"
        assert extra["path"] == "/test"
        assert extra["status_code"] == 200
        assert isinstance(extra["duration_ms"], int)
        assert result == mock_response

    def test_skip_log_paths_default_suppresses_ping(self):
        """Verifica que /ping não gera log com o default."""
        mock_logger = MagicMock()
        mock_request = _make_mock_request(path="/ping")
        mock_response = _make_mock_response(status_code=200)
        get_response = MagicMock(return_value=mock_response)

        middleware = DjangoRequestLoggingMiddleware(get_response, logger=mock_logger)
        middleware(mock_request)

        mock_logger.info.assert_not_called()

    def test_custom_skip_log_paths(self):
        """Verifica que skip_log_paths customizado é respeitado."""
        mock_logger = MagicMock()
        mock_request = _make_mock_request(path="/test")
        mock_response = _make_mock_response(status_code=200)
        get_response = MagicMock(return_value=mock_response)

        middleware = DjangoRequestLoggingMiddleware(
            get_response, logger=mock_logger, skip_log_paths={"/test"}
        )
        middleware(mock_request)

        mock_logger.info.assert_not_called()

    def test_clear_log_context_called_after_request(self):
        """Verifica que clear_log_context é chamado no finally após cada request."""
        mock_request = _make_mock_request()
        mock_response = _make_mock_response()
        get_response = MagicMock(return_value=mock_response)

        middleware = DjangoRequestLoggingMiddleware(get_response)

        with patch("otel_observability.django.clear_log_context") as mock_clear:
            middleware(mock_request)

        mock_clear.assert_called_once()

    def test_async_middleware_logs_request_completed(self):
        """Verifica que o caminho async loga request.completed corretamente."""
        mock_logger = MagicMock()
        mock_request = _make_mock_request(path="/test", method="POST")
        mock_response = _make_mock_response(status_code=201)

        async def async_get_response(request):
            return mock_response

        middleware = DjangoRequestLoggingMiddleware(async_get_response, logger=mock_logger)
        coro = middleware(mock_request)
        asyncio.run(coro)

        mock_logger.info.assert_called_once()
        extra = mock_logger.info.call_args.kwargs["extra"]
        assert extra["method"] == "POST"
        assert extra["path"] == "/test"
        assert extra["status_code"] == 201
        assert isinstance(extra["duration_ms"], int)

    def test_clear_log_context_called_after_async_request(self):
        """Verifica que clear_log_context é chamado no finally do caminho async."""
        mock_request = _make_mock_request()
        mock_response = _make_mock_response()

        async def async_get_response(request):
            return mock_response

        middleware = DjangoRequestLoggingMiddleware(async_get_response)

        with patch("otel_observability.django.clear_log_context") as mock_clear:
            asyncio.run(middleware(mock_request))

        mock_clear.assert_called_once()
