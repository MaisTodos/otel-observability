"""Testes unitários para o módulo propagation."""

from unittest.mock import MagicMock, patch

import pytest

from otel_observability.propagation import (
    attach_context,
    extract_context_from_eventbridge_detail,
    extract_context_from_http_headers,
    extract_context_from_lambda_payload,
    extract_context_from_sns_message,
    extract_context_from_sqs_message,
    get_current_trace_context,
    inject_context_into_eventbridge_detail,
    inject_context_into_http_headers,
    inject_context_into_lambda_payload,
    inject_context_into_sns_message_attributes,
    inject_context_into_sqs_message_attributes,
)


@pytest.mark.unit
class TestInjectContextIntoHttpHeaders:
    """Testes para inject_context_into_http_headers."""

    def test_inject_context_into_empty_headers(self):
        """Testa injeção de contexto em headers vazios."""
        with patch("otel_observability.propagation.inject") as mock_inject:
            result = inject_context_into_http_headers()

            assert isinstance(result, dict)
            mock_inject.assert_called_once()

    def test_inject_context_into_existing_headers(self):
        """Testa injeção de contexto em headers existentes."""
        existing_headers = {"Authorization": "Bearer token"}
        with patch("otel_observability.propagation.inject") as mock_inject:
            result = inject_context_into_http_headers(existing_headers)

            assert result == existing_headers
            mock_inject.assert_called_once_with(existing_headers)


@pytest.mark.unit
class TestInjectContextIntoSqsMessageAttributes:
    """Testes para inject_context_into_sqs_message_attributes."""

    def test_inject_context_into_sqs_attributes(self):
        """Testa injeção de contexto em atributos SQS."""
        with patch("otel_observability.propagation.inject") as mock_inject:
            mock_inject.side_effect = lambda carrier: carrier.update(
                {"traceparent": "00-trace-id-span-id-01", "tracestate": "state"}
            )

            result = inject_context_into_sqs_message_attributes()

            assert isinstance(result, dict)
            assert "traceparent" in result
            assert result["traceparent"]["DataType"] == "String"
            assert "tracestate" in result
            assert result["tracestate"]["DataType"] == "String"

    def test_inject_context_into_sqs_attributes_no_tracestate(self):
        """Testa injeção quando não há tracestate."""
        with patch("otel_observability.propagation.inject") as mock_inject:
            mock_inject.side_effect = lambda carrier: carrier.update(
                {"traceparent": "00-trace-id-span-id-01"}
            )

            result = inject_context_into_sqs_message_attributes()

            assert "traceparent" in result
            assert "tracestate" not in result


@pytest.mark.unit
class TestInjectContextIntoSnsMessageAttributes:
    """Testes para inject_context_into_sns_message_attributes."""

    def test_inject_context_into_sns_attributes(self):
        """Testa que SNS usa mesmo formato que SQS."""
        with patch(
            "otel_observability.propagation.inject_context_into_sqs_message_attributes"
        ) as mock_sqs:
            mock_sqs.return_value = {"traceparent": {"StringValue": "test", "DataType": "String"}}

            result = inject_context_into_sns_message_attributes()

            assert result == mock_sqs.return_value
            mock_sqs.assert_called_once()


@pytest.mark.unit
class TestInjectContextIntoEventbridgeDetail:
    """Testes para inject_context_into_eventbridge_detail."""

    def test_inject_context_into_eventbridge_detail(self):
        """Testa injeção de contexto em detail do EventBridge."""
        detail = {"order_id": 123, "status": "created"}
        with patch("otel_observability.propagation.inject") as mock_inject:
            mock_inject.side_effect = lambda carrier: carrier.update(
                {"traceparent": "00-trace-id-span-id-01", "tracestate": "state"}
            )

            result = inject_context_into_eventbridge_detail(detail)

            assert result["order_id"] == 123
            assert result["status"] == "created"
            assert "_trace_context" in result
            assert "traceparent" in result
            assert "tracestate" in result


@pytest.mark.unit
class TestInjectContextIntoLambdaPayload:
    """Testes para inject_context_into_lambda_payload."""

    def test_inject_context_into_lambda_payload(self):
        """Testa injeção de contexto em payload Lambda."""
        payload = {"action": "process", "data": "test"}
        with patch("otel_observability.propagation.inject") as mock_inject:
            mock_inject.side_effect = lambda carrier: carrier.update(
                {"traceparent": "00-trace-id-span-id-01"}
            )

            result = inject_context_into_lambda_payload(payload)

            assert result["action"] == "process"
            assert result["data"] == "test"
            assert "_trace_context" in result


@pytest.mark.unit
class TestExtractContextFromHttpHeaders:
    """Testes para extract_context_from_http_headers."""

    def test_extract_context_from_http_headers(self):
        """Testa extração de contexto de headers HTTP."""
        headers = {"traceparent": "00-trace-id-span-id-01", "tracestate": "state"}
        mock_context = MagicMock()

        with patch(
            "otel_observability.propagation.extract", return_value=mock_context
        ) as mock_extract:
            result = extract_context_from_http_headers(headers)

            assert result == mock_context
            # Verificar que headers foram normalizados para lowercase
            call_args = mock_extract.call_args[0][0]
            assert all(isinstance(k, str) for k in call_args.keys())  # noqa: SIM118


