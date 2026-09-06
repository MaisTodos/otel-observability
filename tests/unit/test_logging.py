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

    def test_json_formatter_nao_emite_task_name(self):
        """Testa que o JSONFormatter não emite o campo taskName do LogRecord."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="teste",
            level=logging.INFO,
            pathname="/tmp/x.py",
            lineno=1,
            msg="mensagem",
            args=(),
            exc_info=None,
        )
        record.taskName = None  # presente nativamente a partir do Python 3.12
        record.account_id = "123"  # campo extra de negócio: TEM que sobreviver

        payload = json.loads(formatter.format(record))

        assert "taskName" not in payload
        assert payload["account_id"] == "123"


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


@pytest.mark.unit
class TestRedactionFilter:
    """Testes para o RedactionFilter (mascaramento de dados sensíveis)."""

    @staticmethod
    def _record(**extra):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "msg", None, None)
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_redacts_default_sensitive_top_level(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(access_token="super-secret")
        RedactionFilter().filter(record)
        assert record.access_token == "*****"

    def test_redacts_nested_props(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(
            props={"headers": {"Authorization": "Bearer x"}, "ok": 1},
        )
        RedactionFilter().filter(record)
        assert record.props["headers"]["Authorization"] == "*****"
        assert record.props["ok"] == 1

    def test_redacts_inside_list(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(props={"items": [{"password": "p"}, {"keep": "v"}]})
        RedactionFilter().filter(record)
        assert record.props["items"][0]["password"] == "*****"
        assert record.props["items"][1]["keep"] == "v"

    def test_non_sensitive_untouched(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(props={"account_id": "123", "amount": 100})
        RedactionFilter().filter(record)
        assert record.props == {"account_id": "123", "amount": 100}

    def test_custom_keys_extend_defaults(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(custom_secret="x", access_token="y")
        RedactionFilter(redact_keys={"custom_secret"}).filter(record)
        assert record.custom_secret == "*****"
        assert record.access_token == "*****"

    def test_case_insensitive(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(props={"AUTHORIZATION": "x"})
        RedactionFilter().filter(record)
        assert record.props["AUTHORIZATION"] == "*****"

    def test_reserved_logrecord_attrs_untouched(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(props={"ok": 1})
        RedactionFilter().filter(record)
        assert record.msg == "msg"
        assert record.levelname == "INFO"

    def test_configure_logging_applies_redaction(self, capsys, reset_log_context):
        """Integração: logs emitidos via configure_logging saem mascarados."""
        logger_name = "test.redaction"
        configure_logging(level="INFO", json_format=True, logger_name=logger_name)
        logger = get_logger(logger_name)
        logger.info("evento", extra={"props": {"password": "p", "account_id": "1"}})

        captured = capsys.readouterr().out.strip().splitlines()
        payload = json.loads(captured[-1])
        assert payload["props"]["password"] == "*****"
        assert payload["props"]["account_id"] == "1"

    def test_redige_documento_aninhado_em_props(self):
        """O caso observado em producao: mesma chave, mascarada no topo e em claro aninhada."""
        from otel_observability.logging import CONTA_DIGITAL_MASK_POLICY, RedactionFilter

        record = self._record(props={"header": {"account_document": "12345678000199"}})
        RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY).filter(record)
        assert record.props["header"]["account_document"] != "12345678000199"

    def test_redige_chave_sensivel_com_valor_nao_str(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(cpf=12345678901, cnpj={"numero": "123"}, api_key=b"segredo")
        RedactionFilter().filter(record)
        assert record.cpf != 12345678901
        assert record.cnpj != {"numero": "123"}
        assert record.api_key != b"segredo"

    def test_mascara_parcial_preserva_ultimos_digitos(self):
        from otel_observability.logging import CONTA_DIGITAL_MASK_POLICY, RedactionFilter

        record = self._record(account_document="12345678000199")
        RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY).filter(record)
        assert record.account_document.endswith("0199")
        assert "12345678" not in record.account_document

    def test_email_preserva_dominio(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(email="joao.silva@maistodos.com.br")
        RedactionFilter().filter(record)
        assert record.email.endswith("@maistodos.com.br")
        assert "joao.silva" not in record.email

    def test_pix_key_detecta_formato(self):
        from otel_observability.logging import CONTA_DIGITAL_MASK_POLICY, RedactionFilter

        f = RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY)
        casos = {
            "joao@x.com.br": lambda v: v.endswith("@x.com.br") and "joao" not in v,
            "12345678901": lambda v: v.endswith("8901"),
            "+5511987654321": lambda v: v.endswith("4321"),
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890": lambda v: set(v) == {"*"},
        }
        for valor, ok in casos.items():
            record = self._record(pix_key=valor)
            f.filter(record)
            assert ok(record.pix_key), f"{valor} -> {record.pix_key}"

    def test_documento_int_vira_mascara_parcial(self):
        """CPF chega como int com frequencia. Antes virava ***** total."""
        from otel_observability.logging import RedactionFilter

        record = self._record(document_number=12345678901)
        RedactionFilter().filter(record)
        assert str(record.document_number).endswith("8901")

    def test_consumidor_estende_a_policy(self):
        from otel_observability.logging import Mask, RedactionFilter

        record = self._record(numero_proposta="99887766", password="x")
        RedactionFilter(mask_policy={"numero_proposta": Mask.LAST4}).filter(record)
        assert record.numero_proposta.endswith("7766")
        assert record.password != "x"  # default universal continua valendo

    def test_consumidor_sobrescreve_default(self):
        from otel_observability.logging import Mask, RedactionFilter

        record = self._record(email="a@b.com")
        RedactionFilter(mask_policy={"email": Mask.FULL}).filter(record)
        assert set(record.email) == {"*"}

    def test_dominio_nao_esta_no_default(self):
        """A lib nao conhece a Conta Digital sem o servico optar."""
        from otel_observability.logging import RedactionFilter

        record = self._record(addressing_key="joao@x.com")
        RedactionFilter().filter(record)
        assert record.addressing_key == "joao@x.com"

    def test_estrategia_invalida_falha_no_startup(self):
        from otel_observability.logging import RedactionFilter

        with pytest.raises(ValueError, match="not a valid Mask"):
            RedactionFilter(mask_policy={"x": "last5"})

    def test_credencial_mascara_qualquer_tipo(self):
        from otel_observability.logging import RedactionFilter

        record = self._record(api_key=b"segredo", client_secret={"v": 1})
        RedactionFilter().filter(record)
        assert record.api_key != b"segredo"
        assert record.client_secret != {"v": 1}

    def test_redact_keys_nao_sobrescreve_policy(self):
        """redact_keys e o mecanismo antigo: setdefault — a policy vence na colisao."""
        from otel_observability.logging import Mask, RedactionFilter

        record = self._record(email="joao@x.com")
        RedactionFilter(redact_keys=["email"], mask_policy={"email": Mask.EMAIL}).filter(record)
        assert record.email.endswith("@x.com")
        assert "joao" not in record.email


@pytest.mark.unit
class TestMaskDocument:
    """Testes para mask_document (utilitário público de máscara parcial)."""

    def test_mask_document_e_utilitario_publico(self):
        from otel_observability import mask_document

        assert mask_document("12345678000199").endswith("0199")
        assert "12345678" not in mask_document("12345678000199")
        assert mask_document(None) is None
        assert mask_document("") == ""
