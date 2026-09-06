"""Testes unitários para o módulo tracer."""

from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace.sampling import Decision, ParentBased
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    StatusCode,
    TraceFlags,
    set_span_in_context,
)
import pytest

from otel_observability.config import TelemetryConfig
import otel_observability.tracer
from otel_observability.tracer import (
    get_current_span,
    get_current_span_id,
    get_current_trace_id,
    get_tracer,
    init_telemetry,
    shutdown_telemetry,
)
from otel_observability.tracer import (
    trace as trace_decorator,
)


@pytest.mark.unit
class TestInitTelemetry:
    """Testes para init_telemetry."""

    def test_init_telemetry_with_config(self, telemetry_config: TelemetryConfig, reset_telemetry):
        """Testa inicialização com configuração."""
        mock_trace_module = MagicMock()
        with (
            patch("otel_observability.tracer.TracerProvider") as mock_provider,
            patch("otel_observability.tracer.trace_api", mock_trace_module),
            patch("otel_observability.tracer.set_global_textmap"),
            patch("otel_observability.tracer._tracer_provider", None),
        ):
            init_telemetry(telemetry_config)

            # Verificar que TracerProvider foi criado
            assert mock_provider.called

    def test_init_telemetry_from_env(self, mock_env_vars: dict, reset_telemetry):
        """Testa inicialização a partir de variáveis de ambiente."""
        mock_trace_module = MagicMock()
        with (
            patch("otel_observability.tracer.TracerProvider") as mock_provider,
            patch("otel_observability.tracer.trace_api", mock_trace_module),
            patch("otel_observability.tracer.set_global_textmap"),
            patch("otel_observability.tracer._tracer_provider", None),
            patch("otel_observability.logging.init_otlp_log_export", MagicMock()),
        ):
            init_telemetry()

            assert mock_provider.called

    def test_init_telemetry_idempotent(self, telemetry_config: TelemetryConfig, reset_telemetry):
        """Testa que init_telemetry é idempotente."""
        mock_trace_module = MagicMock()
        with (
            patch("otel_observability.tracer.TracerProvider") as mock_provider,
            patch("otel_observability.tracer.trace_api", mock_trace_module),
            patch("otel_observability.tracer.set_global_textmap"),
            patch("otel_observability.tracer._tracer_provider", None),
            patch("otel_observability.logging.init_otlp_log_export", MagicMock()),
            patch("otel_observability.tracer.logger") as mock_logger,
        ):
            init_telemetry(telemetry_config)
            call_count_1 = mock_provider.call_count

            # Chamar novamente — deve logar warning e retornar sem reinicializar
            init_telemetry(telemetry_config)
            call_count_2 = mock_provider.call_count

            # Deve ter sido chamado apenas uma vez
            assert call_count_1 == call_count_2
            mock_logger.warning.assert_called_once_with("Telemetry already initialized. Skipping.")

    def test_init_telemetry_no_otlp_exporter_when_traces_disabled(
        self, telemetry_config: TelemetryConfig, reset_telemetry
    ):
        """OTLPSpanExporter não é criado quando traces estão desabilitados."""
        telemetry_config.otlp_traces_endpoint = None
        telemetry_config.traces_enabled = False

        mock_trace_module = MagicMock()
        with (
            patch("otel_observability.tracer.TracerProvider"),
            patch("otel_observability.tracer.OTLPSpanExporter") as mock_exporter,
            patch("otel_observability.tracer.trace_api", mock_trace_module),
            patch("otel_observability.tracer.set_global_textmap"),
            patch("otel_observability.tracer._tracer_provider", None),
            patch("otel_observability.logging.init_otlp_log_export", MagicMock()),
        ):
            init_telemetry(telemetry_config)
            mock_exporter.assert_not_called()

    def test_init_telemetry_uses_traces_endpoint(
        self, telemetry_config: TelemetryConfig, reset_telemetry
    ):
        """OTLPSpanExporter usa otlp_traces_endpoint, não otlp_endpoint."""
        telemetry_config.otlp_traces_endpoint = "http://traces-only:4318"
        telemetry_config.traces_enabled = True

        mock_trace_module = MagicMock()
        with (
            patch("otel_observability.tracer.TracerProvider"),
            patch("otel_observability.tracer.OTLPSpanExporter") as mock_exporter,
            patch("otel_observability.tracer.trace_api", mock_trace_module),
            patch("otel_observability.tracer.set_global_textmap"),
            patch("otel_observability.tracer._tracer_provider", None),
            patch("otel_observability.logging.init_otlp_log_export", MagicMock()),
        ):
            init_telemetry(telemetry_config)
            mock_exporter.assert_called_once()
            call_kwargs = mock_exporter.call_args[1]
            assert call_kwargs["endpoint"] == "http://traces-only:4318"


