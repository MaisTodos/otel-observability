"""Testes unitários para o módulo config."""

import os
from unittest.mock import patch

import pytest

from otel_observability.config import TelemetryConfig


@pytest.mark.unit
class TestTelemetryConfig:
    """Testes para TelemetryConfig."""

    def test_from_env_with_all_vars(self, mock_env_vars: dict):
        """Testa criação de config com todas as variáveis de ambiente."""
        config = TelemetryConfig.from_env()

        assert config.service_name == "test-service"
        assert config.environment == "test"
        assert config.service_version == "1.0.0"
        assert config.otlp_endpoint == "http://localhost:4318"
        assert config.enable_console_export is False
        assert config.log_level == "INFO"
        assert config.sample_rate == 1.0

    def test_from_env_with_defaults(self):
        """Testa criação de config com valores padrão."""
        with patch.dict(os.environ, {}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.service_name == "unknown-service"
            assert config.environment == "development"
            assert config.service_version == "0.0.0"
            assert config.otlp_endpoint == "http://localhost:4318"
            assert config.sample_rate == 1.0

    def test_from_env_custom_endpoint(self):
        """Testa configuração de endpoint customizado."""
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://custom:4318"}):
            config = TelemetryConfig.from_env()
            assert config.otlp_endpoint == "http://custom:4318"

    def test_from_env_detect_lambda(self):
        """Testa detecção de ambiente Lambda."""
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-function"}):
            config = TelemetryConfig.from_env()
            assert config.is_lambda is True

    def test_from_env_not_lambda(self, mock_env_vars: dict):
        """Testa que não é Lambda quando variável não está presente."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove AWS_LAMBDA_FUNCTION_NAME se existir
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            config = TelemetryConfig.from_env()
            assert config.is_lambda is False

    def test_parse_headers_from_env(self):
        """Testa parsing de headers do ambiente."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_HEADERS": "key1=value1,key2=value2"},
        ):
            config = TelemetryConfig.from_env()
            assert config.otlp_headers == {"key1": "value1", "key2": "value2"}

    def test_parse_headers_datadog(self):
        """Testa parsing de headers do Datadog."""
        with patch.dict(
            os.environ,
            {
                "DD_API_KEY": "test-api-key",
                "DD_SITE": "datadoghq.com",
            },
        ):
            config = TelemetryConfig.from_env()
            assert config.otlp_headers["dd-api-key"] == "test-api-key"
            assert config.otlp_headers["dd-site"] == "datadoghq.com"

    def test_console_export_enabled(self):
        """Testa habilitação de console export."""
        with patch.dict(os.environ, {"OTEL_CONSOLE_EXPORT": "true"}):
            config = TelemetryConfig.from_env()
            assert config.enable_console_export is True

    def test_sample_rate_custom(self):
        """Testa configuração de sample rate customizado."""
        with patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "0.5"}):
            config = TelemetryConfig.from_env()
            assert config.sample_rate == 0.5

    def test_sample_rate_invalid_raises_error(self):
        """Testa que sample rate inválido levanta erro."""
        with (
            patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "2.0"}),
            pytest.raises(ValueError, match="sample_rate must be between"),
        ):
            TelemetryConfig.from_env()

    def test_sample_rate_negative_raises_error(self):
        """Testa que sample rate negativo levanta erro."""
        with (
            patch.dict(os.environ, {"OTEL_TRACES_SAMPLER_ARG": "-0.1"}),
            pytest.raises(ValueError, match="sample_rate must be between"),
        ):
            TelemetryConfig.from_env()

    def test_warning_on_unknown_service(self):
        """Testa que warning é emitido quando service_name não está definido."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.warns(UserWarning, match="OTEL_SERVICE_NAME not set"):
                config = TelemetryConfig.from_env()
            assert config.service_name == "unknown-service"

    def test_config_construivel_sem_log_format(self):
        """Consumidor que constroi config propria (parametro `config=` dos
        instrument_*) nao pode quebrar por causa de campo novo."""
        config = TelemetryConfig(
            service_name="svc",
            environment="prod",
            service_version="1.0.0",
            otlp_endpoint="http://x:4318",
            otlp_traces_endpoint=None,
            otlp_metrics_endpoint=None,
            otlp_logs_endpoint=None,
            traces_enabled=False,
            otlp_headers=None,
            is_lambda=False,
            enable_console_export=False,
            log_level="INFO",
            sample_rate=1.0,
            dogstatsd_enabled=False,
            dogstatsd_host="localhost",
            dogstatsd_port=8125,
        )

        assert config.log_format is None
        assert config.sample_rate == 1.0

    # ------------------------------------------------------------------
    # Signal-specific endpoint resolution
    # ------------------------------------------------------------------

    def test_traces_endpoint_falls_back_to_generic(self):
        """Endpoint genérico é usado como fallback para traces."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4318"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            assert config.otlp_traces_endpoint == "http://generic:4318/v1/traces"
            assert config.traces_enabled is True

    def test_traces_endpoint_signal_specific_overrides_generic(self):
        """Endpoint específico de traces sobrescreve o genérico."""
        with patch.dict(
            os.environ,
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4318",
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://traces-only:4318",
            },
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            assert config.otlp_traces_endpoint == "http://traces-only:4318"
            assert config.otlp_endpoint == "http://generic:4318"

    def test_traces_disabled_when_no_endpoint(self):
        """Sem nenhum endpoint configurado, traces ficam desabilitados."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.warns(UserWarning, match="No OTLP traces endpoint"):
                config = TelemetryConfig.from_env()
            assert config.otlp_traces_endpoint is None
            assert config.traces_enabled is False

    def test_traces_disabled_explicitly_via_env(self):
        """OTEL_TRACES_ENABLED=false desabilita traces mesmo com endpoint."""
        with patch.dict(
            os.environ,
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel:4318",
                "OTEL_TRACES_ENABLED": "false",
            },
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            assert config.traces_enabled is False

    def test_logs_endpoint_falls_back_to_generic(self):
        """Endpoint genérico é usado como fallback para logs."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4318"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            assert config.otlp_logs_endpoint == "http://generic:4318/v1/logs"

    def test_logs_endpoint_signal_specific(self):
        """Endpoint específico de logs é respeitado."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://otlp.datadoghq.com/v1/logs"},
            clear=True,
        ):
            with pytest.warns(UserWarning, match="No OTLP traces endpoint"):
                config = TelemetryConfig.from_env()
            assert config.otlp_logs_endpoint == "https://otlp.datadoghq.com/v1/logs"

    def test_metrics_endpoint_signal_specific(self):
        """Endpoint específico de métricas é respeitado."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "https://otlp.datadoghq.com/v1/metrics"},
            clear=True,
        ):
            with pytest.warns(UserWarning, match="No OTLP traces endpoint"):
                config = TelemetryConfig.from_env()
            assert config.otlp_metrics_endpoint == "https://otlp.datadoghq.com/v1/metrics"

    def test_warning_emitted_when_no_traces_endpoint(self):
        """Warning é emitido quando nenhum endpoint de traces está configurado."""
        with patch.dict(os.environ, {}, clear=True):  # noqa: SIM117
            with pytest.warns(UserWarning, match="No OTLP traces endpoint configured"):
                TelemetryConfig.from_env()

    def test_endpoint_generico_completa_o_path_por_sinal(self):
        """Sidecar: OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 precisa virar
        /v1/traces e /v1/logs, senao os dois sinais POSTam na raiz e no mesmo URL."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()

            assert config.otlp_traces_endpoint == "http://localhost:4318/v1/traces"
            assert config.otlp_logs_endpoint == "http://localhost:4318/v1/logs"
            assert config.otlp_metrics_endpoint == "http://localhost:4318/v1/metrics"

    def test_endpoint_generico_com_barra_final_nao_duplica(self):
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318/"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()

            assert config.otlp_traces_endpoint == "http://localhost:4318/v1/traces"

    def test_endpoint_por_sinal_fica_verbatim(self):
        """Quem declarou o endpoint do sinal ja disse o alvo final — nao mexer."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://otlp.datadoghq.com/v1/logs"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()

            assert config.otlp_logs_endpoint == "https://otlp.datadoghq.com/v1/logs"

    def test_endpoint_por_sinal_com_rota_propria_nao_ganha_path(self):
        """Proxy/gateway com rota propria: completar path aqui quebraria."""
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://gateway:8080/telemetria"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()

            assert config.otlp_traces_endpoint == "http://gateway:8080/telemetria"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("env", "explicit", "default", "esperado"),
    [
        (None, None, False, False),  # FastAPI sem env: comportamento de hoje
        (None, None, True, True),  # Lambda sem env: comportamento de hoje
        ("json", None, False, True),  # env liga JSON no FastAPI — o bug corrigido
        ("text", None, True, False),  # env desliga JSON no Lambda
        ("", None, True, True),  # env vazia é ignorada
        ("JSON", None, False, True),  # case-insensitive
        ("text", True, False, True),  # parâmetro explícito vence a env
    ],
)
def test_resolve_json_logs(monkeypatch, env, explicit, default, esperado):
    if env is None:
        monkeypatch.delenv("OTEL_LOG_FORMAT", raising=False)
    else:
        monkeypatch.setenv("OTEL_LOG_FORMAT", env)
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")

    cfg = TelemetryConfig.from_env()

    assert cfg.resolve_json_logs(explicit, default=default) is esperado


