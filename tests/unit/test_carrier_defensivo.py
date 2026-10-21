import logging
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest

from otel_observability import aws_lambda as aws_lambda_module
from otel_observability import chalice as chalice_module
from otel_observability.aws_lambda import instrument_lambda_handler
from otel_observability.chalice import trace_sqs_message
from otel_observability.config import TelemetryConfig

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

ATRIBUTOS_SQS_SEM_STRING = [
    {"dataType": "Binary", "binaryValue": "AAEC"},
    {"dataType": "String"},
    "texto-solto",
    None,
    123,
]
ATRIBUTOS_SNS_SEM_STRING = [
    {"Type": "Binary", "Value": None},
    {"Type": "Binary"},
    {"Type": "Binary", "Value": b"\x00\x01"},
    "texto-solto",
    None,
]


def _sqs(attr):
    return {
        "Records": [
            {
                "eventSource": "aws:sqs",
                "messageAttributes": {"traceparent": attr, "tracestate": attr},
            }
        ]
    }


def _sns(attr):
    return {
        "Records": [
            {
                "eventSource": "aws:sns",
                "Sns": {"MessageAttributes": {"traceparent": attr, "tracestate": attr}},
            }
        ]
    }


@pytest.fixture(name="ambiente")
def _ambiente():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("teste")
    aws_lambda_module._instrumented = False
    chalice_module._instrumented = False
    with (
        patch.object(aws_lambda_module, "get_tracer", return_value=tracer),
        patch.object(chalice_module, "get_tracer", return_value=tracer),
        patch.object(aws_lambda_module, "flush_telemetry"),
        patch.object(chalice_module, "flush_telemetry"),
        patch.object(aws_lambda_module, "init_telemetry"),
        patch.object(aws_lambda_module, "configure_logging"),
        patch.object(aws_lambda_module, "auto_instrument"),
    ):
        yield tracer, exporter
    aws_lambda_module._instrumented = False
    chalice_module._instrumented = False


def _handler_lambda():
    chamadas = []
    handler = MagicMock(side_effect=lambda e, c: chamadas.append(1) or {"ok": True})
    handler.__name__ = "h"
    contexto = MagicMock()
    contexto.function_name = "fn"
    return instrument_lambda_handler(config=TelemetryConfig.from_env())(handler), chamadas, contexto


def _span_lambda(exporter):
    return next(s for s in exporter.get_finished_spans() if s.name.startswith("lambda."))


@pytest.mark.unit
class TestLambdaCarrierDefensivo:
    @pytest.mark.parametrize("construir", [_sqs, _sns])
    @pytest.mark.parametrize("attr", ATRIBUTOS_SQS_SEM_STRING + ATRIBUTOS_SNS_SEM_STRING)
    def test_atributo_sem_string_nao_derruba_e_mantem_contexto_atual(
        self, ambiente, construir, attr
    ):
        tracer, exporter = ambiente
        decorado, chamadas, contexto = _handler_lambda()

        with tracer.start_as_current_span("pai") as pai:
            assert decorado(construir(attr), contexto) == {"ok": True}

        assert chamadas == [1]
        filho = _span_lambda(exporter)
        assert filho.parent.span_id == pai.get_span_context().span_id

    @pytest.mark.parametrize(
        ("evento", "chave"),
        [
            (
                {
                    "Records": [
                        {
                            "eventSource": "aws:sqs",
                            "messageAttributes": {
                                "traceparent": {"dataType": "String", "stringValue": TRACEPARENT}
                            },
                        }
                    ]
                },
                "sqs",
            ),
            (
                {
                    "Records": [
                        {
                            "eventSource": "aws:sns",
                            "Sns": {
                                "MessageAttributes": {
                                    "traceparent": {"Type": "String", "Value": TRACEPARENT}
                                }
                            },
                        }
                    ]
                },
                "sns",
            ),
        ],
    )
    def test_atributo_string_continua_propagando(self, ambiente, evento, chave):
        _, exporter = ambiente
        decorado, _, contexto = _handler_lambda()

        decorado(evento, contexto)

        assert _span_lambda(exporter).parent.span_id == int("b7ad6b7169203331", 16), chave

    def test_registros_e_atributos_malformados_nao_derrubam(self, ambiente):
        decorado, chamadas, contexto = _handler_lambda()
        for evento in (
            {"Records": [{"eventSource": "aws:sqs", "messageAttributes": "x"}]},
            {"Records": [{"eventSource": "aws:sns", "Sns": {"MessageAttributes": ["x"]}}]},
        ):
            decorado(evento, contexto)
        assert chamadas == [1, 1]


@pytest.mark.unit
class TestChaliceSqsCarrierDefensivo:
    @pytest.mark.parametrize(
        "attr",
        [a for a in ATRIBUTOS_SQS_SEM_STRING + ATRIBUTOS_SNS_SEM_STRING if a != "texto-solto"],
    )
    def test_trace_sqs_message_com_atributo_sem_string(self, ambiente, attr):
        tracer, exporter = ambiente
        chamadas = []
        decorado = trace_sqs_message(lambda e: chamadas.append(1) or "ok")

        with tracer.start_as_current_span("pai") as pai:
            decorado({"messageId": "m1", "messageAttributes": {"traceparent": attr}})

        assert chamadas == [1]
        filho = next(s for s in exporter.get_finished_spans() if s.name == "sqs.process")
        assert filho.parent.span_id == pai.get_span_context().span_id


@pytest.fixture(autouse=True)
def _silencio():
    logging.getLogger("otel_observability").setLevel(logging.CRITICAL)
    yield
    logging.getLogger("otel_observability").setLevel(logging.NOTSET)