@pytest.mark.unit
class TestShutdownTelemetry:
    """Testes para shutdown_telemetry."""

    def test_shutdown_telemetry(self, reset_telemetry):
        """Testa shutdown de telemetria."""
        mock_trace_module = MagicMock()
        # Primeiro inicializar
        with patch("otel_observability.tracer.TracerProvider") as mock_provider_class:
            provider = MagicMock()
            mock_provider_class.return_value = provider

            with (
                patch("otel_observability.tracer.trace_api", mock_trace_module),
                patch("otel_observability.tracer.set_global_textmap"),
                patch("otel_observability.tracer._tracer_provider", None),
            ):
                init_telemetry()

                # Mockar o _tracer_provider após init
                with patch("otel_observability.tracer._tracer_provider", provider):
                    # Agora fazer shutdown
                    shutdown_telemetry(timeout=1)

                    # Verificar que force_flush e shutdown foram chamados
                    assert provider.force_flush.called
                    assert provider.shutdown.called


@pytest.mark.unit
class TestGetTracer:
    """Testes para get_tracer."""

    def test_get_tracer_returns_tracer(self, reset_telemetry):
        """Testa que get_tracer retorna um tracer."""
        mock_tracer = MagicMock()
        mock_trace_module = MagicMock()
        mock_trace_module.get_tracer.return_value = mock_tracer

        with patch("otel_observability.tracer.trace_api", mock_trace_module):
            tracer = get_tracer("test.module")

            assert tracer == mock_tracer
            mock_trace_module.get_tracer.assert_called_once_with("test.module")


@pytest.mark.unit
class TestGetCurrentSpan:
    """Testes para get_current_span."""

    def test_get_current_span(self):
        """Testa obtenção de span atual."""
        mock_span = MagicMock()
        mock_trace_module = MagicMock()
        mock_trace_module.get_current_span.return_value = mock_span

        with patch("otel_observability.tracer.trace_api", mock_trace_module):
            span = get_current_span()

            assert span == mock_span


@pytest.mark.unit
class TestGetCurrentTraceId:
    """Testes para get_current_trace_id."""

    def test_get_current_trace_id_with_span(self):
        """Testa obtenção de trace_id quando há span ativo."""
        mock_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.trace_id = 0x12345678901234567890123456789012
        mock_span.get_span_context.return_value = mock_ctx

        # Mockar o módulo trace no namespace do tracer
        mock_trace_module = MagicMock()
        mock_trace_module.get_current_span.return_value = mock_span

        with patch("otel_observability.tracer.trace_api", mock_trace_module):
            trace_id = get_current_trace_id()

            # Trace ID deve ser uma string hex de 32 caracteres
            assert isinstance(trace_id, str)
            assert len(trace_id) == 32
            assert trace_id != ""

    def test_get_current_trace_id_no_span(self):
        """Testa obtenção de trace_id quando não há span."""
        mock_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.trace_id = 0  # trace_id = 0 significa sem trace
        mock_span.get_span_context.return_value = mock_ctx

        # Mockar o módulo trace no namespace do tracer
        mock_trace_module = MagicMock()
        mock_trace_module.get_current_span.return_value = mock_span

        with patch("otel_observability.tracer.trace_api", mock_trace_module):
            trace_id = get_current_trace_id()

            assert trace_id == ""


