"""Testes unitários para o módulo aws_lambda."""

from unittest.mock import MagicMock, patch

import pytest

from otel_observability import aws_lambda as aws_lambda_module
from otel_observability.aws_lambda import (
    _add_event_attributes,
    _extract_carrier_from_event,
    _get_event_source,
    instrument_lambda_handler,
)
from otel_observability.config import TelemetryConfig


@pytest.fixture(name="reset_lambda_module")
def _reset_lambda_module(reset_telemetry):
    """Reseta a flag global _instrumented entre testes.

    `_instrumented` é global de módulo: sem reset, o teste seguinte entra no
    `if not _instrumented` como falso e vira no-op silencioso. Os globais de
    tracer/logging ficam por conta do reset_telemetry (conftest), pois os
    testes abaixo exercitam o init_telemetry real.
    """
    aws_lambda_module._instrumented = False
    yield
    aws_lambda_module._instrumented = False


def _lambda_context() -> MagicMock:
    """Contexto Lambda mockado, com os atributos usados pelo wrapper."""
    context = MagicMock()
    context.function_name = "test-function"
    context.aws_request_id = "req-123"
    context.function_version = "$LATEST"
    context.memory_limit_in_mb = 512
    return context


@pytest.mark.unit
class TestInstrumentLambdaHandler:
    """Testes para instrument_lambda_handler."""

    def test_instrument_lambda_handler_basic(self, telemetry_config: TelemetryConfig):
        """Testa instrumentação básica de Lambda handler."""
        mock_handler = MagicMock(return_value={"statusCode": 200})
        mock_handler.__name__ = "test_handler"
        mock_lambda_context = MagicMock()
        mock_lambda_context.function_name = "test-function"
        mock_lambda_context.aws_request_id = "req-123"
        mock_lambda_context.function_version = "$LATEST"
        mock_lambda_context.memory_limit_in_mb = 512

        with (
            patch("otel_observability.aws_lambda.init_telemetry") as mock_init,
            patch("otel_observability.aws_lambda.configure_logging") as mock_configure_logs,
            patch("otel_observability.aws_lambda.auto_instrument") as mock_auto_instrument,
            patch("otel_observability.aws_lambda.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach") as mock_attach,
            patch("opentelemetry.context.detach"),
            patch("opentelemetry.context.get_current") as mock_get_current,
            patch("otel_observability.aws_lambda.flush_telemetry") as mock_flush,
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer
            mock_token = MagicMock()
            mock_attach.return_value = mock_token
            mock_get_current.return_value = MagicMock()

            decorated_handler = instrument_lambda_handler(config=telemetry_config)(mock_handler)
            result = decorated_handler({"test": "event"}, mock_lambda_context)

            assert result == {"statusCode": 200}
            mock_init.assert_called_once()
            mock_configure_logs.assert_called_once()
            mock_auto_instrument.assert_called_once()
            mock_handler.assert_called_once_with({"test": "event"}, mock_lambda_context)
            mock_flush.assert_called_once()

    def test_instrument_lambda_handler_without_logs(self, telemetry_config: TelemetryConfig):
        """Testa instrumentação sem configurar logs."""
        mock_handler = MagicMock(return_value={"statusCode": 200})
        mock_handler.__name__ = "test_handler"
        mock_lambda_context = MagicMock()

        with (
            patch("otel_observability.aws_lambda.init_telemetry"),
            patch("otel_observability.aws_lambda.configure_logging") as mock_configure_logs,
            patch("otel_observability.aws_lambda.auto_instrument"),
            patch("otel_observability.aws_lambda.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach"),
            patch("opentelemetry.context.detach"),
            patch("opentelemetry.context.get_current"),
            patch("otel_observability.aws_lambda.flush_telemetry"),
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            decorated_handler = instrument_lambda_handler(
                config=telemetry_config, configure_logs=False
            )(mock_handler)
            decorated_handler({}, mock_lambda_context)

            mock_configure_logs.assert_not_called()

    def test_instrument_lambda_handler_with_exception(self, telemetry_config: TelemetryConfig):
        """Testa instrumentação quando handler levanta exceção."""
        mock_handler = MagicMock(side_effect=ValueError("Test error"))
        mock_handler.__name__ = "test_handler"
        mock_lambda_context = MagicMock()

        with (
            patch("otel_observability.aws_lambda.init_telemetry"),
            patch("otel_observability.aws_lambda.configure_logging"),
            patch("otel_observability.aws_lambda.auto_instrument"),
            patch("otel_observability.aws_lambda.get_tracer") as mock_get_tracer,
            patch("opentelemetry.context.attach") as mock_attach,
            patch("opentelemetry.context.detach") as mock_detach,
            patch("opentelemetry.context.get_current") as mock_get_current,
            patch("otel_observability.aws_lambda.flush_telemetry") as mock_flush,
            patch("otel_observability.aws_lambda.logger"),
        ):
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer
            mock_token = MagicMock()
            mock_attach.return_value = mock_token
            mock_get_current.return_value = MagicMock()

            decorated_handler = instrument_lambda_handler(config=telemetry_config)(mock_handler)

            with pytest.raises(ValueError, match="Test error"):
                decorated_handler({}, mock_lambda_context)

            # Verificar que span foi marcado como erro
            assert mock_span.set_status.called
            assert mock_span.record_exception.called
            mock_detach.assert_called_once_with(mock_token)
            mock_flush.assert_called_once()

    def test_redact_keys_chega_no_configure_logging(self, mocker, reset_lambda_module):
        """redact_keys passado ao decorator chega ao configure_logging."""
        spy = mocker.patch("otel_observability.aws_lambda.configure_logging")

        @instrument_lambda_handler(redact_keys=["cpf_do_cliente"], auto_instrument_libs=False)
        def handler(event, context):
            return {}

        handler({}, _lambda_context())

        assert spy.call_args.kwargs["redact_keys"] == ["cpf_do_cliente"]

    def test_configure_logging_roda_antes_de_init_telemetry(self, mocker, reset_lambda_module):
        """Ordem importa: init_telemetry instala o handler OTLP e configure_logging
        faz handlers.clear(). Invertido, o log nunca sai via OTLP."""
        manager = mocker.MagicMock()
        manager.attach_mock(
            mocker.patch("otel_observability.aws_lambda.configure_logging"), "cfg_log"
        )
        manager.attach_mock(mocker.patch("otel_observability.aws_lambda.init_telemetry"), "init")

        @instrument_lambda_handler(auto_instrument_libs=False)
        def handler(event, context):
            return {}

        handler({}, _lambda_context())

        nomes = [c[0] for c in manager.mock_calls]
        assert nomes.index("cfg_log") < nomes.index("init")

    def test_segunda_invocacao_ainda_exporta_span(self, mocker, reset_lambda_module):
        """Container warm: shutdown a cada invocação mata a exportação da 2ª em diante."""
        shutdown = mocker.patch("otel_observability.aws_lambda.shutdown_telemetry")
        flush = mocker.patch("otel_observability.aws_lambda.flush_telemetry")
        # configure_logging real instalaria handler com TraceContextFilter no root
        # logger, vazando para os testes seguintes.
        mocker.patch("otel_observability.aws_lambda.configure_logging")

        @instrument_lambda_handler(auto_instrument_libs=False)
        def handler(event, context):
            return {}

        handler({}, _lambda_context())
        handler({}, _lambda_context())

        assert shutdown.call_count == 0
        assert flush.call_count == 2


@pytest.mark.unit
class TestExtractCarrierFromEvent:
    """Testes para _extract_carrier_from_event."""

    def test_extract_from_http_headers(self):
        """Testa extração de contexto de headers HTTP."""
        event = {
            "headers": {
                "traceparent": "00-trace-id-span-id-01",
                "tracestate": "state",
            }
        }

        carrier = _extract_carrier_from_event(event)

        assert carrier["traceparent"] == "00-trace-id-span-id-01"
        assert carrier["tracestate"] == "state"

    def test_extract_from_sqs_message(self):
        """Testa extração de contexto de mensagem SQS."""
        event = {
            "Records": [
                {
                    "eventSource": "aws:sqs",
                    "messageAttributes": {
                        "traceparent": {"stringValue": "00-trace-id-span-id-01"},
                        "tracestate": {"stringValue": "state"},
                    },
                }
            ]
        }

        carrier = _extract_carrier_from_event(event)

        assert carrier["traceparent"] == "00-trace-id-span-id-01"
        assert carrier["tracestate"] == "state"

    def test_extract_from_sns_message(self):
        """Testa extração de contexto de mensagem SNS."""
        event = {
            "Records": [
                {
                    "eventSource": "aws:sns",
                    "Sns": {
                        "MessageAttributes": {
                            "traceparent": {"Value": "00-trace-id-span-id-01"},
                            "tracestate": {"Value": "state"},
                        }
                    },
                }
            ]
        }

        carrier = _extract_carrier_from_event(event)

        assert carrier["traceparent"] == "00-trace-id-span-id-01"
        assert carrier["tracestate"] == "state"

    def test_extract_from_eventbridge(self):
        """Testa extração de contexto de EventBridge."""
        event = {
            "detail-type": "test.event",
            "detail": {
                "traceparent": "00-trace-id-span-id-01",
                "tracestate": "state",
            },
        }

        carrier = _extract_carrier_from_event(event)

        assert carrier["traceparent"] == "00-trace-id-span-id-01"
        assert carrier["tracestate"] == "state"

    def test_extract_no_context(self):
        """Testa extração quando não há contexto."""
        event = {"test": "data"}

        carrier = _extract_carrier_from_event(event)

        assert carrier == {}


@pytest.mark.unit
class TestGetEventSource:
    """Testes para _get_event_source."""

    def test_get_event_source_http(self):
        """Testa identificação de fonte HTTP."""
        event = {"httpMethod": "GET"}
        assert _get_event_source(event) == "http"

        event = {"requestContext": {}}
        assert _get_event_source(event) == "http"

    def test_get_event_source_sqs(self):
        """Testa identificação de fonte SQS."""
        event = {"Records": [{"eventSource": "aws:sqs"}]}
        assert _get_event_source(event) == "sqs"

    def test_get_event_source_sns(self):
        """Testa identificação de fonte SNS."""
        event = {"Records": [{"eventSource": "aws:sns"}]}
        assert _get_event_source(event) == "sns"

    def test_get_event_source_s3(self):
        """Testa identificação de fonte S3."""
        event = {"Records": [{"eventSource": "aws:s3"}]}
        assert _get_event_source(event) == "s3"

    def test_get_event_source_dynamodb(self):
        """Testa identificação de fonte DynamoDB."""
        event = {"Records": [{"eventSource": "aws:dynamodbstreams"}]}
        assert _get_event_source(event) == "dynamodb"

    def test_get_event_source_eventbridge(self):
        """Testa identificação de fonte EventBridge."""
        event = {"detail-type": "test.event"}
        assert _get_event_source(event) == "eventbridge"

    def test_get_event_source_other(self):
        """Testa identificação de fonte desconhecida."""
        event = {"unknown": "event"}
        assert _get_event_source(event) == "other"


@pytest.mark.unit
class TestAddEventAttributes:
    """Testes para _add_event_attributes."""

    def test_add_http_attributes(self):
        """Testa adição de atributos HTTP."""
        mock_span = MagicMock()
        event = {
            "httpMethod": "POST",
            "resource": "/users",
            "path": "/users/123",
            "requestContext": {
                "requestId": "req-123",
                "domainName": "api.example.com",
            },
            "headers": {"user-agent": "test-agent"},
        }

        _add_event_attributes(mock_span, event)

        assert mock_span.set_attribute.call_count >= 5
        calls = {call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list}
        assert calls["http.method"] == "POST"
        assert calls["http.route"] == "/users"
        assert calls["http.target"] == "/users/123"
        assert calls["http.request_id"] == "req-123"
        assert calls["http.host"] == "api.example.com"

    def test_add_sqs_attributes(self):
        """Testa adição de atributos SQS."""
        mock_span = MagicMock()
        event = {
            "Records": [
                {
                    "eventSource": "aws:sqs",
                    "messageId": "msg-123",
                    "eventSourceARN": "arn:aws:sqs:us-east-1:123:my-queue",
                }
            ]
        }

        _add_event_attributes(mock_span, event)

        assert mock_span.set_attribute.call_count >= 4
        calls = {call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list}
        assert calls["messaging.system"] == "aws_sqs"
        assert calls["messaging.operation"] == "process"
        assert calls["messaging.message.id"] == "msg-123"
        assert calls["messaging.destination.name"] == "my-queue"

    def test_add_sns_attributes(self):
        """Testa adição de atributos SNS."""
        mock_span = MagicMock()
        event = {
            "Records": [
                {
                    "eventSource": "aws:sns",
                    "Sns": {
                        "MessageId": "msg-123",
                        "TopicArn": "arn:aws:sns:us-east-1:123:my-topic",
                    },
                }
            ]
        }

        _add_event_attributes(mock_span, event)

        assert mock_span.set_attribute.call_count >= 4
        calls = {call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list}
        assert calls["messaging.system"] == "aws_sns"
        assert calls["messaging.message.id"] == "msg-123"
        assert calls["messaging.destination.name"] == "my-topic"

    def test_add_eventbridge_attributes(self):
        """Testa adição de atributos EventBridge."""
        mock_span = MagicMock()
        event = {
            "detail-type": "test.event",
            "source": "my.app",
            "resources": ["arn:aws:resource:123"],
        }

        _add_event_attributes(mock_span, event)

        assert mock_span.set_attribute.call_count >= 4
        calls = {call[0][0]: call[0][1] for call in mock_span.set_attribute.call_args_list}
        assert calls["messaging.system"] == "aws_eventbridge"
        assert calls["messaging.message.event_type"] == "test.event"
        assert calls["cloud.event.source"] == "my.app"
        assert calls["cloud.event.resource"] == "arn:aws:resource:123"
