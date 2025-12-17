"""Testes de integração para logging."""

import json
import logging

import pytest

from otel_observability.logging import (
    clear_log_context,
    configure_logging,
    get_logger,
    set_log_context,
)


@pytest.mark.integration
class TestLoggingIntegration:
    """Testes de integração para o sistema de logging."""

    def test_logging_with_context(self, reset_log_context):
        """Testa logging completo com contexto customizado."""
        from unittest.mock import patch

        # Mockar trace_id e span_id para evitar dependência do tracer
        with (
            patch("otel_observability.logging.get_current_trace_id", return_value="trace123"),
            patch("otel_observability.logging.get_current_span_id", return_value="span456"),
        ):
            # Configurar logging
            logger_name = "test_integration"
            configure_logging(level="INFO", json_format=True, logger_name=logger_name)
            logger = get_logger(logger_name)

            # Capturar logs
            log_capture = []

            class ListHandler(logging.Handler):
                def emit(self, record):
                    log_capture.append(self.format(record))

            list_handler = ListHandler()
            list_handler.setFormatter(logger.handlers[0].formatter)
            logger.addHandler(list_handler)

            # Definir contexto
            set_log_context(user_id="123", request_id="req-456")

            # Fazer log
            logger.info("Test message", extra={"custom_field": "value"})

            # Verificar
            assert len(log_capture) > 0
            log_data = json.loads(log_capture[0])

            assert log_data["message"] == "Test message"
            assert log_data["user_id"] == "123"
            assert log_data["request_id"] == "req-456"
            assert log_data["custom_field"] == "value"
            assert log_data["trace_id"] == "trace123"
            assert log_data["span_id"] == "span456"

            # Limpar
            clear_log_context()
