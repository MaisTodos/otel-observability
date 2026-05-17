"""Testes unitários para o módulo logging."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from otel_observability.logging import (
    FlattenAttributesLogRecordProcessor,
    JSONFormatter,
    TraceContextFilter,
    _flatten_value,
    clear_log_context,
    configure_logging,
    get_log_context,
    get_logger,
    set_log_context,
)


@pytest.mark.unit
class TestLogContext:
    """Testes para contexto de log."""

    def test_set_log_context(self, reset_log_context):
        """Testa definição de contexto de log."""
        set_log_context(user_id="123", request_id="req-456")

        context = get_log_context()
        assert context["user_id"] == "123"
        assert context["request_id"] == "req-456"

    def test_get_log_context_empty(self, reset_log_context):
        """Testa obtenção de contexto vazio."""
        context = get_log_context()
        assert context == {}

    def test_clear_log_context(self, reset_log_context):
        """Testa limpeza de contexto."""
        set_log_context(user_id="123")
        clear_log_context()

        context = get_log_context()
        assert context == {}

    def test_update_log_context(self, reset_log_context):
        """Testa atualização de contexto existente."""
        set_log_context(user_id="123")
        set_log_context(request_id="req-456")

        context = get_log_context()
        assert context["user_id"] == "123"
        assert context["request_id"] == "req-456"


@pytest.mark.unit
class TestTraceContextFilter:
    """Testes para TraceContextFilter."""

    def test_filter_adds_trace_context(self, reset_log_context):
        """Testa que o filter adiciona trace_id e span_id."""
        with (
            patch("otel_observability.logging.get_current_trace_id", return_value="trace123"),
            patch("otel_observability.logging.get_current_span_id", return_value="span456"),
        ):
            filter_obj = TraceContextFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test",
                args=(),
                exc_info=None,
            )

            result = filter_obj.filter(record)

            assert result is True
            assert record.trace_id == "trace123"
            assert record.span_id == "span456"

    def test_filter_adds_custom_context(self, reset_log_context):
        """Testa que o filter adiciona contexto customizado."""
        set_log_context(user_id="123", request_id="req-456")

        with (
            patch("otel_observability.logging.get_current_trace_id", return_value=""),
            patch("otel_observability.logging.get_current_span_id", return_value=""),
        ):
            filter_obj = TraceContextFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test",
                args=(),
                exc_info=None,
            )

            filter_obj.filter(record)

            assert record.user_id == "123"
            assert record.request_id == "req-456"


@pytest.mark.unit
class TestJSONFormatter:
    """Testes para JSONFormatter."""

    def test_format_basic_log(self):
        """Testa formatação de log básico."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.trace_id = "trace123"
        record.span_id = "span456"

        result = formatter.format(record)
        log_data = json.loads(result)

        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.logger"
        assert log_data["message"] == "Test message"
        assert log_data["trace_id"] == "trace123"
        assert log_data["span_id"] == "span456"
        assert "timestamp" in log_data

    def test_format_with_extra_fields(self):
        """Testa formatação com campos extras."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.user_id = "123"
        record.request_id = "req-456"

        result = formatter.format(record)
        log_data = json.loads(result)

        assert log_data["user_id"] == "123"
        assert log_data["request_id"] == "req-456"

    def test_format_with_exception(self):
        """Testa formatação com exceção."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),  # Passar exc_info corretamente
            )

            result = formatter.format(record)
            log_data = json.loads(result)

            assert log_data["level"] == "ERROR"
            assert "exception" in log_data
            assert "ValueError" in log_data["exception"]


@pytest.mark.unit
class TestConfigureLogging:
    """Testes para configure_logging."""

    def test_configure_logging_json_format(self):
        """Testa configuração com formato JSON."""
        logger_name = "test_logger"
        configure_logging(level="DEBUG", json_format=True, logger_name=logger_name)

        logger = logging.getLogger(logger_name)
        assert logger.level == logging.DEBUG

        # Verificar que tem handler com JSONFormatter
        handlers = logger.handlers
        assert len(handlers) > 0
        assert isinstance(handlers[0].formatter, JSONFormatter)

    def test_configure_logging_human_readable(self):
        """Testa configuração com formato legível."""
        logger_name = "test_logger_2"
        configure_logging(level="INFO", json_format=False, logger_name=logger_name)

        logger = logging.getLogger(logger_name)
        assert logger.level == logging.INFO

        # Verificar que tem handler com formatter padrão
        handlers = logger.handlers
        assert len(handlers) > 0
        assert not isinstance(handlers[0].formatter, JSONFormatter)

    def test_configure_logging_with_trace_filter(self):
        """Testa que TraceContextFilter é adicionado."""
        logger_name = "test_logger_3"
        configure_logging(level="INFO", json_format=True, logger_name=logger_name)

        logger = logging.getLogger(logger_name)
        handlers = logger.handlers

        # Verificar que tem TraceContextFilter
        assert any(isinstance(f, TraceContextFilter) for f in handlers[0].filters)


@pytest.mark.unit
class TestFlattenValue:
    """Testes para _flatten_value."""

    def test_primitive_string(self):
        result = {}
        _flatten_value("key", "value", result)
        assert result == {"key": "value"}

    def test_primitive_int(self):
        result = {}
        _flatten_value("count", 42, result)
        assert result == {"count": 42}

    def test_none_value_is_dropped(self):
        result = {}
        _flatten_value("key", None, result)
        assert result == {}

    def test_none_value_inside_nested_dict_is_dropped(self):
        result = {}
        _flatten_value("root", {"keep": "x", "drop": None}, result)
        assert result == {"root.keep": "x"}

    def test_nested_dict(self):
        result = {}
        _flatten_value("root", {"child": "val"}, result)
        assert result == {"root.child": "val"}

    def test_non_primitive_serialized(self):
        result = {}
        _flatten_value("obj", object(), result)
        assert "obj" in result
        assert isinstance(result["obj"], str)

    def test_max_depth_truncates(self):
        result = {}
        _flatten_value("deep", {"a": {"b": {"c": "v"}}}, result, depth=3)
        assert "deep" in result


@pytest.mark.unit
class TestFlattenAttributesProcessor:
    """Testes para FlattenAttributesLogRecordProcessor."""

    def test_on_emit_no_attributes(self):
        processor = FlattenAttributesLogRecordProcessor()
        inner = MagicMock()
        inner.attributes = None
        log_record = MagicMock()
        log_record.log_record = inner
        processor.on_emit(log_record)  # deve retornar sem erro

    def test_on_emit_flattens_attributes(self):
        processor = FlattenAttributesLogRecordProcessor()
        inner = MagicMock()
        inner.attributes = {"key": "value", "nested": "flat"}
        log_record = MagicMock()
        log_record.log_record = inner
        processor.on_emit(log_record)
        assert inner.attributes is not None

    def test_shutdown(self):
        processor = FlattenAttributesLogRecordProcessor()
        processor.shutdown()  # deve retornar sem erro

    def test_force_flush(self):
        processor = FlattenAttributesLogRecordProcessor()
        assert processor.force_flush() is True


@pytest.mark.unit
class TestGetLogger:
    """Testes para get_logger."""

    def test_get_logger_returns_logger(self):
        """Testa que get_logger retorna uma instância de Logger."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"