@pytest.mark.unit
class TestGetCurrentSpanId:
    """Testes para get_current_span_id."""

    def test_get_current_span_id_with_span(self):
        """Testa obtenção de span_id quando há span ativo."""
        mock_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.span_id = 0x1234567890123456
        mock_span.get_span_context.return_value = mock_ctx

        # Mockar o módulo trace no namespace do tracer
        mock_trace_module = MagicMock()
        mock_trace_module.get_current_span.return_value = mock_span

        with patch("otel_observability.tracer.trace_api", mock_trace_module):
            span_id = get_current_span_id()

            # Span ID deve ser uma string hex de 16 caracteres
            assert isinstance(span_id, str)
            assert len(span_id) == 16
            assert span_id != ""

    def test_get_current_span_id_no_span(self):
        """Testa obtenção de span_id quando não há span."""
        mock_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.span_id = 0  # span_id = 0 significa sem span
        mock_span.get_span_context.return_value = mock_ctx

        # Mockar o módulo trace no namespace do tracer
        mock_trace_module = MagicMock()
        mock_trace_module.get_current_span.return_value = mock_span

        with patch("otel_observability.tracer.trace_api", mock_trace_module):
            span_id = get_current_span_id()

            assert span_id == ""


@pytest.mark.unit
class TestTraceDecorator:
    """Testes para o decorator @trace."""

    def test_trace_decorator_sync_function(self):
        """Testa decorator @trace em função síncrona."""

        @trace_decorator("test_operation")
        def test_func(x: int, y: int) -> int:
            return x + y

        with patch("otel_observability.tracer.get_tracer") as mock_get_tracer:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            result = test_func(2, 3)

            assert result == 5
            mock_tracer.start_as_current_span.assert_called_once_with("test_operation")

    def test_trace_decorator_with_attributes(self):
        """Testa decorator @trace com atributos."""

        @trace_decorator("test_operation", attributes={"key": "value"})
        def test_func():
            return "result"

        with patch("otel_observability.tracer.get_tracer") as mock_get_tracer:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            test_func()

            # Verificar que set_attributes foi chamado com os atributos customizados
            mock_span.set_attributes.assert_called_once_with({"key": "value"})
            # Verificar que atributos automáticos também foram setados
            assert mock_span.set_attribute.call_count >= 2  # code.function e code.namespace

    def test_trace_decorator_with_exception(self):
        """Testa decorator @trace com exceção."""

        @trace_decorator("test_operation")
        def test_func():
            raise ValueError("Test error")

        with patch("otel_observability.tracer.get_tracer") as mock_get_tracer:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            with pytest.raises(ValueError, match="Test error"):
                test_func()

            # Verificar que span foi marcado como erro
            mock_span.set_status.assert_called()
            calls = mock_span.set_status.call_args_list
            assert any(call[0][0].status_code == StatusCode.ERROR for call in calls)


@pytest.mark.unit
class TestSampler:
    """Testes para o sampler do TracerProvider (ParentBased)."""

    def test_sampler_e_parent_based(
        self, mock_env_vars: dict, monkeypatch: pytest.MonkeyPatch, reset_telemetry
    ):
        """Sampler do provider é ParentBased, com a taxa da config no sampler raiz."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
        monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "0.1")

        init_telemetry()

        sampler = otel_observability.tracer._tracer_provider.sampler
        assert isinstance(sampler, ParentBased)

    def test_decisao_do_pai_e_respeitada(
        self, mock_env_vars: dict, monkeypatch: pytest.MonkeyPatch, reset_telemetry
    ):
        """Pai amostrado força filho amostrado, mesmo com sample_rate=0.0."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
        monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "0.0")  # sozinho, descartaria tudo

        init_telemetry()

        parent_ctx = set_span_in_context(
            NonRecordingSpan(
                SpanContext(
                    trace_id=0x1234,
                    span_id=0x5678,
                    is_remote=True,
                    trace_flags=TraceFlags(TraceFlags.SAMPLED),
                )
            )
        )

        sampler = otel_observability.tracer._tracer_provider.sampler
        result = sampler.should_sample(parent_ctx, 0x1234, "span-filho")

        assert result.decision is not Decision.DROP