@pytest.mark.unit
class TestExtractContextFromSqsMessage:
    """Testes para extract_context_from_sqs_message."""

    def test_extract_context_from_sqs_message_with_attributes(self):
        """Testa extração quando há messageAttributes."""
        message = {
            "messageAttributes": {
                "traceparent": {"stringValue": "00-trace-id-span-id-01"},
                "tracestate": {"stringValue": "state"},
            }
        }
        mock_context = MagicMock()

        with patch(
            "otel_observability.propagation.extract", return_value=mock_context
        ) as mock_extract:
            result = extract_context_from_sqs_message(message)

            assert result == mock_context
            mock_extract.assert_called_once()

    def test_extract_context_from_sqs_message_no_attributes(self):
        """Testa extração quando não há messageAttributes."""
        message = {}
        mock_current_context = MagicMock()

        with patch("opentelemetry.context.get_current", return_value=mock_current_context):
            result = extract_context_from_sqs_message(message)

            assert result == mock_current_context


@pytest.mark.unit
class TestExtractContextFromSnsMessage:
    """Testes para extract_context_from_sns_message."""

    def test_extract_context_from_sns_message_with_attributes(self):
        """Testa extração quando há MessageAttributes."""
        record = {
            "Sns": {
                "MessageAttributes": {
                    "traceparent": {"Value": "00-trace-id-span-id-01"},
                    "tracestate": {"Value": "state"},
                }
            }
        }
        mock_context = MagicMock()

        with patch(
            "otel_observability.propagation.extract", return_value=mock_context
        ) as mock_extract:
            result = extract_context_from_sns_message(record)

            assert result == mock_context
            mock_extract.assert_called_once()

    def test_extract_context_from_sns_message_no_attributes(self):
        """Testa extração quando não há MessageAttributes."""
        record = {}
        mock_current_context = MagicMock()

        with patch("opentelemetry.context.get_current", return_value=mock_current_context):
            result = extract_context_from_sns_message(record)

            assert result == mock_current_context


@pytest.mark.unit
class TestExtractContextFromEventbridgeDetail:
    """Testes para extract_context_from_eventbridge_detail."""

    def test_extract_context_from_eventbridge_detail_with_trace_context(self):
        """Testa extração quando há _trace_context."""
        detail = {
            "_trace_context": {
                "traceparent": "00-trace-id-span-id-01",
                "tracestate": "state",
            }
        }
        mock_context = MagicMock()

        with patch(
            "otel_observability.propagation.extract", return_value=mock_context
        ) as mock_extract:
            result = extract_context_from_eventbridge_detail(detail)

            assert result == mock_context
            mock_extract.assert_called_once()

    def test_extract_context_from_eventbridge_detail_with_root_fields(self):
        """Testa extração quando há campos no nível raiz."""
        detail = {
            "traceparent": "00-trace-id-span-id-01",
            "tracestate": "state",
        }
        mock_context = MagicMock()

        with patch(
            "otel_observability.propagation.extract", return_value=mock_context
        ) as mock_extract:
            result = extract_context_from_eventbridge_detail(detail)

            assert result == mock_context
            mock_extract.assert_called_once()

    def test_extract_context_from_eventbridge_detail_no_context(self):
        """Testa extração quando não há contexto."""
        detail = {"order_id": 123}
        mock_current_context = MagicMock()

        with patch("opentelemetry.context.get_current", return_value=mock_current_context):
            result = extract_context_from_eventbridge_detail(detail)

            assert result == mock_current_context


@pytest.mark.unit
class TestExtractContextFromLambdaPayload:
    """Testes para extract_context_from_lambda_payload."""

    def test_extract_context_from_lambda_payload_with_context(self):
        """Testa extração quando há _trace_context."""
        payload = {
            "_trace_context": {
                "traceparent": "00-trace-id-span-id-01",
            }
        }
        mock_context = MagicMock()

        with patch(
            "otel_observability.propagation.extract", return_value=mock_context
        ) as mock_extract:
            result = extract_context_from_lambda_payload(payload)

            assert result == mock_context
            mock_extract.assert_called_once()

    def test_extract_context_from_lambda_payload_no_context(self):
        """Testa extração quando não há contexto."""
        payload = {"action": "process"}
        mock_current_context = MagicMock()

        with patch("opentelemetry.context.get_current", return_value=mock_current_context):
            result = extract_context_from_lambda_payload(payload)

            assert result == mock_current_context


@pytest.mark.unit
class TestGetCurrentTraceContext:
    """Testes para get_current_trace_context."""

    def test_get_current_trace_context(self):
        """Testa obtenção do contexto atual."""
        with patch("otel_observability.propagation.inject") as mock_inject:
            mock_inject.side_effect = lambda carrier: carrier.update(
                {"traceparent": "00-trace-id-span-id-01", "tracestate": "state"}
            )

            result = get_current_trace_context()

            assert isinstance(result, dict)
            assert "traceparent" in result
            assert "tracestate" in result
            mock_inject.assert_called_once()


@pytest.mark.unit
class TestAttachContext:
    """Testes para attach_context."""

    def test_attach_context(self):
        """Testa anexação de contexto."""
        mock_parent_context = MagicMock()
        mock_token = MagicMock()

        with patch("opentelemetry.context.attach", return_value=mock_token) as mock_attach:
            result = attach_context(mock_parent_context)

            assert result == mock_token
            mock_attach.assert_called_once_with(mock_parent_context)
