"""CNT-3524: mascaramento por sufixo de chave, camelCase/kebab e Mask.NAME."""

from dataclasses import dataclass
import json
import logging

import pytest

from otel_observability.logging import (
    CONTA_DIGITAL_MASK_POLICY,
    DEFAULT_MASK_POLICY,
    Mask,
    RedactionFilter,
)

DOC = "12345678901"
CONTA = "9876543210"
EMAIL = "joao.silva@exemplo.com.br"
NOME = "Joao da Silva"


def _record(**extra):
    record = logging.LogRecord("n", logging.INFO, "p", 1, "msg", None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _filtro():
    return RedactionFilter(mask_policy=CONTA_DIGITAL_MASK_POLICY)


def _mascarar(chave, valor, filtro=None):
    """Passa o valor por props[chave] com o colaborador real e devolve o que sobrou."""
    record = _record(props={chave: valor})
    (filtro or _filtro()).filter(record)
    return record.props[chave]


DOCUMENTOS = [
    "documentNumber",
    "customerDocument",
    "accountDocument",
    "taxId",
    "taxID",
    "tax_id",
    "sender_document",
    "recipient_document",
    "user_document",
    "business_document",
    "account_number",
    "account_branch",
    "accountNumber",
    "customer_cpf",
    "customerCpf",
    "partner_cnpj",
    "partnerCnpj",
    "sender_account_number",
]
CHAVES_PIX = ["pixKey", "pix-key", "addressingKey", "recipient_pix_key"]
NOMES = ["account_name", "holder_name", "trade_name", "user_name", "accountName", "holderName"]
EMAILS = ["user_email", "userEmail", "customer_email"]


@pytest.mark.unit
class TestSufixoECamelCase:
    @pytest.mark.parametrize("chave", DOCUMENTOS)
    def test_documento_e_conta_mascarados(self, chave):
        mascarado = _mascarar(chave, DOC)

        assert mascarado == "*******8901"

    @pytest.mark.parametrize("chave", CHAVES_PIX)
    def test_chave_pix_mascarada(self, chave):
        assert _mascarar(chave, DOC) == "*******8901"
        assert _mascarar(chave, EMAIL).endswith("@exemplo.com.br")
        assert "joao" not in _mascarar(chave, EMAIL)

    @pytest.mark.parametrize("chave", NOMES)
    def test_nome_vira_iniciais(self, chave):
        assert _mascarar(chave, NOME) == "J. d. S."

    @pytest.mark.parametrize("chave", EMAILS)
    def test_email_mascarado(self, chave):
        mascarado = _mascarar(chave, EMAIL)

        assert mascarado.endswith("@exemplo.com.br")
        assert "joao" not in mascarado

    def test_chave_em_maiusculo(self):
        assert _mascarar("SENDER_DOCUMENT", DOC) == "*******8901"
        assert _mascarar("Sender-Document", DOC) == "*******8901"

    def test_camel_case_cai_na_chave_exata_do_default(self):
        """O default nao muda, mas a normalizacao vale pra ele: documentNumber -> document_number."""
        record = _record(props={"documentNumber": DOC})
        RedactionFilter().filter(record)

        assert record.props["documentNumber"] == "*******8901"

    def test_default_sozinho_nao_ganha_sufixo(self):
        record = _record(props={"customerDocument": DOC, "user_email": EMAIL, "user_name": NOME})
        RedactionFilter().filter(record)

        assert record.props == {"customerDocument": DOC, "user_email": EMAIL, "user_name": NOME}


@pytest.mark.unit
class TestSufixoEmQualquerFormaDeColecao:
    """Requisito negativo: a chave sensivel e mascarada em toda forma de container."""

    def test_dict_aninhado(self):
        record = _record(props={"a": {"b": {"customerDocument": DOC}}})
        _filtro().filter(record)

        assert record.props["a"]["b"]["customerDocument"] == "*******8901"

    def test_lista_de_dicts(self):
        record = _record(props={"itens": [{"sender_document": DOC}, {"ok": 1}]})
        _filtro().filter(record)

        assert record.props["itens"][0]["sender_document"] == "*******8901"
        assert record.props["itens"][1] == {"ok": 1}

    def test_tupla_de_dicts(self):
        record = _record(props=({"holder_name": NOME},))
        _filtro().filter(record)

        assert record.props[0]["holder_name"] == "J. d. S."

    def test_conjunto_de_strings_json(self):
        record = _record(props={json.dumps({"sender_document": DOC})})
        _filtro().filter(record)

        (item,) = record.props
        assert DOC not in item

    def test_string_json(self):
        record = _record(raw=json.dumps({"userEmail": EMAIL}))
        _filtro().filter(record)

        assert "joao" not in record.raw

    def test_dataclass(self):
        @dataclass
        class Dto:
            customerDocument: str

        record = _record(input=Dto(customerDocument=DOC))
        _filtro().filter(record)

        assert record.input == {"customerDocument": "*******8901"}

    def test_topo_do_record(self):
        record = _record(sender_document=DOC)
        _filtro().filter(record)

        assert record.sender_document == "*******8901"


@pytest.mark.unit
class TestChavesQueNaoPodemSerMascaradas:
    @pytest.mark.parametrize(
        "chave",
        [
            "key",
            "name",
            "event_name",
            "file_name",
            "eventName",
            "filename",
            "username",
            "document_id",
            "documents",
            "redocument",
            "my_documents",
            "xaccount_number",
            "account_numbers",
            "email_verified",
            "emailed",
            "s3_key",
            "cache_key",
            "pix_keys_count",
        ],
    )
    def test_intocada(self, chave):
        assert _mascarar(chave, "valor-de-negocio") == "valor-de-negocio"

    def test_name_e_key_no_topo_do_record(self):
        record = _record(key="cache:abc", event_name="x", file_name="y.csv")
        _filtro().filter(record)

        assert (record.key, record.event_name, record.file_name) == ("cache:abc", "x", "y.csv")
        assert record.name == "n"  # atributo reservado do LogRecord

    def test_policy_nao_declara_key_nem_name_sozinhos(self):
        chaves = set(DEFAULT_MASK_POLICY) | set(CONTA_DIGITAL_MASK_POLICY)

        assert not chaves & {"key", "name", "*_name", "*_key"}

    @pytest.mark.parametrize("valor", [None, 0, 1.5, True, "", "texto"])
    def test_valor_nao_sensivel_de_qualquer_tipo_passa(self, valor):
        assert _mascarar("event_name", valor) == valor


@pytest.mark.unit
class TestResolucaoDaPolicy:
    def test_chave_exata_vence_o_sufixo(self):
        filtro = RedactionFilter(mask_policy={"*_document": Mask.LAST4, "sender_document": "full"})

        assert _mascarar("sender_document", DOC, filtro) == "*****"
        assert _mascarar("other_document", DOC, filtro) == "*******8901"

    def test_sufixo_mais_longo_vence(self):
        filtro = RedactionFilter(mask_policy={"*_document": Mask.LAST4, "*_tax_document": "full"})

        assert _mascarar("company_tax_document", DOC, filtro) == "*****"
        assert _mascarar("company_document", DOC, filtro) == "*******8901"

    def test_sufixo_nao_casa_a_chave_sozinha(self):
        filtro = RedactionFilter(mask_policy={"*_protocolo": Mask.LAST4})

        assert _mascarar("protocolo", "abcdefgh", filtro) == "abcdefgh"
        assert _mascarar("cliente_protocolo", "abcdefgh", filtro) == "****efgh"

    def test_consumidor_define_sufixo_e_chave_em_camel_case(self):
        filtro = RedactionFilter(mask_policy={"*_Protocolo": "last4", "numeroProposta": "last4"})

        assert _mascarar("clienteProtocolo", "abcdefgh", filtro) == "****efgh"
        assert _mascarar("numero_proposta", "abcdefgh", filtro) == "****efgh"
        assert _mascarar("numeroProposta", "abcdefgh", filtro) == "****efgh"

    def test_policy_do_consumidor_sobrescreve_sufixo_da_conta_digital(self):
        filtro = RedactionFilter(mask_policy={**CONTA_DIGITAL_MASK_POLICY, "*_document": "full"})

        assert _mascarar("sender_document", DOC, filtro) == "*****"

    def test_redact_keys_legado_continua_valendo(self):
        record = _record(custom_secret="x")
        RedactionFilter(redact_keys=["custom_secret"]).filter(record)

        assert record.custom_secret == "*****"

    def test_estrategia_invalida_em_sufixo_falha_no_startup(self):
        with pytest.raises(ValueError, match="not a valid Mask"):
            RedactionFilter(mask_policy={"*_x": "last5"})

    def test_estrategia_invalida_em_chave_exata_continua_falhando(self):
        with pytest.raises(ValueError, match="not a valid Mask"):
            RedactionFilter(mask_policy={"x": "last5"})

    @pytest.mark.parametrize("sufixo", ["*", "*_", "*  "])
    def test_sufixo_vazio_falha_no_startup(self, sufixo):
        with pytest.raises(ValueError, match="sufixo"):
            RedactionFilter(mask_policy={sufixo: "full"})

    def test_idempotente_nos_dois_handlers(self):
        record = _record(props={"sender_document": DOC, "holder_name": NOME})
        _filtro().filter(record)
        primeiro = dict(record.props)
        _filtro().filter(record)

        assert (
            record.props
            == primeiro
            == {"sender_document": "*******8901", "holder_name": "J. d. S."}
        )


@pytest.mark.unit
class TestMaskName:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("Joao da Silva", "J. d. S."),
            ("João da Silva", "J. d. S."),
            ("Maria", "M."),
            ("", ""),
            ("   ", ""),
            ("  Ana   Maria  ", "A. M."),
            ("ana maria", "a. m."),
            ("José", "J."),
        ],
    )
    def test_iniciais(self, entrada, esperado):
        filtro = RedactionFilter(mask_policy={"nome": Mask.NAME})

        assert _mascarar("nome", entrada, filtro) == esperado

    @pytest.mark.parametrize("estrategia", ["name", "NAME", "Name", Mask.NAME])
    def test_aceita_o_nome_em_qualquer_caixa(self, estrategia):
        filtro = RedactionFilter(mask_policy={"nome": estrategia})

        assert _mascarar("nome", "Joao Silva", filtro) == "J. S."

    def test_nao_entrega_o_sobrenome(self):
        mascarado = _mascarar("holder_name", "Fernanda Albuquerque Montenegro")

        assert "lbuquerque" not in mascarado
        assert "ontenegro" not in mascarado

    def test_bytes_e_numero_nao_quebram(self):
        filtro = RedactionFilter(mask_policy={"nome": Mask.NAME})

        assert _mascarar("nome", b"Joao Silva", filtro) == "J. S."
        assert isinstance(_mascarar("nome", 12345, filtro), str)


