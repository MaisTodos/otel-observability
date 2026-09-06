"""Testes unitários para o módulo chalice."""

from unittest.mock import MagicMock, patch

import pytest

from otel_observability import chalice as chalice_module
from otel_observability.chalice import (
    CHALICE_AVAILABLE,
    _extract_sqs_carrier,
    instrument_chalice,
    trace_sqs_message,
)
from otel_observability.config import TelemetryConfig


@pytest.fixture(autouse=True)
def _reset_chalice_instrumented():
    """Reseta flag global _instrumented entre testes."""
    chalice_module._instrumented = False
    yield
    chalice_module._instrumented = False


@pytest.mark.unit
class TestInstrumentChalice:
    """Testes para instrument_chalice."""

    def test_instrument_chalice_without_chalice_available(self):
        """Testa que levanta ImportError quando Chalice não está disponível."""
        with patch("otel_observability.chalice.CHALICE_AVAILABLE", False):
            mock_app = MagicMock()

            with pytest.raises(ImportError, match="Chalice instrumentation not available"):
                instrument_chalice(mock_app)

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_instrument_chalice_with_config(self, telemetry_config: TelemetryConfig):
        """Testa instrumentação com configuração customizada."""
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        mock_app.middleware = MagicMock()

        with (
            patch("otel_observability.chalice.init_telemetry") as mock_init,
            patch("otel_observability.chalice.configure_logging") as mock_configure_logs,
            patch("otel_observability.chalice.auto_instrument") as mock_auto_instrument,
        ):
            instrument_chalice(mock_app, config=telemetry_config)

            mock_init.assert_called_once_with(telemetry_config)
            mock_configure_logs.assert_called_once()
            mock_auto_instrument.assert_called_once()
            mock_app.middleware.assert_called_once_with("http")

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_instrument_chalice_without_logs(self):
        """Testa instrumentação sem configurar logs."""
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        mock_app.middleware = MagicMock()

        with (
            patch("otel_observability.chalice.init_telemetry"),
            patch("otel_observability.chalice.configure_logging") as mock_configure_logs,
            patch("otel_observability.chalice.auto_instrument"),
        ):
            instrument_chalice(mock_app, configure_logs=False)

            mock_configure_logs.assert_not_called()
            mock_app.middleware.assert_called_once()

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_instrument_chalice_without_auto_instrument(self):
        """Testa instrumentação sem auto-instrumentação."""
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        mock_app.middleware = MagicMock()

        with (
            patch("otel_observability.chalice.init_telemetry"),
            patch("otel_observability.chalice.configure_logging"),
            patch("otel_observability.chalice.auto_instrument") as mock_auto_instrument,
        ):
            instrument_chalice(mock_app, auto_instrument_libs=False)

            mock_auto_instrument.assert_not_called()
            mock_app.middleware.assert_called_once()

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_instrument_chalice_idempotent(self):
        """Testa que instrumentar múltiplas vezes não causa problemas."""
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        mock_app.middleware = MagicMock()

        with (
            patch("otel_observability.chalice.init_telemetry"),
            patch("otel_observability.chalice.configure_logging"),
            patch("otel_observability.chalice.auto_instrument"),
        ):
            # Primeira chamada
            instrument_chalice(mock_app)
            first_call_count = mock_app.middleware.call_count

            # Segunda chamada (deve ser ignorada)
            instrument_chalice(mock_app)
            second_call_count = mock_app.middleware.call_count

            # Deve ter chamado apenas uma vez
            assert first_call_count == second_call_count == 1

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_instrument_chalice_middleware_http_request(self):
        """Testa que o middleware HTTP cria spans corretamente."""
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        captured_middleware = []

        def fake_middleware_decorator(event_type):
            def decorator(func):
                captured_middleware.append(func)
                return func

            return decorator

        mock_app.middleware = MagicMock(side_effect=fake_middleware_decorator)

        mock_event = MagicMock()
        mock_event.method = "GET"
        mock_event.path = "/users/123"
        mock_event.headers = {"user-agent": "test-agent", "traceparent": "00-abc-123-01"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get_response = MagicMock(return_value=mock_response)

        with (
            patch("otel_observability.chalice.init_telemetry"),
            patch("otel_observability.chalice.configure_logging"),
            patch("otel_observability.chalice.auto_instrument"),
            patch("otel_observability.chalice.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach") as mock_attach,
            patch("opentelemetry.context.detach") as mock_detach,
            patch("opentelemetry.context.get_current") as mock_get_current,
            patch("opentelemetry.propagate.extract") as mock_extract,
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
            mock_get_tracer.return_value = mock_tracer
            mock_token = MagicMock()
            mock_attach.return_value = mock_token
            mock_get_current.return_value = MagicMock()
            mock_extract.return_value = MagicMock()

            # Registrar middleware
            instrument_chalice(mock_app)

            # Obter o middleware registrado
            middleware_func = captured_middleware[0]

            # Chamar o middleware
            result = middleware_func(mock_event, mock_get_response)

            assert result == mock_response
            mock_get_tracer.assert_called_once()
            mock_span.set_attribute.assert_any_call("http.method", "GET")
            mock_span.set_attribute.assert_any_call("http.route", "/users/123")
            mock_span.set_attribute.assert_any_call("http.target", "/users/123")
            mock_span.set_attribute.assert_any_call("http.user_agent", "test-agent")
            mock_span.set_attribute.assert_any_call("http.status_code", 200)
            mock_span.set_status.assert_called_once()
            mock_attach.assert_called_once()
            mock_detach.assert_called_once()

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_instrument_chalice_middleware_with_exception(self):
        """Testa que o middleware trata exceções corretamente."""
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        captured_middleware = []

        def fake_middleware_decorator(event_type):
            def decorator(func):
                captured_middleware.append(func)
                return func

            return decorator

        mock_app.middleware = MagicMock(side_effect=fake_middleware_decorator)

        mock_event = MagicMock()
        mock_event.method = "POST"
        mock_event.path = "/users"
        mock_event.headers = {}

        test_error = ValueError("Test error")
        mock_get_response = MagicMock(side_effect=test_error)

        with (
            patch("otel_observability.chalice.init_telemetry"),
            patch("otel_observability.chalice.configure_logging"),
            patch("otel_observability.chalice.auto_instrument"),
            patch("otel_observability.chalice.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach") as mock_attach,
            patch("opentelemetry.context.detach"),
            patch("opentelemetry.context.get_current") as mock_get_current,
            patch("opentelemetry.propagate.extract") as mock_extract,
            patch("otel_observability.chalice.logger") as mock_logger,
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
            mock_get_tracer.return_value = mock_tracer
            mock_token = MagicMock()
            mock_attach.return_value = mock_token
            mock_get_current.return_value = MagicMock()
            mock_extract.return_value = MagicMock()

            instrument_chalice(mock_app)
            middleware_func = captured_middleware[0]

            with pytest.raises(ValueError, match="Test error"):
                middleware_func(mock_event, mock_get_response)

            mock_span.set_status.assert_called_once()
            mock_span.record_exception.assert_called_once_with(test_error)
            mock_logger.exception.assert_called_once()

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_instrument_chalice_middleware_health_check(self):
        """Testa que health checks são identificados corretamente."""
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        captured_middleware = []

        def fake_middleware_decorator(event_type):
            def decorator(func):
                captured_middleware.append(func)
                return func

            return decorator

        mock_app.middleware = MagicMock(side_effect=fake_middleware_decorator)

        mock_event = MagicMock()
        mock_event.method = "GET"
        mock_event.path = "/health"
        mock_event.headers = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get_response = MagicMock(return_value=mock_response)

        with (
            patch("otel_observability.chalice.init_telemetry"),
            patch("otel_observability.chalice.configure_logging"),
            patch("otel_observability.chalice.auto_instrument"),
            patch("otel_observability.chalice.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach"),
            patch("opentelemetry.context.detach"),
            patch("opentelemetry.context.get_current"),
            patch("opentelemetry.propagate.extract"),
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
            mock_get_tracer.return_value = mock_tracer

            instrument_chalice(mock_app)
            middleware_func = captured_middleware[0]
            middleware_func(mock_event, mock_get_response)

            mock_span.set_attribute.assert_any_call("request.is_health_check", True)

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_redact_keys_chega_no_configure_logging(self, mocker, reset_telemetry):
        """redact_keys chega ao configure_logging."""
        spy = mocker.patch("otel_observability.chalice.configure_logging")
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        mock_app.middleware = MagicMock()

        instrument_chalice(mock_app, redact_keys=["cpf_do_cliente"], auto_instrument_libs=False)

        assert spy.call_args.kwargs["redact_keys"] == ["cpf_do_cliente"]

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_configure_logging_roda_antes_de_init_telemetry(self, mocker):
        """Ordem importa: init_telemetry instala o handler OTLP e configure_logging
        faz handlers.clear(). Invertido, o log nunca sai via OTLP."""
        manager = mocker.MagicMock()
        manager.attach_mock(mocker.patch("otel_observability.chalice.configure_logging"), "cfg_log")
        manager.attach_mock(mocker.patch("otel_observability.chalice.init_telemetry"), "init")
        mock_app = MagicMock()
        mock_app.app_name = "test-app"
        mock_app.middleware = MagicMock()

        instrument_chalice(mock_app, auto_instrument_libs=False)

        nomes = [c[0] for c in manager.mock_calls]
        assert nomes.index("cfg_log") < nomes.index("init")


@pytest.mark.unit
class TestTraceSqsMessage:
    """Testes para trace_sqs_message."""

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_trace_sqs_message_basic(self):
        """Testa tracing básico de mensagem SQS."""
        mock_event = {
            "messageId": "msg-123",
            "body": '{"test": "data"}',
            "eventSourceARN": "arn:aws:sqs:us-east-1:123456789:test-queue",
        }

        mock_handler = MagicMock(return_value={"status": "processed"})

        with (
            patch("otel_observability.chalice.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach") as mock_attach,
            patch("opentelemetry.context.detach"),
            patch("opentelemetry.context.get_current") as mock_get_current,
            patch("opentelemetry.propagate.extract") as mock_extract,
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
            mock_get_tracer.return_value = mock_tracer
            mock_token = MagicMock()
            mock_attach.return_value = mock_token
            mock_get_current.return_value = MagicMock()
            mock_extract.return_value = MagicMock()

            decorated_handler = trace_sqs_message(mock_handler)
            result = decorated_handler(mock_event)

            assert result == {"status": "processed"}
            mock_handler.assert_called_once_with(mock_event)
            mock_span.set_attribute.assert_any_call("messaging.system", "aws_sqs")
            mock_span.set_attribute.assert_any_call("messaging.operation", "process")
            mock_span.set_attribute.assert_any_call("messaging.message.id", "msg-123")
            mock_span.set_attribute.assert_any_call("messaging.destination.name", "test-queue")
            mock_span.set_status.assert_called_once()

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_trace_sqs_message_with_trace_context(self):
        """Testa tracing com trace context extraído."""
        mock_event = {
            "messageId": "msg-123",
            "messageAttributes": {
                "traceparent": {"stringValue": "00-abc-123-01"},
                "tracestate": {"stringValue": "key=value"},
            },
            "eventSourceARN": "arn:aws:sqs:us-east-1:123456789:test-queue",
        }

        mock_handler = MagicMock(return_value={"status": "processed"})

        with (
            patch("otel_observability.chalice.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach") as mock_attach,
            patch("opentelemetry.context.detach"),
            patch("opentelemetry.context.get_current") as mock_get_current,
            patch("opentelemetry.propagate.extract") as mock_extract,
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
            mock_get_tracer.return_value = mock_tracer
            mock_token = MagicMock()
            mock_attach.return_value = mock_token
            mock_get_current.return_value = MagicMock()
            mock_extract.return_value = MagicMock()

            decorated_handler = trace_sqs_message(mock_handler)
            decorated_handler(mock_event)

            mock_span.set_attribute.assert_any_call("messaging.message.attributes_count", 2)

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_trace_sqs_message_with_exception(self):
        """Testa tracing quando handler levanta exceção."""
        mock_event = {
            "messageId": "msg-123",
            "body": '{"test": "data"}',
        }

        test_error = ValueError("Processing error")
        mock_handler = MagicMock(side_effect=test_error)

        with (
            patch("otel_observability.chalice.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach") as mock_attach,
            patch("opentelemetry.context.detach"),
            patch("opentelemetry.context.get_current") as mock_get_current,
            patch("opentelemetry.propagate.extract") as mock_extract,
            patch("otel_observability.chalice.logger") as mock_logger,
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_tracer.start_as_current_span.return_value.__exit__.return_value = None
            mock_get_tracer.return_value = mock_tracer
            mock_token = MagicMock()
            mock_attach.return_value = mock_token
            mock_get_current.return_value = MagicMock()
            mock_extract.return_value = MagicMock()

            decorated_handler = trace_sqs_message(mock_handler)

            with pytest.raises(ValueError, match="Processing error"):
                decorated_handler(mock_event)

            mock_span.set_status.assert_called_once()
            mock_span.record_exception.assert_called_once_with(test_error)
            mock_logger.exception.assert_called_once()

    @pytest.mark.skipif(not CHALICE_AVAILABLE, reason="Chalice not available")
    def test_trace_sqs_message_without_chalice_available(self):
        """Testa que levanta ImportError quando Chalice não está disponível."""
        with patch("otel_observability.chalice.CHALICE_AVAILABLE", False):
            mock_handler = MagicMock()

            with pytest.raises(ImportError, match="Chalice not available"):
                trace_sqs_message(mock_handler)


@pytest.mark.unit
class TestExtractSqsCarrier:
    """Testes para _extract_sqs_carrier."""

    def test_extract_sqs_carrier_with_traceparent(self):
        """Testa extração de trace context com traceparent."""
        event = {
            "messageAttributes": {
                "traceparent": {"stringValue": "00-abc-123-01"},
                "tracestate": {"stringValue": "key=value"},
            }
        }

        carrier = _extract_sqs_carrier(event)

        assert carrier["traceparent"] == "00-abc-123-01"
        assert carrier["tracestate"] == "key=value"

    def test_extract_sqs_carrier_with_string_values(self):
        """Testa extração quando messageAttributes são strings."""
        event = {
            "messageAttributes": {
                "traceparent": "00-abc-123-01",
                "tracestate": "key=value",
            }
        }

        carrier = _extract_sqs_carrier(event)

        assert carrier["traceparent"] == "00-abc-123-01"
        assert carrier["tracestate"] == "key=value"

    def test_extract_sqs_carrier_with_value_key(self):
        """Testa extração quando usa 'Value' ao invés de 'stringValue'."""
        event = {
            "messageAttributes": {
                "traceparent": {"Value": "00-abc-123-01"},
                "tracestate": {"Value": "key=value"},
            }
        }

        carrier = _extract_sqs_carrier(event)

        assert carrier["traceparent"] == "00-abc-123-01"
        assert carrier["tracestate"] == "key=value"

    def test_extract_sqs_carrier_without_message_attributes(self):
        """Testa extração quando não há messageAttributes."""
        event = {"messageId": "msg-123", "body": "test"}

        carrier = _extract_sqs_carrier(event)

        assert carrier == {}

    def test_extract_sqs_carrier_without_trace_context(self):
        """Testa extração quando messageAttributes não contém trace context."""
        event = {
            "messageAttributes": {
                "custom-key": {"stringValue": "custom-value"},
            }
        }

        carrier = _extract_sqs_carrier(event)

        assert carrier == {}

    def test_extract_sqs_carrier_empty_message_attributes(self):
        """Testa extração quando messageAttributes está vazio."""
        event = {"messageAttributes": {}}

        carrier = _extract_sqs_carrier(event)

        assert carrier == {}