@pytest.mark.unit
class TestSeedOtelEnv:
    """Testes para seed_otel_env."""

    def test_seed_from_object(self):
        """Popula os.environ a partir de um objeto de settings."""
        from otel_observability.config import seed_otel_env

        class Settings:
            OTEL_SERVICE_NAME = "banking-credit-api"
            DD_API_KEY = "dd-key"

        with patch.dict(os.environ, {}, clear=True):
            applied = seed_otel_env(Settings())
            assert os.environ["OTEL_SERVICE_NAME"] == "banking-credit-api"
            assert os.environ["DD_API_KEY"] == "dd-key"
            assert applied["OTEL_SERVICE_NAME"] == "banking-credit-api"

    def test_seed_from_dict(self):
        """Aceita também um dicionário como fonte."""
        from otel_observability.config import seed_otel_env

        with patch.dict(os.environ, {}, clear=True):
            seed_otel_env({"OTEL_ENVIRONMENT": "production"})
            assert os.environ["OTEL_ENVIRONMENT"] == "production"

    def test_seed_skips_empty_and_missing(self):
        """Valores vazios ou ausentes não são injetados."""
        from otel_observability.config import seed_otel_env

        class Settings:
            OTEL_SERVICE_NAME = ""

        with patch.dict(os.environ, {}, clear=True):
            seed_otel_env(Settings())
            assert "OTEL_SERVICE_NAME" not in os.environ
            assert "DD_API_KEY" not in os.environ

    def test_seed_does_not_override_existing_env(self):
        """setdefault: env real do processo tem precedência sobre settings."""
        from otel_observability.config import seed_otel_env

        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": "real"}, clear=True):
            seed_otel_env({"OTEL_SERVICE_NAME": "from-settings"})
            assert os.environ["OTEL_SERVICE_NAME"] == "real"

    def test_overrides_take_precedence_over_source(self):
        """Overrides explícitos vencem o valor do source."""
        from otel_observability.config import seed_otel_env

        with patch.dict(os.environ, {}, clear=True):
            seed_otel_env({"OTEL_SERVICE_NAME": "from-source"}, OTEL_SERVICE_NAME="override")
            assert os.environ["OTEL_SERVICE_NAME"] == "override"