@pytest.mark.unit
class TestBytesEmChaveSensivel:
    @pytest.mark.parametrize("tipo", [bytes, bytearray])
    def test_sem_sobra_de_digito(self, tipo):
        record = _record(cpf=tipo(DOC.encode()))
        RedactionFilter().filter(record)

        assert record.cpf == "*******8901"

    def test_bytes_em_chave_por_sufixo(self):
        assert _mascarar("sender_document", DOC.encode()) == "*******8901"

    def test_bytes_email(self):
        mascarado = _mascarar("user_email", EMAIL.encode())

        assert mascarado.endswith("@exemplo.com.br")
        assert "joao" not in mascarado

    def test_bytes_pix(self):
        assert _mascarar("pixKey", DOC.encode()) == "*******8901"

    def test_bytes_nao_utf8_nao_derruba(self):
        mascarado = _mascarar("sender_document", b"\xff\xfe12345678901")

        assert "b'" not in mascarado
        assert mascarado.endswith("8901")

    def test_mask_document_publico_com_bytes(self):
        from otel_observability import mask_document

        assert mask_document(DOC.encode()) == "*******8901"

    def test_bytes_em_credencial_continua_totalmente_mascarado(self):
        record = _record(api_key=b"segredo")
        RedactionFilter().filter(record)

        assert record.api_key == "*****"
