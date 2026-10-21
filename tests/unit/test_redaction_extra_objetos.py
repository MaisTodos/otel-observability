"""CNT-3942: objetos e strings JSON dentro de `extra` passam pelo mascaramento."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
import io
import json
import logging
import sys
from uuid import UUID

import pytest

from otel_observability.logging import (
    FlattenAttributesLogRecordProcessor,
    JSONFormatter,
    RedactionFilter,
    TraceContextFilter,
)

DOC = "12345678901"
DOC_OCULTO = "1234567"  # prefixo que nao pode sobrar em nenhuma saida


@dataclass
class Dto:
    document: str
    amount: int


def _pydantic_dto():
    pydantic = pytest.importorskip("pydantic")

    class PydanticDto(pydantic.BaseModel):
        document: str
        amount: int
        created: datetime
        ident: UUID

    return PydanticDto(
        document=DOC,
        amount=10,
        created=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        ident=UUID("abcdef01-abcd-abcd-abcd-abcdef012345"),
    )


class Pipeline:
    """Handler stdout (JSONFormatter) e handler OTLP (LoggingHandler) reais, filtro compartilhado."""

    def __init__(self, mask_policy=None):
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor

        self.stream = io.StringIO()
        self.exporter = InMemoryLogExporter()
        provider = LoggerProvider()
        provider.add_log_record_processor(FlattenAttributesLogRecordProcessor())
        provider.add_log_record_processor(SimpleLogRecordProcessor(self.exporter))
        redaction = RedactionFilter(mask_policy=mask_policy)

        stdout = logging.StreamHandler(self.stream)
        stdout.setFormatter(JSONFormatter())
        otlp = LoggingHandler(level=logging.NOTSET, logger_provider=provider)
        self.errors = []
        for handler in (stdout, otlp):
            handler.addFilter(TraceContextFilter())
            handler.addFilter(redaction)
            handler.handleError = lambda _record: self.errors.append(sys.exc_info()[1])

        self.logger = logging.getLogger(f"test.extra.{id(self)}")
        self.logger.handlers = [stdout, otlp]
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)

    def emit(self, **extra):
        self.exporter.clear()
        self.stream.seek(0)
        self.stream.truncate()
        self.logger.info("evento", extra=extra)
        return self.stdout_text(), self.otlp_text()

    def encoded(self):
        """Serializa pelo encoder OTLP real; um atributo que ele descarta nao aparece aqui."""
        from opentelemetry.exporter.otlp.proto.common._log_encoder import encode_logs

        return str(encode_logs(self.exporter.get_finished_logs()))

    def stdout_text(self):
        return self.stream.getvalue()

    def otlp_text(self):
        registros = self.exporter.get_finished_logs()
        return json.dumps(
            [dict(r.log_record.attributes) for r in registros], default=str, ensure_ascii=False
        )


@pytest.fixture
def pipeline():
    return Pipeline()


@pytest.mark.unit
class TestObjetosEmExtra:
    @pytest.mark.parametrize(
        "fabrica",
        [
            pytest.param(lambda: _pydantic_dto(), id="pydantic"),
            pytest.param(lambda: Dto(document=DOC, amount=10), id="dataclass"),
            pytest.param(lambda: json.dumps({"document": DOC, "amount": 10}), id="json-dumps"),
            pytest.param(lambda: json.dumps(asdict(Dto(DOC, 10))), id="json-dumps-asdict"),
            pytest.param(lambda: _pydantic_dto().model_dump_json(), id="model-dump-json"),
        ],
    )
    def test_documento_mascarado_no_stdout_e_no_otlp(self, pipeline, fabrica):
        stdout, otlp = pipeline.emit(input=fabrica())

        assert stdout, "a linha sumiu do stdout"
        assert DOC_OCULTO not in stdout
        assert DOC_OCULTO not in otlp
        assert "8901" in stdout
        assert "8901" in otlp

    def test_json_dentro_de_props(self, pipeline):
        stdout, otlp = pipeline.emit(props={"event": json.dumps({"document": DOC, "n": 1})})

        assert DOC_OCULTO not in stdout
        assert DOC_OCULTO not in otlp

    @pytest.mark.parametrize(
        "colecao",
        [
            pytest.param(lambda d: [d], id="lista"),
            pytest.param(lambda d: (d,), id="tupla"),
            pytest.param(lambda d: {"a": {"b": [d]}}, id="dict-aninhado"),
            pytest.param(lambda d: {d}, id="conjunto"),
            pytest.param(lambda d: frozenset({d}), id="frozenset"),
        ],
    )
    @pytest.mark.parametrize(
        "item",
        [
            pytest.param(lambda: json.dumps({"document": DOC}), id="string-json"),
            pytest.param(lambda: json.dumps([{"document": DOC}]), id="string-json-lista"),
        ],
    )
    def test_json_em_qualquer_colecao(self, pipeline, colecao, item):
        stdout, otlp = pipeline.emit(props=colecao(item()))

        assert DOC_OCULTO not in stdout
        assert DOC_OCULTO not in otlp

    @pytest.mark.parametrize(
        "colecao",
        [
            pytest.param(lambda d: [d], id="lista"),
            pytest.param(lambda d: (d,), id="tupla"),
            pytest.param(lambda d: {"a": {"b": [d]}}, id="dict-aninhado"),
        ],
    )
    def test_objeto_em_qualquer_colecao(self, pipeline, colecao):
        for obj in (Dto(DOC, 1), _pydantic_dto()):
            stdout, otlp = pipeline.emit(props=colecao(obj))

            assert DOC_OCULTO not in stdout
            assert DOC_OCULTO not in otlp

    def test_json_dentro_de_json(self, pipeline):
        interno = json.dumps({"document": DOC})
        stdout, otlp = pipeline.emit(input=json.dumps({"payload": interno}))

        assert DOC_OCULTO not in stdout
        assert DOC_OCULTO not in otlp

    def test_objeto_dentro_de_objeto(self, pipeline):
        @dataclass
        class Envelope:
            dto: Dto

        stdout, otlp = pipeline.emit(input=Envelope(dto=Dto(DOC, 1)))

        assert DOC_OCULTO not in stdout
        assert DOC_OCULTO not in otlp

    def test_json_sem_dado_sensivel_sai_byte_a_byte_igual(self):
        original = '{"a":1,"b":[1,2,3]}'
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.props = {"raw": original}
        RedactionFilter().filter(record)

        assert record.props["raw"] == original

    def test_json_com_dado_sensivel_continua_json_valido(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.raw = json.dumps({"document": DOC, "n": 1})
        RedactionFilter().filter(record)

        assert json.loads(record.raw) == {"document": "*******8901", "n": 1}


@pytest.mark.unit
class TestTiposNaoSerializaveisNaoPerdemALinha:
    def test_uuid_decimal_datetime(self, pipeline):
        stdout, otlp = pipeline.emit(
            ident=UUID("abcdef01-abcd-abcd-abcd-abcdef012345"),
            valor=Decimal("10.50"),
            quando=datetime(2026, 1, 2, tzinfo=UTC),
            props={"valor": Decimal("1.5")},
        )

        linha = json.loads(stdout.strip().splitlines()[-1])
        assert linha["valor"] == "10.50"
        assert linha["ident"] == "abcdef01-abcd-abcd-abcd-abcdef012345"
        assert linha["props"]["valor"] == "1.5"
        assert "10.50" in otlp

    def test_objeto_arbitrario_nao_derruba_a_linha(self, pipeline):
        class Qualquer:
            def __repr__(self):
                return "<Qualquer>"

        stdout, _ = pipeline.emit(coisa=Qualquer())

        assert "<Qualquer>" in stdout


@pytest.mark.unit
class TestStringQueParecemJsonMasNao:
    @pytest.mark.parametrize(
        "texto",
        [
            "{nao e json}",
            "[1, 2",
            '{"a": }',
            "[]x",
            "{",
            "[",
            "  {sem fechar",
            "texto normal",
            "",
        ],
    )
    def test_sai_igual(self, texto):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.campo = texto
        RedactionFilter().filter(record)

        assert record.campo == texto

    def test_acima_do_limite_passa_direto(self):
        grande = json.dumps({"document": DOC, "pad": "x" * 70_000})
        assert len(grande) > 64 * 1024
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.campo = grande
        RedactionFilter().filter(record)

        assert record.campo == grande

    def test_no_limite_exato_ainda_e_aberto(self):
        base = json.dumps({"document": DOC, "pad": ""})
        texto = json.dumps({"document": DOC, "pad": "x" * (64 * 1024 - len(base))})
        assert len(texto) == 64 * 1024
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.campo = texto
        RedactionFilter().filter(record)

        assert DOC_OCULTO not in record.campo

    def test_um_acima_do_limite_nao_e_aberto(self):
        base = json.dumps({"document": DOC, "pad": ""})
        texto = json.dumps({"document": DOC, "pad": "x" * (64 * 1024 - len(base) + 1)})
        assert len(texto) == 64 * 1024 + 1
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.campo = texto
        RedactionFilter().filter(record)

        assert record.campo == texto

    def test_json_que_estoura_a_pilha_nao_derruba_e_nao_vaza(self, monkeypatch):
        def estoura(_texto):
            raise RecursionError

        monkeypatch.setattr("otel_observability.logging.json.loads", estoura)
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.campo = json.dumps([{"document": DOC}])
        RedactionFilter().filter(record)

        assert DOC not in record.campo

    def test_json_mais_fundo_que_o_limite_nao_vaza(self):
        fundo = "[" * 40 + '"' + DOC + '"' + "]" * 40
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.campo = fundo
        RedactionFilter().filter(record)

        assert DOC not in record.campo


@pytest.mark.unit
class TestIdempotenciaComObjetos:
    def test_segundo_handler_nao_remascara(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.input = Dto(DOC, 1)
        RedactionFilter().filter(record)
        primeiro = record.input
        RedactionFilter().filter(record)

        assert record.input == primeiro
        assert primeiro == {"document": "*******8901", "amount": 1}
