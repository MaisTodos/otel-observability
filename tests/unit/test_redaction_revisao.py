"""Revisao adversarial do CNT-3942/CNT-3524: o filtro nao derruba, nao perde linha, nao vaza."""

from collections import namedtuple
from dataclasses import dataclass
from datetime import date
import json
import logging
from uuid import UUID
import warnings

import pytest

from otel_observability.logging import (
    CONTA_DIGITAL_MASK_POLICY,
    JSONFormatter,
    Mask,
    RedactionFilter,
)

from .test_redaction_extra_objetos import Pipeline

DOC = "12345678901"
DOC2 = "98765432100"
EMAIL1 = "a.silva@exemplo.com"
EMAIL2 = "b.souza@exemplo.org"


@pytest.fixture
def pipe():
    return Pipeline(mask_policy=CONTA_DIGITAL_MASK_POLICY)


def _tudo(pipe, **extra):
    stdout, otlp = pipe.emit(**extra)
    assert not pipe.errors, pipe.errors
    return stdout, otlp, pipe.encoded()


class FalhaNoStr:
    def __str__(self):
        raise RuntimeError("segredo-na-excecao")

    __repr__ = __str__


class SetComInit(set):
    def __init__(self, a, b):
        super().__init__([a, b])


@pytest.mark.unit
class TestFiltroNuncaDerrubaQuemChama:
    def test_objeto_cujo_str_falha_sob_chave_sensivel(self, pipe):
        stdout, otlp, enc = _tudo(pipe, cpf=FalhaNoStr())

        assert "*****" in stdout
        assert "segredo-na-excecao" not in stdout + otlp + enc

    def test_subclasse_de_set_com_init_proprio(self, pipe):
        stdout, otlp, enc = _tudo(pipe, props=SetComInit(json.dumps({"cpf": DOC}), "x"))

        assert stdout
        assert "1234567" not in stdout + otlp + enc

    def test_falha_em_um_campo_nao_afeta_os_outros(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.cpf = FalhaNoStr()
        record.ok = "intacto"
        record.document = DOC

        assert RedactionFilter().filter(record) is True
        assert (record.cpf, record.ok, record.document) == ("*****", "intacto", "*******8901")

    def test_objeto_que_falha_na_conversao_nao_entrega_o_texto_da_excecao(self):
        class Quebrado:
            def model_dump(self, **_):
                raise ValueError("12345678901")

        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.input = Quebrado()
        RedactionFilter().filter(record)

        assert record.input == "*****"


@pytest.mark.unit
class TestFormatterComObjetoQueNaoConvertePraTexto:
    def test_str_que_falha_nao_perde_a_linha(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.x = FalhaNoStr()

        linha = json.loads(JSONFormatter().format(record))
        assert linha["x"] == "<FalhaNoStr>"
        assert "segredo-na-excecao" not in json.dumps(linha)


@pytest.mark.unit
class TestChavesQueNaoSaoString:
    @pytest.mark.parametrize(
        "chave",
        [date(2026, 1, 2), UUID(int=1), (1, 2), 7, None, 1.5, b"k"],
        ids=["date", "uuid", "tupla", "int", "none", "float", "bytes"],
    )
    def test_linha_sai_no_stdout_e_no_otlp(self, pipe, chave):
        stdout, otlp, enc = _tudo(pipe, totals={chave: 10})

        assert stdout, "a linha sumiu do stdout"
        assert json.loads(stdout)["totals"][str(chave)] == 10
        assert "10" in otlp
        assert "totals" in enc

    def test_aninhado_em_lista_e_dict(self, pipe):
        stdout, _, enc = _tudo(pipe, x={"a": [{date(2026, 1, 2): {UUID(int=1): {(1, 2): 3}}}]})

        assert stdout
        assert "2026-01-02" in enc

    def test_chave_nao_str_nao_esconde_dado_sensivel(self, pipe):
        stdout, otlp, enc = _tudo(pipe, x={date(2026, 1, 2): {"customerDocument": DOC}})

        assert "1234567" not in stdout + otlp + enc

    def test_formatter_sozinho_nao_perde_a_linha(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.totals = {date(2026, 1, 2): 1, (1, 2): {UUID(int=1): 2}}

        linha = json.loads(JSONFormatter().format(record))
        assert linha["totals"]["2026-01-02"] == 1
        assert linha["totals"]["(1, 2)"] == {"00000000-0000-0000-0000-000000000001": 2}

    def test_formatter_sozinho_com_ciclo_nao_perde_a_linha(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        ciclo = {}
        ciclo[date(2026, 1, 2)] = ciclo
        record.x = ciclo

        assert json.loads(JSONFormatter().format(record))["message"] == "m"


@pytest.mark.unit
class TestEstrategiaAplicadaACadaElemento:
    @pytest.mark.parametrize(
        "colecao",
        [list, tuple, set, frozenset],
        ids=["lista", "tupla", "set", "frozenset"],
    )
    def test_emails(self, pipe, colecao):
        stdout, otlp, enc = _tudo(pipe, recipient_email=colecao([EMAIL1, EMAIL2]))

        for visto in (stdout, otlp, enc):
            assert "silva" not in visto
            assert "souza" not in visto
            assert "@exemplo.com" in visto
            assert "@exemplo.org" in visto

    @pytest.mark.parametrize("colecao", [list, tuple, set], ids=["lista", "tupla", "set"])
    def test_documentos(self, pipe, colecao):
        stdout, otlp, enc = _tudo(pipe, sender_document=colecao([DOC, DOC2]))

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto
            assert "9876543" not in visto
            assert "8901" in visto
            assert "2100" in visto

    def test_dict_sob_chave_sensivel(self, pipe):
        stdout, otlp, enc = _tudo(pipe, sender_document={"number": DOC, "other": DOC2})

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto
            assert "9876543" not in visto
        assert json.loads(stdout)["sender_document"] == {
            "number": "*******8901",
            "other": "*******2100",
        }

    def test_aninhado_lista_de_dicts_de_listas(self, pipe):
        valor = [{"a": [DOC, {"b": (DOC2,)}]}, [[DOC]]]
        stdout, otlp, enc = _tudo(pipe, user_document=valor)

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto
            assert "9876543" not in visto

    def test_credencial_em_lista_e_totalmente_mascarada(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.password = ["abc", "def"]
        RedactionFilter().filter(record)

        assert record.password == "*****"

    def test_nome_em_lista(self, pipe):
        stdout, _, _ = _tudo(pipe, holder_name=["Joao da Silva", "Maria Souza"])

        assert json.loads(stdout)["holder_name"] == ["J. d. S.", "M. S."]

    def test_objeto_sob_chave_sensivel(self, pipe):
        @dataclass
        class Par:
            a: str
            b: str

        stdout, otlp, enc = _tudo(pipe, sender_document=Par(DOC, DOC2))

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto
            assert "9876543" not in visto


@pytest.mark.unit
class TestBytesComJson:
    def test_response_content_em_json(self, pipe):
        stdout, otlp, enc = _tudo(pipe, body=json.dumps({"cpf": DOC}).encode())

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto
        assert "8901" in stdout

    def test_bytes_json_em_colecoes(self, pipe):
        corpo = json.dumps({"customerDocument": DOC}).encode()
        stdout, otlp, enc = _tudo(pipe, x={"a": [corpo, (corpo,)]})

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto

    def test_bytearray_json(self, pipe):
        stdout, otlp, enc = _tudo(pipe, body=bytearray(json.dumps({"cpf": DOC}).encode()))

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto

    def test_bytes_que_nao_sao_json_seguem_iguais(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.a = b"\x00\x01binario"
        record.b = b"texto qualquer"
        record.c = b"{nao e json}"
        RedactionFilter().filter(record)

        assert (record.a, record.b, record.c) == (
            b"\x00\x01binario",
            b"texto qualquer",
            b"{nao e json}",
        )

    def test_bytes_sob_chave_sensivel_continuam_sem_sobra(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.cpf = DOC.encode()
        RedactionFilter().filter(record)

        assert record.cpf == "*******8901"


@pytest.mark.unit
class TestNamedtuple:
    def test_campos_nomeados_sao_mascarados(self, pipe):
        Cliente = namedtuple("Cliente", "cpf amount")
        stdout, otlp, enc = _tudo(pipe, input=Cliente(DOC, 1))

        assert json.loads(stdout)["input"] == {"cpf": "*******8901", "amount": 1}
        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto

    def test_namedtuple_em_lista(self, pipe):
        Par = namedtuple("Par", "customerDocument n")
        stdout, otlp, enc = _tudo(pipe, x=[Par(DOC, 1)])

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto

    def test_tupla_comum_continua_tupla(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.x = (1, "a")
        RedactionFilter().filter(record)

        assert record.x == (1, "a")


@pytest.mark.unit
class TestFlagsEContagensNaoSaoMascaradas:
    @pytest.mark.parametrize(
        ("chave", "valor"),
        [
            ("has_document", False),
            ("has_document", True),
            ("is_valid_email", True),
            ("total_cnpj", 3),
            ("count_cpf", 0),
            ("total_cpf", 9999),
            ("total_cpf", -9999),
            ("count_cnpj", 9999.5),
            ("hasDocument", False),
            ("isValidEmail", True),
            ("totalCnpj", 3),
            ("has_document", None),
            ("missing_cpf", True),
            ("send_email", False),
            ("document", True),
        ],
    )
    def test_passam_intactos(self, chave, valor):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.props = {chave: valor}
        RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY).filter(record)

        assert record.props[chave] == valor
        assert type(record.props[chave]) is type(valor)

    @pytest.mark.parametrize(
        ("chave", "valor"),
        [
            ("total_cnpj", "12345678000199"),
            ("has_document", "12345678901"),
            ("is_valid_email", "a@b.com"),
            ("customer_cpf", 12345678901),
            ("document_number", 12345678901),
            ("sender_document", 12345678901),
            ("qty_cpf", "12345678901"),
        ],
    )
    def test_texto_ou_numero_de_documento_continua_mascarado(self, chave, valor):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.props = {chave: valor}
        RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY).filter(record)

        resultado = record.props[chave]
        if chave == "total_cnpj" or chave == "qty_cpf" or chave == "has_document":
            assert isinstance(resultado, str)
        assert str(valor)[:5] not in str(resultado)

    @pytest.mark.parametrize(
        ("chave", "valor"),
        [
            ("num_cpf", 12345678901),
            ("num_document", 12345678901),
            ("qty_account_number", 12345678901),
            ("num_document", 2),
            ("qty_account_number", 7),
            ("total_cpf", 12345678901),
            ("total_cpf", 10000),
            ("total_cpf", -10000),
            ("count_cnpj", 10000.0),
            ("has_document", 12345678901),
        ],
    )
    def test_numero_de_documento_nao_e_poupado_por_prefixo(self, chave, valor):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.props = {chave: valor}
        RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY).filter(record)

        resultado = record.props[chave]
        assert isinstance(resultado, str)
        assert str(valor)[:3] not in resultado

    @pytest.mark.parametrize("prefixo", ["has_", "is_", "total_", "count_", "num_", "qty_"])
    @pytest.mark.parametrize("valor", [3, 12345678901, None])
    def test_chave_exata_da_policy_nunca_e_poupada(self, prefixo, valor):
        chave = f"{prefixo}cpf"
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        setattr(record, chave, valor)
        RedactionFilter(mask_policy={chave: Mask.LAST4}).filter(record)

        assert isinstance(getattr(record, chave), str)

    def test_chave_exata_aninhada_nunca_e_poupada(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.props = {"itens": [{"total_cpf": 12345678901}]}
        RedactionFilter(mask_policy={"total_cpf": Mask.LAST4}).filter(record)

        assert record.props["itens"][0]["total_cpf"] == "*******8901"

    def test_contagem_pequena_por_sufixo_em_lista(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.total_cnpj = [3, 4]
        RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY).filter(record)

        assert record.total_cnpj == [3, 4]

    def test_credencial_booleana_continua_mascarada(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.password = True
        RedactionFilter().filter(record)

        assert record.password == "*****"

    def test_numero_inteiro_de_documento_sob_prefixo_de_contagem_e_exato(self):
        """Prefixo so poupa a chave por sufixo; document_number inteiro e CPF, e continua mascarado."""
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.document_number = 12345678901
        RedactionFilter().filter(record)

        assert record.document_number == "*******8901"


@pytest.mark.unit
class TestSurrogateNaoDivergeEntreStdoutEOtlp:
    def test_surrogate_escapado_no_json(self, pipe):
        corpo = '{"cpf":"' + DOC + '","t":"\\ud800"}'
        stdout, _, enc = _tudo(pipe, body=corpo)

        assert "body" in enc, "o encoder OTLP descartou o atributo"
        assert "body" in json.loads(stdout)
        assert "1234567" not in stdout + enc
        assert "ud800" in enc

    def test_acentos_continuam_legiveis(self, pipe):
        _, otlp, _ = _tudo(pipe, body=json.dumps({"cpf": DOC, "nome": "José"}))

        assert "José" in otlp


@pytest.mark.unit
class TestJsonQueNaoAbreMasNaoE:
    def test_bom_no_inicio(self, pipe):
        stdout, otlp, enc = _tudo(pipe, body="﻿" + json.dumps({"cpf": DOC}))

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto

    def test_bom_sem_dado_sensivel_sai_igual(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.body = "﻿" + json.dumps({"a": 1})
        RedactionFilter().filter(record)

        assert record.body == "﻿" + json.dumps({"a": 1})

    def test_inteiro_acima_do_limite_do_python(self, pipe):
        corpo = '{"cpf":"' + DOC + '","n":' + "1" * 5000 + "}"
        stdout, otlp, enc = _tudo(pipe, body=corpo)

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto

    def test_json_invalido_de_verdade_sai_igual(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.body = '{"cpf": "12345678901",}'
        RedactionFilter().filter(record)

        assert record.body == '{"cpf": "12345678901",}'


@pytest.mark.unit
class TestLimiteDe64KbEmBytes:
    @staticmethod
    def _json_com_bytes(total_bytes):
        base = json.dumps({"document": DOC, "pad": ""}, ensure_ascii=False)
        pad = "é" * ((total_bytes - len(base.encode())) // 2)
        texto = json.dumps({"document": DOC, "pad": pad}, ensure_ascii=False)
        if len(texto.encode()) < total_bytes:
            texto = texto.replace('"pad": "', '"pad": "x', 1)
        assert len(texto.encode()) == total_bytes
        return texto

    def test_no_limite_em_bytes_e_aberto(self):
        texto = self._json_com_bytes(64 * 1024)
        assert len(texto) < 64 * 1024
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.body = texto
        RedactionFilter().filter(record)

        assert "1234567" not in record.body

    def test_um_byte_acima_nao_e_aberto(self):
        texto = self._json_com_bytes(64 * 1024 + 1)
        assert len(texto) <= 64 * 1024
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.body = texto
        RedactionFilter().filter(record)

        assert record.body == texto

    def test_bytes_respeitam_o_mesmo_limite(self):
        texto = self._json_com_bytes(64 * 1024 + 1).encode()
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.body = texto
        RedactionFilter().filter(record)

        assert record.body == texto


@pytest.mark.unit
class TestLimitesConhecidosTravados:
    """O que funciona hoje fica travado; o que nao funciona esta em docs/USAGE.md."""

    def test_pydantic_com_alias_e_populate_by_name(self):
        pydantic = pytest.importorskip("pydantic")

        class M(pydantic.BaseModel):
            model_config = pydantic.ConfigDict(populate_by_name=True)
            document_number: str = pydantic.Field(alias="documentNumber")
            pixKey: str

        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.input = M(documentNumber=DOC, pixKey=DOC)
        RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY).filter(record)

        assert record.input == {"document_number": "*******8901", "pixKey": "*******8901"}

    def test_dataclass_aninhada_com_tupla(self):
        @dataclass
        class Inner:
            holderName: str
            customerDocument: str

        @dataclass
        class Outer:
            inner: Inner
            tags: tuple

        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.input = Outer(Inner("Joao da Silva", DOC), ("t",))
        RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY).filter(record)

        assert record.input == {
            "inner": {"holderName": "J. d. S.", "customerDocument": "*******8901"},
            "tags": ("t",),
        }

    def test_ciclo_em_dataclass_vira_mascara_total(self):
        @dataclass
        class No:
            cpf: str
            filho: "No | None" = None

        raiz = No(DOC)
        raiz.filho = raiz
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.input = raiz
        RedactionFilter().filter(record)

        assert record.input == "*****"

    def test_ciclo_em_lista_nao_derruba(self):
        ciclo = []
        ciclo.append(ciclo)
        ciclo.append({"cpf": DOC})
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.x = ciclo

        assert RedactionFilter().filter(record) is True
        assert DOC not in str(record.x)


@pytest.mark.unit
class TestOrdemDeHandlersDocumentada:
    """O filtro troca o valor no proprio record: o que vem depois ve o mascarado, o que vem antes ve o original."""

    def test_handler_do_cliente_antes_e_depois_do_filtro(self):
        @dataclass
        class Dto:
            document: str
            amount: int

        vistos = {}

        class Espiao(logging.Handler):
            def __init__(self, nome):
                super().__init__()
                self.nome = nome

            def emit(self, record):
                vistos[self.nome] = record.input

        pipe = Pipeline()
        antes, depois = Espiao("antes"), Espiao("depois")
        pipe.logger.handlers.insert(0, antes)
        pipe.logger.addHandler(depois)
        dto = Dto(DOC, 10)
        pipe.emit(input=dto)

        assert vistos["antes"] is dto
        assert vistos["depois"] == {"document": "*******8901", "amount": 10}
        assert dto.document == DOC


class FakeAttrib:
    def __init__(self, name):
        self.name = name


class FakeAttrs:
    """Mesma interface de uma classe attrs: `__attrs_attrs__` na classe, valores nos atributos."""

    __attrs_attrs__ = (FakeAttrib("document"), FakeAttrib("amount"))

    def __init__(self, document, amount):
        self.document = document
        self.amount = amount


class FakeSlottedAttrs:
    __slots__ = ("customerDocument", "n")
    __attrs_attrs__ = (FakeAttrib("customerDocument"), FakeAttrib("n"))

    def __init__(self, doc, n):
        self.customerDocument = doc
        self.n = n

    def __repr__(self):
        return f"FakeSlottedAttrs({self.customerDocument})"


class FakePydanticV1:
    """Mesma interface do pydantic v1: `.dict()` e nenhum `model_dump`."""

    def __init__(self, document, amount):
        self._d = {"document": document, "amount": amount}

    def dict(self):
        return dict(self._d)

    def __str__(self):
        return f"document={self._d['document']} amount={self._d['amount']}"


def _pydantic_v1_real():
    pytest.importorskip("pydantic")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v1 = pytest.importorskip("pydantic.v1")

    class ModelV1(v1.BaseModel):
        document: str
        amount: int

    modelo = ModelV1(document=DOC, amount=1)
    if not modelo.dict():
        pytest.skip("pydantic.v1 nao funciona nesta versao do Python")
    return modelo


@pytest.mark.unit
class TestPydanticV1EAttrs:
    @pytest.mark.parametrize(
        "fabrica",
        [
            pytest.param(_pydantic_v1_real, id="pydantic-v1-real"),
            pytest.param(lambda: FakePydanticV1(DOC, 1), id="pydantic-v1-interface"),
            pytest.param(lambda: FakeAttrs(DOC, 1), id="attrs-interface"),
            pytest.param(lambda: FakeSlottedAttrs(DOC, 1), id="attrs-slots-interface"),
        ],
    )
    def test_documento_mascarado_nos_dois_caminhos(self, pipe, fabrica):
        stdout, otlp, enc = _tudo(pipe, input=fabrica())

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto
        assert "8901" in stdout

    @pytest.mark.parametrize(
        "fabrica",
        [
            lambda: FakePydanticV1(DOC, 1),
            lambda: FakeAttrs(DOC, 1),
            lambda: FakeSlottedAttrs(DOC, 1),
        ],
    )
    def test_em_qualquer_colecao_e_sob_chave_sensivel(self, pipe, fabrica):
        stdout, otlp, enc = _tudo(
            pipe, props={"a": [fabrica(), (fabrica(),)]}, sender_document=[fabrica()]
        )

        for visto in (stdout, otlp, enc):
            assert "1234567" not in visto

    def test_campos_viram_dict(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.a = FakeAttrs(DOC, 1)
        record.b = FakePydanticV1(DOC, 2)
        RedactionFilter().filter(record)

        assert record.a == {"document": "*******8901", "amount": 1}
        assert record.b == {"document": "*******8901", "amount": 2}

    def test_dict_que_quebra_nao_derruba_e_fecha_mascarado(self):
        class Quebrado:
            def dict(self):
                raise ValueError(DOC)

        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.input = Quebrado()
        RedactionFilter().filter(record)

        assert record.input == "*****"

    def test_atributo_chamado_dict_que_nao_e_metodo_nao_e_confundido(self):
        class Config:
            def __init__(self):
                self.dict = {"a": 1}

        cfg = Config()
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.cfg = cfg
        RedactionFilter().filter(record)

        assert record.cfg is cfg

    def test_classe_nao_e_instancia(self):
        record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
        record.tipo = FakeAttrs
        RedactionFilter().filter(record)

        assert record.tipo is FakeAttrs
