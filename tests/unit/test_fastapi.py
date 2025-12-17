"""Testes unitários para o módulo fastapi."""

from unittest.mock import MagicMock, patch

import pytest

from otel_observability.config import TelemetryConfig
from otel_observability.fastapi import (
    FASTAPI_AVAILABLE,
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