@pytest.mark.unit
def test_versao_do_pacote_bate_com_pyproject():
    """__version__ do pacote é a mesma versão declarada no pyproject.toml."""
    from pathlib import Path

    import tomllib

    from otel_observability import __version__

    pyproject = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
    assert __version__ == pyproject["project"]["version"]


@pytest.mark.unit
def test_timeout_aceita_fracao_de_segundo(monkeypatch):
    """int() derrubava o startup com ValueError em 1.5."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "1.5")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")

    assert TelemetryConfig.from_env().export_timeout == 1.5


@pytest.mark.unit
@pytest.mark.parametrize("valor", ["true", "  ", "1", "yes"])
def test_valor_desconhecido_de_log_format_cai_no_default(monkeypatch, valor):
    """Em Lambda (default True), valor nao reconhecido nao pode desligar o JSON em silencio."""
    monkeypatch.setenv("OTEL_LOG_FORMAT", valor)
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")

    cfg = TelemetryConfig.from_env()

    assert cfg.resolve_json_logs(None, default=True) is True
    assert cfg.resolve_json_logs(None, default=False) is False


MARCADOR_ENV = "secret-value-123"


def _mensagens_encadeadas(exc: BaseException) -> str:
    partes, atual = [], exc
    while atual is not None:
        partes += [str(atual), repr(atual)]
        atual = atual.__cause__ or atual.__context__
    return "\n".join(partes)


@pytest.mark.unit
@pytest.mark.parametrize(
    "variavel",
    ["OTEL_EXPORTER_OTLP_TIMEOUT", "OTEL_TRACES_SAMPLER_ARG", "DD_DOGSTATSD_PORT"],
)
def test_env_numerica_invalida_nao_repete_o_valor(monkeypatch, variavel):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")
    monkeypatch.setenv(variavel, MARCADOR_ENV)

    with pytest.raises(ValueError, match=variavel) as info:
        TelemetryConfig.from_env()

    assert MARCADOR_ENV not in _mensagens_encadeadas(info.value)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("OTEL_EXPORTER_OTLP_TIMEOUT", "0.001"),
        ("OTEL_TRACES_SAMPLER_ARG", "0"),
        ("OTEL_TRACES_SAMPLER_ARG", "1"),
        ("DD_DOGSTATSD_PORT", "1"),
        ("DD_DOGSTATSD_PORT", "65535"),
    ],
)
def test_ultimo_valor_valido_passa(monkeypatch, variavel, valor):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")
    monkeypatch.setenv(variavel, valor)

    TelemetryConfig.from_env()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("OTEL_EXPORTER_OTLP_TIMEOUT", "0"),
        ("OTEL_EXPORTER_OTLP_TIMEOUT", "-1"),
        ("OTEL_EXPORTER_OTLP_TIMEOUT", "nan"),
        ("OTEL_EXPORTER_OTLP_TIMEOUT", "inf"),
        ("OTEL_EXPORTER_OTLP_TIMEOUT", ""),
        ("OTEL_TRACES_SAMPLER_ARG", "nan"),
        ("OTEL_TRACES_SAMPLER_ARG", "1.0001"),
        ("OTEL_TRACES_SAMPLER_ARG", "-0.0001"),
        ("DD_DOGSTATSD_PORT", "0"),
        ("DD_DOGSTATSD_PORT", "65536"),
        ("DD_DOGSTATSD_PORT", "-1"),
        ("DD_DOGSTATSD_PORT", "8125.5"),
    ],
)
def test_primeiro_valor_invalido_e_rejeitado_sem_ecoar(monkeypatch, variavel, valor):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")
    monkeypatch.setenv(variavel, valor)

    with pytest.raises(ValueError, match=variavel) as info:
        TelemetryConfig.from_env()

    assert info.value.__context__ is None
    if len(valor) > 1:
        assert valor not in str(info.value)


@pytest.mark.unit
def test_aviso_de_log_format_desconhecido_nao_ecoa_o_valor(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")
    monkeypatch.setenv("OTEL_LOG_FORMAT", MARCADOR_ENV)
    config = TelemetryConfig.from_env()

    with pytest.warns(UserWarning, match="OTEL_LOG_FORMAT") as avisos:
        config.resolve_json_logs(None, default=True)

    assert all(MARCADOR_ENV not in str(a.message) for a in avisos)
    assert any("json" in str(a.message) for a in avisos)


@pytest.mark.unit
@pytest.mark.parametrize("valor", [MARCADOR_ENV, "0", "65536"])
def test_porta_do_dogstatsd_so_e_validada_quando_habilitado(monkeypatch, valor):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "svc-teste")
    monkeypatch.setenv("DD_DOGSTATSD_PORT", valor)

    monkeypatch.setenv("DD_DOGSTATSD_ENABLED", "false")
    assert TelemetryConfig.from_env().dogstatsd_enabled is False

    monkeypatch.setenv("DD_DOGSTATSD_ENABLED", "true")
    with pytest.raises(ValueError, match="DD_DOGSTATSD_PORT"):
        TelemetryConfig.from_env()
